"""F2 B2 — testes do seed de `contratos`.

Não usa a fixture `client` porque o lifespan do app dispara o seed do JSON
real; aqui montamos um JSON pequeno em tmp_path e testamos a função
`seed_contratos` isoladamente.
"""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Contrato
from app.seeds.seed_contratos import (
    _uuid_for_numero,
    _validate_entry,
    seed_contratos,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    """Sessão SQLAlchemy contra SQLite em arquivo temporário."""
    db_path = tmp_path / "seed_test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _write_json(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "base_contratos.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _make_contrato_dict(**overrides):
    base = {
        "sigla": "CPFL",
        "cnpj": "53859112000169",
        "tranche": "2ª Tranche",
        "uf": "SP",
        "valor_contrato": 2143980,
        "valor_cde": 1715180,
        "participacao_cde": 0.8,
        "tipo_contrato": "LPT",
    }
    base.update(overrides)
    return base


def test_uuid_for_numero_is_deterministic():
    """Mesmo numero → mesmo UUID em runs separados (adversarial #31)."""
    a = _uuid_for_numero("ECFS 101/2005")
    b = _uuid_for_numero("ECFS 101/2005")
    assert a == b
    assert _uuid_for_numero("ECFS 102/2005") != a


def test_seed_creates_contratos(tmp_path, db_session):
    json_path = _write_json(tmp_path, {
        "ECFS 101/2005": _make_contrato_dict(),
        "ECFS 108/2005": _make_contrato_dict(sigla="CPFL Jaguari", uf="SP"),
    })

    total = seed_contratos(db_session, json_path=json_path)

    assert total == 2
    rows = db_session.query(Contrato).order_by(Contrato.numero).all()
    assert len(rows) == 2
    assert rows[0].numero == "ECFS 101/2005"
    assert rows[0].sigla == "CPFL"
    assert rows[0].id == _uuid_for_numero("ECFS 101/2005")


def test_seed_is_idempotent(tmp_path, db_session):
    """Rodar 2x não duplica."""
    json_path = _write_json(tmp_path, {
        "ECFS 101/2005": _make_contrato_dict(),
    })

    seed_contratos(db_session, json_path=json_path)
    seed_contratos(db_session, json_path=json_path)

    rows = db_session.query(Contrato).all()
    assert len(rows) == 1


def test_seed_updates_existing_on_value_change(tmp_path, db_session):
    """Mesmo numero, valores diferentes no JSON → UPDATE, não duplicata."""
    json_path = _write_json(tmp_path, {
        "ECFS 101/2005": _make_contrato_dict(valor_contrato=1000),
    })
    seed_contratos(db_session, json_path=json_path)

    json_path = _write_json(tmp_path, {
        "ECFS 101/2005": _make_contrato_dict(valor_contrato=2000),
    })
    seed_contratos(db_session, json_path=json_path)

    rows = db_session.query(Contrato).all()
    assert len(rows) == 1
    assert int(rows[0].valor_contrato) == 2000


def test_seed_rejects_missing_required_field(tmp_path, db_session):
    """JSON malformado falha cedo com erro claro."""
    json_path = _write_json(tmp_path, {
        "ECFS 999/2099": {"sigla": "X", "cnpj": "00000000000000"},  # sem tipo_contrato
    })

    with pytest.raises(ValueError, match="tipo_contrato"):
        seed_contratos(db_session, json_path=json_path)


def test_seed_rejects_non_numeric_value(tmp_path, db_session):
    """valor_contrato não-numérico → ValueError."""
    bad = _make_contrato_dict()
    bad["valor_contrato"] = "muito"

    json_path = _write_json(tmp_path, {"ECFS 999/2099": bad})

    with pytest.raises(ValueError, match="valor_contrato"):
        seed_contratos(db_session, json_path=json_path)


def test_seed_file_not_found_raises_filenotfound(tmp_path, db_session):
    """JSON ausente → FileNotFoundError. Lifespan captura e pula seed."""
    inexistente = tmp_path / "nao_existe.json"

    with pytest.raises(FileNotFoundError):
        seed_contratos(db_session, json_path=inexistente)


def test_validate_entry_rejects_non_dict():
    with pytest.raises(ValueError, match="dict"):
        _validate_entry("ECFS 999/2099", "string ao invés de dict")  # type: ignore
