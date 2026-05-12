from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import init_db, reset_db_state
from app.server import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "test.db"
    upload_dir = (tmp_path / "uploads").resolve()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(upload_dir))
    # F4 — UPLOAD_STORAGE_DIR em `server.py` é capturado no import do módulo,
    # então `setenv` sozinho não basta para isolar testes. Patcheamos o atributo
    # do módulo também para que o endpoint de PDF leia o caminho correto.
    monkeypatch.setattr("app.server.UPLOAD_STORAGE_DIR", upload_dir)
    reset_db_state()
    init_db()
    return TestClient(app)
