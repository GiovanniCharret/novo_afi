"""F2 B4 — testes de integração entre `/api/uploads` e contrato selecionado.

Cobre:
- Upload sem contrato na sessão → 400 (require_contrato)
- Upload com contrato ativo → batch.contrato_id preenchido, parser recebe contrato.numero
- Upload com contrato_id na sessão mas contrato desativado entre seleção e upload → 400 + sessão limpa
- Adapter falha rápido se contrato_numero=None (defesa)

Os testes legados em `test_uploads.py` têm `FakeAdapter` com signature antiga
(2 args) que era pré-F8a. F2 não revive esses testes — eles seguem como
falhas pré-existentes documentadas.
"""
from app.db import get_session
from app.models import Contrato, UploadBatch
from app.parser_adapter import ParserOutcome


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contrato(numero: str, *, ativo: bool = True) -> str:
    """Cria um Contrato no DB de teste e retorna seu id."""
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
            ativo=ativo,
        ))
        db.commit()
    return contrato_id


def _select_contrato(client, contrato_id: str) -> None:
    response = client.post("/api/session/contrato", json={"contrato_id": contrato_id})
    assert response.status_code == 200


def _make_pdf_files(count: int):
    return [("files", (f"nf_{i}.pdf", b"%PDF-stub", "application/pdf")) for i in range(count)]


# -------- Upload sem contrato na sessão --------

def test_upload_without_contrato_returns_400(client) -> None:
    """`require_contrato` (F2) — upload sem contrato_id na sessão → 400."""
    authenticate(client)

    response = client.post("/api/uploads", files=_make_pdf_files(1))

    assert response.status_code == 400
    assert "contrato" in response.json()["detail"].lower()


# -------- Upload com contrato ativo --------

def test_upload_with_contrato_passes_numero_to_adapter(client, monkeypatch) -> None:
    """Adapter recebe `contrato.numero` (string), não o `contrato.id`."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    received = {}

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            received["contrato_numero"] = contrato_numero
            received["filename"] = filename
            return ParserOutcome(status="rejeitado", rows=[], reason="stub", error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post("/api/uploads", files=_make_pdf_files(1))

    assert response.status_code == 200
    assert received["contrato_numero"] == "ECFS 101/2005", (
        f"adapter deveria receber numero do contrato, recebeu: {received!r}"
    )


def test_upload_with_contrato_persists_contrato_id_on_batch(client, monkeypatch) -> None:
    """`UploadBatch.contrato_id` é preenchido com o id do contrato selecionado."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            return ParserOutcome(status="rejeitado", rows=[], reason="stub", error=None)

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post("/api/uploads", files=_make_pdf_files(1))
    assert response.status_code == 200

    with get_session() as db:
        batches = db.query(UploadBatch).all()
        assert len(batches) == 1
        assert batches[0].contrato_id == contrato_id


# -------- Estado stale: contrato desativado --------

def test_upload_with_inactive_contrato_returns_400_and_clears_session(client, monkeypatch) -> None:
    """Contrato_id na sessão mas contrato foi desativado no DB → 400 + sessão limpa."""
    contrato_id = _seed_contrato("ECFS 101/2005")
    authenticate(client)
    _select_contrato(client, contrato_id)

    # Desativa direto no DB (simula admin removendo entre seleção e upload).
    with get_session() as db:
        c = db.get(Contrato, contrato_id)
        c.ativo = False
        db.commit()

    class FakeAdapter:
        def parse_pdf_bytes(self, filename, content, debug_dir, contrato_numero):
            raise AssertionError("adapter não deveria ser chamado quando contrato inativo")

    monkeypatch.setattr("app.server.LegacyParserAdapter", FakeAdapter)

    response = client.post("/api/uploads", files=_make_pdf_files(1))

    assert response.status_code == 400
    assert "ativo" in response.json()["detail"].lower()

    # Confirma que sessão foi limpa
    get_resp = client.get("/api/session/contrato")
    assert get_resp.status_code == 404


# -------- Adapter — defesa contra contrato_numero=None --------

def test_adapter_raises_if_contrato_numero_missing(tmp_path):
    """Adapter falha rápido se caller não passar contrato_numero (defesa F2)."""
    from app.parser_adapter import LegacyParserAdapter

    adapter = LegacyParserAdapter()

    import pytest as _pytest
    with _pytest.raises(ValueError, match="contrato_numero"):
        adapter.parse_pdf_bytes("test.pdf", b"%PDF-stub", None, None)
