"""Testes dos fixes de 2026-05-19 — ver docs/BUG_validacao_numerica_pre_insert.md
e docs/BUG_sessao_sqlalchemy_envenenada.md.

Item 3 — campo numérico ilegível do parser é roteado para o fluxo de
preenchimento humano do F8b (modal `nf_pending`), não para `erro_parsing`.
NF de 1 linha → vira pendência. NF multi-linha → cai no safety net
`NfRowValidationError` -> `erro_parsing` (sem `0` silencioso nem crash).

Item 4 — erro de banco ao inserir as linhas de UM arquivo (dentro do
SAVEPOINT por arquivo) não envenena a Session nem derruba o lote inteiro.

Nota sobre cobertura: o fluxo F8b de suspender o generator e retomar via
`/resolve` não é dirigível por `TestClient` (cada request abre seu próprio
event loop, então o `asyncio.Event` do registry não cruza requests). Os
testes abaixo que envolvem pendência pré-setam o event do registry para o
generator não suspender — verificam que a `NfPending` é criada corretamente.
A resolução em si (`/resolve` inserindo a NfEntry) é coberta por
`test_pending_endpoints.py`.
"""
import asyncio
import json

from app.db import get_session
from app.models import Contrato, NfEntry, NfPending, UploadFile as UploadFileRecord
from app.parser_adapter import ParserOutcome
from app.server import _invalid_numeric_fields


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contrato(numero: str = "ECFS 101/2005") -> str:
    contrato_id = f"id-{numero}"
    with get_session() as db:
        db.add(Contrato(
            id=contrato_id,
            numero=numero,
            sigla="CPFL",
            cnpj="53859112000169",
            tranche="2ª Tranche",
            uf="SP",
            valor_contrato=2143980,
            valor_cde=1715180,
            participacao_cde="0.8",
            tipo_contrato="LPT",
            ativo=True,
        ))
        db.commit()
    return contrato_id


def _select_contrato(client, contrato_id: str) -> None:
    response = client.post("/api/session/contrato", json={"contrato_id": contrato_id})
    assert response.status_code == 200


def _row(numero_nf: str, contrato_numero: str, **overrides) -> dict:
    """Linha válida no formato que o parser entrega. `overrides` injeta defeitos."""
    row = {
        "descricao": "Serviço de instalação",
        "ncm": "não se aplica",
        "quant": "1",
        "preco_unitario": "5656,23",
        "numero_nf": numero_nf,
        "tipo_nota": "service",
        "data_emissao": "03/10/2024",
        "cnpj": "01.126.556/0001-91",
        "fornecedor": "Fornecedor Teste",
        "valor": "5656,23",
        "contrato": contrato_numero,
    }
    row.update(overrides)
    return row


def _patch_registry_no_suspend(monkeypatch) -> None:
    """Faz `pending_registry.register` devolver um Event já setado — o
    generator emite `file_pending_input`, cria a `NfPending` (commit) e segue
    sem suspender. Permite dirigir o caminho pelo TestClient."""
    def _fake_register(pending_id):
        ev = asyncio.Event()
        ev.set()
        return ev

    monkeypatch.setattr("app.pending_registry.register", _fake_register)


# ---------- _invalid_numeric_fields (unidade) ----------

def test_invalid_numeric_fields_detecta_ilegivel_e_ausente() -> None:
    cn = "ECFS 101/2005"
    assert _invalid_numeric_fields(_row("1", cn)) == []
    # caso NF-12259: "R$ ..." não converte para Decimal
    assert _invalid_numeric_fields(
        _row("1", cn, preco_unitario="R$ 160.569,92")
    ) == ["preco_unitario"]
    # ausente, ilegível e lixo — todos detectados
    bad = _row("1", cn, quant=None, preco_unitario="R$ 1", valor="abc")
    assert set(_invalid_numeric_fields(bad)) == {"quant", "preco_unitario", "valor"}


# ---------- Item 3 — NF de 1 linha vira pendência F8b ----------

