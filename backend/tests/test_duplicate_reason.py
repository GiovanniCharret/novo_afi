"""F2 follow-up — mensagem de duplicidade enriquecida com contrato.

Cobre 4 cenários ao detectar duplicidade no upload:
1. Todos os duplicados estão arquivados sob o MESMO contrato.
2. Duplicados espalhados em N contratos.
3. Todos os duplicados são pré-F2 (contrato_id NULL).
4. Mistura: alguns com contrato_id, outros sem.

Setup: pré-insere NfEntries no banco com `business_key` que casa com as rows
que a FakeAdapter vai devolver. Como o backend dedupa via UNIQUE
(`business_key`), a colisão garante status="duplicado".
"""
import json
from decimal import Decimal

from app.db import get_session
from app.models import Contrato, NfEntry
from app.normalization import (
    build_business_key,
    normalize_cnpj,
    normalize_text,
    parse_brazilian_date,
    parse_brazilian_decimal,
)
from app.parser_adapter import ParserOutcome


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contrato(numero: str, *, contrato_id: str | None = None) -> str:
    contrato_id = contrato_id or f"id-{numero}"
    with get_session() as db:
        db.add(Contrato(
            id=contrato_id, numero=numero,
            sigla="TEST", cnpj="00000000000000",
            tranche="1ª", uf="SP",
            valor_contrato=0, valor_cde=0, participacao_cde="0",
            tipo_contrato="LPT", ativo=True,
        ))
        db.commit()
    return contrato_id


def _select_contrato(client, contrato_id: str) -> None:
    response = client.post("/api/session/contrato", json={"contrato_id": contrato_id})
    assert response.status_code == 200


def _make_row(**overrides) -> dict:
    """Row padrão; sobrescreva apenas o necessário para diferenciar business_keys."""
    base = {
        "descricao": "Servico de instalacao",
        "ncm": "n/a",
        "quant": 1,
        "preco_unitario": "100,00",
        "numero_nf": "999",
        "tipo_nota": "service",
        "data_emissao": "01/06/2024",
        "cnpj": "01.126.556/0001-91",
        "fornecedor": "Fornecedor X",
        "valor": "100,00",
        "contrato": "qualquer",
    }
    base.update(overrides)
    return base


def _preinsert_nf(row: dict, *, contrato_id: str | None) -> None:
    """Pré-insere uma NfEntry no banco com business_key derivado de `row`.
    Garante colisão quando a FakeAdapter retornar a mesma row em upload."""
    with get_session() as db:
        nf = NfEntry(
            business_key=build_business_key(row),
            numero_nf=normalize_text(row["numero_nf"]),
            cnpj=normalize_cnpj(row["cnpj"]),
            data_emissao=parse_brazilian_date(row["data_emissao"]),
            tipo_nota=normalize_text(row["tipo_nota"]),
            fornecedor=row.get("fornecedor"),
            descricao=normalize_text(row["descricao"]),
            valor_total=parse_brazilian_decimal(row.get("valor")) or Decimal("0"),
            contrato=row.get("contrato"),
            contrato_id=contrato_id,
            raw_payload=row,
        )
        db.add(nf)
        db.commit()


def _parse_sse(text: str) -> list[dict]:
    """Parser leniente para chunks `data: {json}\\n\\n` da SSE."""
    events = []
    for chunk in text.split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data:"):
            payload = chunk[len("data:"):].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


def _file_done(events: list[dict]) -> dict:
    """Retorna o último evento `file_done` (assume 1 arquivo por teste)."""
    matches = [e for e in events if e.get("event") == "file_done"]
    assert matches, f"Nenhum evento file_done encontrado em: {events!r}"
    return matches[-1]


def _post_with_adapter(client, monkeypatch, rows) -> dict:
    """Faz upload de 1 PDF com FakeAdapter devolvendo `rows`; retorna o file_done."""
    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            return ParserOutcome(status="processado", rows=rows, reason=None, error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"%PDF-stub", "application/pdf"))],
    )
    assert response.status_code == 200
    return _file_done(_parse_sse(response.text))


# ------------------------------------------------------------------
# Cenário 1: todos duplicados sob o mesmo contrato.
# ------------------------------------------------------------------

def test_duplicate_reason_mentions_single_contract(client, monkeypatch) -> None:
    cid_upload = _seed_contrato("ECFS 101/2005")
    cid_existente = _seed_contrato("ECFS 326/2012")
    authenticate(client)
    _select_contrato(client, cid_upload)

    row = _make_row(numero_nf="A1")
    _preinsert_nf(row, contrato_id=cid_existente)

    event = _post_with_adapter(client, monkeypatch, [row])

    assert event["status"] == "duplicado"
    assert event["duplicate_count"] == 1
    reason = event["status_reason"]
    assert reason == f"Já foi arquivado no contrato ECFS 326/2012.", reason


# ------------------------------------------------------------------
# Cenário 2: duplicados espalhados em N contratos.
# ------------------------------------------------------------------

def test_duplicate_reason_mentions_multiple_contracts(client, monkeypatch) -> None:
    cid_upload = _seed_contrato("ECFS 101/2005")
    cid_x = _seed_contrato("ECFS 326/2012")
    cid_y = _seed_contrato("ECFS 999/1999")
    authenticate(client)
    _select_contrato(client, cid_upload)

    row_x = _make_row(numero_nf="X")
    row_y = _make_row(numero_nf="Y")
    _preinsert_nf(row_x, contrato_id=cid_x)
    _preinsert_nf(row_y, contrato_id=cid_y)

    event = _post_with_adapter(client, monkeypatch, [row_x, row_y])

    assert event["status"] == "duplicado"
    assert event["duplicate_count"] == 2
    reason = event["status_reason"]
    assert reason.startswith("Já foi arquivado nos contratos:"), reason
    assert "ECFS 326/2012" in reason
    assert "ECFS 999/1999" in reason


# ------------------------------------------------------------------
# Cenário 3: todos pré-F2 (contrato_id NULL).
# ------------------------------------------------------------------

def test_duplicate_reason_handles_pre_f2_null_contrato(client, monkeypatch) -> None:
    cid_upload = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, cid_upload)

    row = _make_row(numero_nf="LEGADO")
    _preinsert_nf(row, contrato_id=None)  # NF pré-F2

    event = _post_with_adapter(client, monkeypatch, [row])

    assert event["status"] == "duplicado"
    assert event["duplicate_count"] == 1
    reason = event["status_reason"]
    assert reason == "Já existe na base (sem contrato registrado, anterior à F2).", reason
    assert "ECFS" not in reason


# ------------------------------------------------------------------
# Cenário 4: mistura — alguns com contrato_id, outros NULL.
# ------------------------------------------------------------------

def test_duplicate_reason_mixes_contract_and_pre_f2(client, monkeypatch) -> None:
    cid_upload = _seed_contrato("ECFS 101/2005")
    cid_x = _seed_contrato("ECFS 326/2012")
    authenticate(client)
    _select_contrato(client, cid_upload)

    row_a = _make_row(numero_nf="COM_CONTRATO")
    row_b = _make_row(numero_nf="SEM_CONTRATO")
    _preinsert_nf(row_a, contrato_id=cid_x)
    _preinsert_nf(row_b, contrato_id=None)

    event = _post_with_adapter(client, monkeypatch, [row_a, row_b])

    assert event["status"] == "duplicado"
    assert event["duplicate_count"] == 2
    reason = event["status_reason"]
    assert reason == "Já foi arquivado (em ECFS 326/2012 + outras anteriores à F2).", reason
