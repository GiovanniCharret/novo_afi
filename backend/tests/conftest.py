from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import init_db, reset_db_state
from app.main import app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path / "uploads"))
    reset_db_state()
    init_db()
    return TestClient(app)