def test_single_row_illegible_numeric_routes_to_pending(client, monkeypatch) -> None:
    """NF de 1 linha com `preco_unitario`/`valor` ilegíveis (caso NF-12259)
    → `NfPending` criada com esses campos em `missing`, para o operador
    preencher pelo modal F8b. Não vira `erro_parsing`."""
    contrato_id = _seed_contrato()
    authenticate(client)
    _select_contrato(client, contrato_id)
    _patch_registry_no_suspend(monkeypatch)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            return ParserOutcome(
                status="processado",
                rows=[_row("12259", contrato_numero,
                           preco_unitario="R$ 160.569,92",
                           valor="R$ 160.569,92")],
                reason=None, error=None,
            )

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("NF-12259.pdf", b"%PDF-stub", "application/pdf"))],
    )
    assert response.status_code == 200
    assert "file_pending_input" in response.text  # modal foi acionado

    with get_session() as db:
        pendings = db.query(NfPending).all()
        assert len(pendings) == 1, "deveria ter criado exatamente uma NfPending"
        missing = json.loads(pendings[0].missing_fields_json)
        assert set(missing) == {"preco_unitario", "valor"}, (
            f"campos ilegíveis deveriam ir para o modal, recebido: {missing!r}"
        )
        prefilled = json.loads(pendings[0].prefilled_json)
        assert prefilled["numero_nf"] == "12259"  # demais campos prefilled
        assert pendings[0].contrato_id == contrato_id


# ---------- Item 3 — NF multi-linha cai no safety net ----------

def test_multirow_with_illegible_numeric_marks_erro_parsing(client, monkeypatch) -> None:
    """NF com >1 linha foge do modelo single-row da pendência F8b: o campo
    ilegível cai no safety net `NfRowValidationError` -> `erro_parsing`, com
    motivo nomeando o campo. Sem `0` silencioso, sem crash, sem NfEntry."""
    contrato_id = _seed_contrato()
    authenticate(client)
    _select_contrato(client, contrato_id)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            return ParserOutcome(
                status="processado",
                rows=[
                    _row("300", contrato_numero),
                    _row("301", contrato_numero, preco_unitario="R$ 160.569,92"),
                ],
                reason=None, error=None,
            )

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("multi.pdf", b"%PDF-stub", "application/pdf"))],
    )

    assert response.status_code == 200
    assert "event\": \"error\"" not in response.text  # batch não explodiu

    with get_session() as db:
        assert db.query(NfEntry).count() == 0, "nenhuma NfEntry deve ser gravada"
        records = db.query(UploadFileRecord).all()
        assert len(records) == 1
        assert records[0].status == "erro_parsing"
        assert "preco_unitario" in (records[0].status_reason or ""), (
            f"motivo deveria nomear o campo, recebido: {records[0].status_reason!r}"
        )


# ---------- Item 4 — SAVEPOINT isola a falha de um arquivo ----------

def test_batch_survives_db_error_in_one_file(client, monkeypatch) -> None:
    """Lote de 2 PDFs: o 2º dispara erro de banco no flush (fornecedor vazio
    → NOT NULL; não é campo numérico, então não vira pendência). O SAVEPOINT
    por arquivo desfaz só o 2º; o 1º é commitado.

    Antes do fix, a Session envenenada fazia o rollback final descartar o
    lote inteiro — a NfEntry do 1º arquivo era perdida."""
    contrato_id = _seed_contrato()
    authenticate(client)
    _select_contrato(client, contrato_id)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            if filename == "ok.pdf":
                return ParserOutcome(
                    status="processado",
                    rows=[_row("100", contrato_numero)],
                    reason=None, error=None,
                )
            # fornecedor vazio → normalize_nullable_text devolve None →
            # IntegrityError (NOT NULL) dentro do flush de create_nf_entry.
            return ParserOutcome(
                status="processado",
                rows=[_row("200", contrato_numero, fornecedor="")],
                reason=None, error=None,
            )

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[
            ("files", ("ok.pdf", b"%PDF-stub", "application/pdf")),
            ("files", ("ruim.pdf", b"%PDF-stub", "application/pdf")),
        ],
    )

    assert response.status_code == 200
    assert "event\": \"error\"" not in response.text  # lote não foi abortado
    assert "batch_done" in response.text

    with get_session() as db:
        entries = db.query(NfEntry).all()
        assert len(entries) == 1, (
            f"o arquivo bem-sucedido deve sobreviver ao erro do outro; "
            f"encontrado {len(entries)} NfEntry"
        )
        assert entries[0].numero_nf == "100"

        por_nome = {r.original_filename: r.status for r in db.query(UploadFileRecord).all()}
        assert por_nome == {"ok.pdf": "processado", "ruim.pdf": "erro_parsing"}
