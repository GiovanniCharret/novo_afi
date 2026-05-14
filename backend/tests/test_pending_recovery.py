"""F8b — testes da Fase B3b: recovery cross-reboot de pendings órfãos.

O job `expire_orphan_pendings` roda no lifespan do FastAPI. Aqui exercitamos
direto a função (sem subir o servidor de novo), garantindo que pendências
expiradas + upload_files transitórios voltam pra um estado terminal.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import pending_registry
from app.db import get_session
from app.models import Contrato, NfPending, UploadBatch, UploadFile, User
from app.security import hash_password


def _seed_user_contrato_batch_file(db):
    user = User(
        username="op",
        password_hash=hash_password("password"),
        email_confirmed=True,
    )
    db.add(user)
    db.flush()

    contrato = Contrato(
        id="c-recov-1",
        numero="ECFS RECOV/2026",
        sigla="RECOV",
        cnpj="00000000000001",
        tipo_contrato="LPT",
    )
    db.add(contrato)
    db.flush()

    batch = UploadBatch(user_id=user.id, contrato_id=contrato.id)
    db.add(batch)
    db.flush()

    upload_file = UploadFile(
        upload_batch_id=batch.id,
        original_filename="NF-RECOV.pdf",
        stored_filename="x.pdf",
        status="aguardando_preenchimento",
    )
    db.add(upload_file)
    db.flush()

    return contrato, batch, upload_file


def test_expire_orphan_pendings_zera_quando_nao_ha_nada(client):
    with get_session() as db:
        count = pending_registry.expire_orphan_pendings(db)
        assert count == 0


def test_expire_orphan_pendings_marca_pending_e_upload_file(client):
    """Pending com expires_at no passado vira 'expirado' + upload_file vira
    'rejeitado_pendencia_expirada'."""
    with get_session() as db:
        contrato, batch, upload_file = _seed_user_contrato_batch_file(db)
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json='["cnpj"]',
            status="aguardando",
            expires_at=past,
        )
        db.add(pending)
        db.commit()
        pending_id = pending.id
        upload_file_id = upload_file.id

    with get_session() as db:
        count = pending_registry.expire_orphan_pendings(db)
        assert count == 1

    with get_session() as db:
        pending = db.get(NfPending, pending_id)
        assert pending.status == "expirado"
        assert pending.resolved_at is not None

        upload_file = db.get(UploadFile, upload_file_id)
        assert upload_file.status == "rejeitado_pendencia_expirada"
        assert "expirou" in (upload_file.status_reason or "").lower()


def test_expire_orphan_pendings_nao_toca_em_dentro_da_janela(client):
    """Pending com expires_at no FUTURO continua 'aguardando' — pode ser
    legitimamente retomado pelo operador após o reboot enquanto a janela
    de 30min não acabou."""
    with get_session() as db:
        contrato, batch, upload_file = _seed_user_contrato_batch_file(db)
        future = datetime.now(timezone.utc) + timedelta(minutes=15)
        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json='["cnpj"]',
            status="aguardando",
            expires_at=future,
        )
        db.add(pending)
        db.commit()
        pending_id = pending.id

    with get_session() as db:
        count = pending_registry.expire_orphan_pendings(db)
        assert count == 0

    with get_session() as db:
        pending = db.get(NfPending, pending_id)
        assert pending.status == "aguardando"


def test_expire_orphan_pendings_nao_toca_em_resolvido_ou_cancelado(client):
    """Status terminal (resolvido/cancelado/expirado) ficam intocados mesmo
    com expires_at no passado."""
    with get_session() as db:
        contrato, batch, upload_file = _seed_user_contrato_batch_file(db)
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        for st in ("resolvido", "cancelado", "expirado"):
            db.add(NfPending(
                upload_file_id=upload_file.id,
                upload_batch_id=batch.id,
                contrato_id=contrato.id,
                prefilled_json="{}",
                missing_fields_json='[]',
                status=st,
                expires_at=past,
                resolved_at=datetime.now(timezone.utc),
            ))
        db.commit()

    with get_session() as db:
        count = pending_registry.expire_orphan_pendings(db)
        assert count == 0


def test_expire_orphan_pendings_idempotente(client):
    """Rodar 2x não tem efeito da segunda vez."""
    with get_session() as db:
        contrato, batch, upload_file = _seed_user_contrato_batch_file(db)
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.add(NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json='["cnpj"]',
            status="aguardando",
            expires_at=past,
        ))
        db.commit()

    with get_session() as db:
        first = pending_registry.expire_orphan_pendings(db)
    with get_session() as db:
        second = pending_registry.expire_orphan_pendings(db)

    assert first == 1
    assert second == 0


def test_expire_orphan_preserva_upload_file_status_terminal(client):
    """Edge: upload_file que estava 'aguardando_preenchimento' migra pra
    'rejeitado_pendencia_expirada'. Mas se já tem outro status (ex.: parser
    deu erro depois — não deveria, mas defensivo), preserva."""
    with get_session() as db:
        contrato, batch, upload_file = _seed_user_contrato_batch_file(db)
        upload_file.status = "rejeitado"  # outro status terminal
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json="{}",
            missing_fields_json='["cnpj"]',
            status="aguardando",
            expires_at=past,
        )
        db.add(pending)
        db.commit()
        upload_file_id = upload_file.id

    with get_session() as db:
        pending_registry.expire_orphan_pendings(db)

    with get_session() as db:
        upload_file = db.get(UploadFile, upload_file_id)
        # Status final não foi sobrescrito.
        assert upload_file.status == "rejeitado"


def test_pending_registry_module_exports_expire_orphan(client):
    """Sanity: função está acessível via `pending_registry.expire_orphan_pendings`,
    como o lifespan importa."""
    assert hasattr(pending_registry, "expire_orphan_pendings")
    assert callable(pending_registry.expire_orphan_pendings)
