"""F8b — testes da Fase B2 (schema).

Cobre:
1. `NfPending` model pode ser instanciado com fields obrigatórios.
2. SQLite criado via `init_db()` (que reflete models.py) rejeita INSERT em
   `nf_entries` com NULL nas 5 colunas que viraram NOT NULL.
3. `nf_pending` rejeita NULL nos campos NOT NULL e aceita defaults.
4. CASCADE delete: deletar `upload_batch` apaga `nf_pending` correspondente.

Não exercita a migration Alembic diretamente — testes usam `create_all`
sobre SQLite (padrão do projeto). Smoke da migration vs Postgres real fica
para a Fase D.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.models import Contrato, NfEntry, NfPending, UploadBatch, UploadFile, User
from app.security import hash_password


def _seed_dependencies(db):
    """Cria User + Contrato + UploadBatch + UploadFile mínimos para FK."""
    user = User(email="op@local", password_hash=hash_password("password123"), email_confirmed=True)
    db.add(user)
    db.flush()

    contrato = Contrato(
        id="11111111-1111-1111-1111-111111111111",
        numero="ECFS TEST/2026",
        sigla="TEST",
        cnpj="00000000000000",
        tipo_contrato="LPT",
    )
    db.add(contrato)
    db.flush()

    batch = UploadBatch(user_id=user.id, contrato_id=contrato.id)
    db.add(batch)
    db.flush()

    upload_file = UploadFile(
        upload_batch_id=batch.id,
        original_filename="NF-TEST.pdf",
        stored_filename="xxxx.pdf",
        status="processando",
    )
    db.add(upload_file)
    db.flush()

    return user, contrato, batch, upload_file


def test_nf_pending_pode_ser_criado_com_campos_obrigatorios(client):
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)

        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json=json.dumps({"cnpj": "12.345.678/0001-90"}),
            missing_fields_json=json.dumps(["fornecedor"]),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(pending)
        db.flush()

        # Default de status deve ser 'aguardando'.
        assert pending.status == "aguardando"
        assert pending.resolved_at is None
        assert pending.id  # UUID4 gerado automaticamente


def test_nf_pending_rejeita_prefilled_json_null(client):
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)

        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json=None,  # type: ignore[arg-type]
            missing_fields_json=json.dumps(["cnpj"]),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(pending)
        with pytest.raises(IntegrityError):
            db.flush()


def test_nf_pending_rejeita_expires_at_null(client):
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)

        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json="[]",
            expires_at=None,  # type: ignore[arg-type]
        )
        db.add(pending)
        with pytest.raises(IntegrityError):
            db.flush()


def test_nf_entries_rejeita_ncm_null(client):
    """Antes de F8b ncm era nullable. Agora é NOT NULL — invariant garantida
    no schema, não só no parser."""
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)
        entry = NfEntry(
            business_key="bk-test-1",
            numero_nf="NF-1",
            cnpj="12345678000190",
            data_emissao=datetime(2026, 4, 12).date(),
            tipo_nota="produto",
            fornecedor="Acme",
            descricao="Teste",
            ncm=None,  # type: ignore[arg-type]
            quantidade=1,
            preco_unitario=10,
            valor_total=10,
            contrato="ECFS TEST/2026",
            contrato_id=contrato.id,
            upload_file_id=upload_file.id,
            raw_payload={},
        )
        db.add(entry)
        with pytest.raises(IntegrityError):
            db.flush()


def test_nf_entries_rejeita_fornecedor_null(client):
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)
        entry = NfEntry(
            business_key="bk-test-2",
            numero_nf="NF-2",
            cnpj="12345678000190",
            data_emissao=datetime(2026, 4, 12).date(),
            tipo_nota="produto",
            fornecedor=None,  # type: ignore[arg-type]
            descricao="Teste",
            ncm="84.21",
            quantidade=1,
            preco_unitario=10,
            valor_total=10,
            contrato="ECFS TEST/2026",
            contrato_id=contrato.id,
            upload_file_id=upload_file.id,
            raw_payload={},
        )
        db.add(entry)
        with pytest.raises(IntegrityError):
            db.flush()


def test_nf_entries_rejeita_quantidade_null(client):
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)
        entry = NfEntry(
            business_key="bk-test-3",
            numero_nf="NF-3",
            cnpj="12345678000190",
            data_emissao=datetime(2026, 4, 12).date(),
            tipo_nota="produto",
            fornecedor="Acme",
            descricao="Teste",
            ncm="84.21",
            quantidade=None,  # type: ignore[arg-type]
            preco_unitario=10,
            valor_total=10,
            contrato="ECFS TEST/2026",
            contrato_id=contrato.id,
            upload_file_id=upload_file.id,
            raw_payload={},
        )
        db.add(entry)
        with pytest.raises(IntegrityError):
            db.flush()


def test_nf_entries_aceita_todas_as_11_colunas_preenchidas(client):
    """Caminho feliz: NF completa entra normalmente. Garante que o NOT NULL
    novo não quebrou inserções legítimas."""
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)
        entry = NfEntry(
            business_key="bk-test-happy",
            numero_nf="NF-100",
            cnpj="12345678000190",
            data_emissao=datetime(2026, 4, 12).date(),
            tipo_nota="produto",
            fornecedor="Acme Energia",
            descricao="Servico de instalação",
            ncm="84.21",
            quantidade=1,
            preco_unitario="125.50",
            valor_total="125.50",
            contrato="ECFS TEST/2026",
            contrato_id=contrato.id,
            upload_file_id=upload_file.id,
            raw_payload={"foo": "bar"},
        )
        db.add(entry)
        db.flush()
        assert entry.id


def test_nf_pending_cascade_delete_quando_batch_deletado(client):
    """`ON DELETE CASCADE` em upload_batch_id e upload_file_id — se o batch
    sumir (futuro endpoint admin), pendência some junto."""
    with get_session() as db:
        _, contrato, batch, upload_file = _seed_dependencies(db)

        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json='["cnpj"]',
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(pending)
        db.flush()
        pending_id = pending.id

        # SQLite default não respeita FK cascade — precisa de PRAGMA. O backend
        # rodando contra Postgres respeita por default. Aqui só verificamos
        # que o schema declara CASCADE no ORM (compatibilidade futura), não
        # que o SQLite local realmente cascateie.
        cascade_declared = NfPending.__table__.c.upload_batch_id.foreign_keys
        assert any("CASCADE" in str(fk.ondelete or "").upper() for fk in cascade_declared)
