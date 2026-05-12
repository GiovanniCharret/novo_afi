"""F4 — endpoint `GET /api/uploads/files/{id}/pdf`.

Cobertura:
- Sem auth → 401.
- Id inexistente → 404.
- Id válido e arquivo em disco → 200 com headers corretos.
- `?download=true` → Content-Disposition: attachment.
- Inline default → Content-Disposition: inline.
- Usuário A não acessa PDF de batch do usuário B → 404 (não 403).
- Arquivo removido do disco → 404.

Setup: insere User + Contrato + UploadBatch + UploadFileRecord diretamente
no DB, grava bytes do PDF em `UPLOAD_STORAGE_DIR/<batch_id>/<stored_filename>`.
Não passa pelo fluxo de upload — testes ficam rápidos e isolados.
"""
import os
from pathlib import Path

import pytest

from app.db import get_session
from app.models import Contrato, UploadBatch, UploadFile as UploadFileRecord, User


PDF_BYTES = b"%PDF-1.4\n%fake pdf content for tests\n"


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_user(username: str = "user") -> str:
    """Garante que o User existe no DB e retorna seu id."""
    with get_session() as db:
        existing = db.scalar(
            __import__("sqlalchemy").select(User).where(User.username == username)
        )
        if existing:
            return existing.id
        u = User(username=username, password_hash="placeholder", display_name=username)
        db.add(u)
        db.commit()
        return u.id


def _seed_batch(user_id: str) -> str:
    with get_session() as db:
        b = UploadBatch(user_id=user_id)
        db.add(b)
        db.commit()
        return b.id


def _seed_upload_file(
    batch_id: str,
    stored_filename: str | None = None,
    original_filename: str = "nota.pdf",
) -> str:
    with get_session() as db:
        uf = UploadFileRecord(
            upload_batch_id=batch_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            status="processado",
            inserted_count=1,
            duplicate_count=0,
        )
        db.add(uf)
        db.commit()
        return uf.id


def _write_pdf(stored_filename: str, batch_id: str) -> Path:
    """Grava o PDF fake no UPLOAD_STORAGE_DIR/<batch_id>/<stored_filename>."""
    storage = Path(os.environ["UPLOAD_STORAGE_DIR"]).resolve()
    batch_dir = storage / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    path = batch_dir / stored_filename
    path.write_bytes(PDF_BYTES)
    return path


# ---------------------------------------------------------------- 401

def test_pdf_endpoint_requires_authentication(client) -> None:
    response = client.get("/api/uploads/files/qualquer-id/pdf")
    assert response.status_code == 401


# ---------------------------------------------------------------- 404 (id inexistente)

def test_pdf_endpoint_unknown_id_returns_404(client) -> None:
    authenticate(client)
    response = client.get("/api/uploads/files/nao-existe/pdf")
    assert response.status_code == 404


# ---------------------------------------------------------------- 200 inline

def test_pdf_endpoint_returns_pdf_inline_by_default(client) -> None:
    user_id = _seed_user()
    batch_id = _seed_batch(user_id)
    stored = "f4-test-001.pdf"
    uf_id = _seed_upload_file(batch_id, stored_filename=stored, original_filename="minha-nota.pdf")
    _write_pdf(stored, batch_id)

    authenticate(client)
    response = client.get(f"/api/uploads/files/{uf_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    cd = response.headers["content-disposition"]
    assert cd.startswith("inline"), cd
    assert "minha-nota.pdf" in cd
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == PDF_BYTES


# ---------------------------------------------------------------- 200 attachment

def test_pdf_endpoint_download_query_returns_attachment(client) -> None:
    user_id = _seed_user()
    batch_id = _seed_batch(user_id)
    stored = "f4-test-002.pdf"
    uf_id = _seed_upload_file(batch_id, stored_filename=stored, original_filename="baixar.pdf")
    _write_pdf(stored, batch_id)

    authenticate(client)
    response = client.get(f"/api/uploads/files/{uf_id}/pdf?download=true")

    assert response.status_code == 200
    cd = response.headers["content-disposition"]
    assert cd.startswith("attachment"), cd
    assert "baixar.pdf" in cd


# ---------------------------------------------------------------- 404 (outro usuário)

def test_pdf_endpoint_does_not_leak_other_users_pdf(client) -> None:
    """User A autenticado tenta acessar PDF de batch do User B → 404, não 403."""
    user_b_id = _seed_user(username="other_user")
    batch_b_id = _seed_batch(user_b_id)
    stored = "f4-test-003.pdf"
    uf_b_id = _seed_upload_file(batch_b_id, stored_filename=stored)
    _write_pdf(stored, batch_b_id)

    authenticate(client)  # autentica como "user" (default fixture)

    response = client.get(f"/api/uploads/files/{uf_b_id}/pdf")
    assert response.status_code == 404


# ---------------------------------------------------------------- 404 (arquivo sumiu)

def test_pdf_endpoint_returns_404_when_file_missing_on_disk(client) -> None:
    user_id = _seed_user()
    batch_id = _seed_batch(user_id)
    # Row aponta para stored_filename mas arquivo NÃO existe em disco.
    uf_id = _seed_upload_file(batch_id, stored_filename="nao-existe-no-disco.pdf")

    authenticate(client)
    response = client.get(f"/api/uploads/files/{uf_id}/pdf")
    assert response.status_code == 404


# ---------------------------------------------------------------- fallback heurístico

def test_pdf_endpoint_falls_back_to_original_filename_when_stored_is_null(client) -> None:
    """Legados pré-F4 sem stored_filename: resolver tenta original_filename."""
    user_id = _seed_user()
    batch_id = _seed_batch(user_id)
    uf_id = _seed_upload_file(
        batch_id,
        stored_filename=None,  # legado pré-F4
        original_filename="legado.pdf",
    )
    # Grava o arquivo com o nome original (não com UUID, simula pré-F4).
    storage = Path(os.environ["UPLOAD_STORAGE_DIR"]).resolve()
    batch_dir = storage / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "legado.pdf").write_bytes(PDF_BYTES)

    authenticate(client)
    response = client.get(f"/api/uploads/files/{uf_id}/pdf")

    assert response.status_code == 200
    assert response.content == PDF_BYTES
