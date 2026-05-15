"""F8b camada 1 — dedup por SHA256 do PDF.

Re-upload de um arquivo byte-idêntico (mesmo usuário, desfecho bem-sucedido
anterior) é interceptado antes do parser: marcado `duplicado` com razão
específica de SHA256. Cobre o bug 2026-05-14 (operador subiu o mesmo batch
duas vezes e gerou NFs duplicadas).
"""
from app.db import get_session
from app.models import Contrato, NfEntry, UploadBatch, UploadFile
from app.parser_adapter import ParserOutcome


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contrato(numero: str) -> str:
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


def _row(**overrides):
    base = {
        "descricao": "Servico de instalacao",
        "ncm": "84.21",
        "quant": 1,
        "preco_unitario": "100,00",
        "numero_nf": "555",
        "tipo_nota": "product",
        "data_emissao": "03/10/2024",
        "cnpj": "01.126.556/0001-91",
        "fornecedor": "Fornecedor Teste",
        "valor": "100,00",
        "contrato": "ECFS 101/2005",
    }
    base.update(overrides)
    return base


def _parse_sse_statuses(text: str) -> list[dict]:
    """Extrai os eventos file_done do corpo SSE."""
    import json
    events = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk.startswith("data: "):
            continue
        try:
            ev = json.loads(chunk[6:])
        except json.JSONDecodeError:
            continue
        if ev.get("event") == "file_done":
            events.append(ev)
    return events


# Bytes de PDF idênticos reusados entre os dois uploads — é isso que dá o
# mesmo SHA256.
PDF_BYTES = b"%PDF-1.4 conteudo-de-teste-fixo para gerar sha estavel"


def test_reupload_mesmo_arquivo_vira_duplicado(client, monkeypatch):
    """1º upload processa; 2º upload do MESMO arquivo é duplicado por SHA256
    sem chamar o parser."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    parse_calls = {"n": 0}

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            parse_calls["n"] += 1
            return ParserOutcome(status="processado", rows=[_row()], reason=None, error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    # 1º upload — processa normalmente.
    r1 = client.post("/api/uploads", files=[("files", ("nf.pdf", PDF_BYTES, "application/pdf"))])
    assert r1.status_code == 200
    done1 = _parse_sse_statuses(r1.text)
    assert len(done1) == 1
    assert done1[0]["status"] == "processado"
    assert parse_calls["n"] == 1

    # 2º upload — MESMO arquivo. Deve virar duplicado SEM chamar o parser.
    r2 = client.post("/api/uploads", files=[("files", ("nf.pdf", PDF_BYTES, "application/pdf"))])
    assert r2.status_code == 200
    done2 = _parse_sse_statuses(r2.text)
    assert len(done2) == 1
    assert done2[0]["status"] == "duplicado"
    assert "já foi enviado" in done2[0]["status_reason"].lower()
    assert parse_calls["n"] == 1, "parser não pode ter rodado no re-upload"

    # Banco tem só UMA NfEntry — o re-upload não inseriu nada.
    with get_session() as db:
        assert db.query(NfEntry).count() == 1


def test_reupload_com_nome_diferente_ainda_e_duplicado(client, monkeypatch):
    """SHA256 é do conteúdo — renomear o arquivo não escapa do dedup."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            return ParserOutcome(status="processado", rows=[_row()], reason=None, error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    client.post("/api/uploads", files=[("files", ("original.pdf", PDF_BYTES, "application/pdf"))])
    r2 = client.post("/api/uploads", files=[("files", ("renomeado.pdf", PDF_BYTES, "application/pdf"))])

    done2 = _parse_sse_statuses(r2.text)
    assert done2[0]["status"] == "duplicado"
    assert "já foi enviado" in done2[0]["status_reason"].lower()


def test_arquivo_distinto_nao_e_marcado_duplicado(client, monkeypatch):
    """Conteúdo diferente → SHA diferente → processa normalmente."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            # Cada arquivo gera uma NF distinta (numero_nf derivado do conteúdo).
            numero = "A" if b"arquivo-A" in content else "B"
            return ParserOutcome(
                status="processado", rows=[_row(numero_nf=numero)], reason=None, error=None
            )

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    client.post("/api/uploads", files=[("files", ("a.pdf", b"%PDF arquivo-A", "application/pdf"))])
    r2 = client.post("/api/uploads", files=[("files", ("b.pdf", b"%PDF arquivo-B", "application/pdf"))])

    done2 = _parse_sse_statuses(r2.text)
    assert done2[0]["status"] == "processado"

    with get_session() as db:
        assert db.query(NfEntry).count() == 2


def test_reupload_apos_falha_de_parser_nao_e_duplicado(client, monkeypatch):
    """Se o 1º upload falhou (erro_parsing), o re-upload PODE tentar de novo —
    SHA256 só dedupa contra desfechos terminais bem-sucedidos."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    state = {"falhar": True}

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            if state["falhar"]:
                return ParserOutcome(status="erro_parsing", rows=[], reason="estrutura", error="x")
            return ParserOutcome(status="processado", rows=[_row()], reason=None, error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    r1 = client.post("/api/uploads", files=[("files", ("nf.pdf", PDF_BYTES, "application/pdf"))])
    assert _parse_sse_statuses(r1.text)[0]["status"] == "erro_parsing"

    # 2ª tentativa do mesmo arquivo — não pode ser bloqueada por SHA256.
    state["falhar"] = False
    r2 = client.post("/api/uploads", files=[("files", ("nf.pdf", PDF_BYTES, "application/pdf"))])
    done2 = _parse_sse_statuses(r2.text)
    assert done2[0]["status"] == "processado", (
        "re-upload após falha deve poder reprocessar, não cair em duplicado"
    )
