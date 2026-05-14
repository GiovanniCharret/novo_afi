"""F8b — testes dos endpoints /api/uploads/pending/{id}/resolve e /cancel.

Não exercitam o generator SSE (isso vem na Fase B3b). Aqui criamos
NfPending direto no DB e validamos a semântica dos endpoints isolados.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import pending_registry
from app.db import get_session
from app.models import Contrato, NfEntry, NfPending, UploadBatch, UploadFile, User


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_pending(
    *,
    prefilled: dict | None = None,
    missing: list[str] | None = None,
    status: str = "aguardando",
    owner_username: str = "user",
) -> str:
    """Cria User + Contrato + Batch + UploadFile + NfPending mínimos
    para os testes dos endpoints. Retorna o nf_pending_id.
    """
    from app.security import hash_password

    with get_session() as db:
        user = db.scalar(select(User).where(User.username == owner_username))
        if user is None:
            user = User(
                username=owner_username,
                password_hash=hash_password("password"),
                email_confirmed=True,
            )
            db.add(user)
            db.flush()

        contrato = Contrato(
            id="c-test-1",
            numero="ECFS PEND/2026",
            sigla="PEND",
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
            original_filename="NF-PEND.pdf",
            stored_filename="xxxx.pdf",
            status="aguardando_preenchimento",
        )
        db.add(upload_file)
        db.flush()

        pending = NfPending(
            upload_file_id=upload_file.id,
            upload_batch_id=batch.id,
            contrato_id=contrato.id,
            prefilled_json=json.dumps(prefilled or {}),
            missing_fields_json=json.dumps(missing or []),
            status=status,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        db.add(pending)
        db.commit()
        return pending.id


# ------------- /resolve -------------

def test_resolve_sem_auth_retorna_401(client):
    response = client.post("/api/uploads/pending/qualquer/resolve", json={"filled": {}})
    assert response.status_code == 401


def test_resolve_pending_inexistente_retorna_404(client):
    authenticate(client)
    response = client.post("/api/uploads/pending/nao-existe/resolve", json={"filled": {"x": "y"}})
    assert response.status_code == 404


def test_resolve_pendencia_de_outro_usuario_retorna_404(client):
    """Não vaza existência via 403 — retorna 404 igual quando não existe."""
    pending_id = _seed_pending(owner_username="outro_usuario")
    authenticate(client)  # loga como "user", não "outro_usuario"

    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": {"cnpj": "12.345.678/0001-90"}},
    )
    assert response.status_code == 404


def test_resolve_insere_nf_entry_e_marca_pending_resolvido(client):
    """Caminho feliz: filled + prefilled → row completa em nf_entries,
    pending vira 'resolvido', upload_file recebe status='processado',
    signal_resolve disparado."""
    prefilled = {
        "descricao": "Servico de instalação",
        "ncm": "84.21",
        "quant": "1",
        "preco_unitario": "100,00",
        "tipo_nota": "produto",
        "data_emissao": "12/04/2026",
        "fornecedor": "Acme Energia",
        "valor": "100,00",
        "numero_nf": "NF-001",
    }
    pending_id = _seed_pending(prefilled=prefilled, missing=["cnpj"])

    # Registra o Event como o generator faria, pra ver se signal_resolve
    # acorda corretamente.
    pending_registry.register(pending_id)

    authenticate(client)
    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": {"cnpj": "12.345.678/0001-90"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "resolvido"
    assert body["outcome"] == "processado"
    assert body["nf_pending_id"] == pending_id
    nf_entry_id = body["nf_entry_id"]

    with get_session() as db:
        # NfPending status='resolvido' + resolved_at preenchido.
        pending = db.get(NfPending, pending_id)
        assert pending.status == "resolvido"
        assert pending.resolved_at is not None

        # NfEntry inserida com cnpj do filled + ncm do prefilled.
        entry = db.get(NfEntry, nf_entry_id)
        assert entry is not None
        assert entry.cnpj == "12345678000190"  # normalize_cnpj
        assert entry.ncm == "84.21"
        assert entry.upload_file_id == pending.upload_file_id

        # UploadFile foi atualizado com status final (caminho generator agora
        # confia em /resolve em vez de sobrescrever).
        upload_file = db.get(UploadFile, pending.upload_file_id)
        assert upload_file.status == "processado"
        assert upload_file.inserted_count == 1
        assert upload_file.duplicate_count == 0

    # signal_resolve foi chamado — desfecho marcado.
    desfecho = pending_registry.consume_desfecho(pending_id)
    assert desfecho.resolved is True


def test_resolve_detecta_duplicado_e_nao_explode(client):
    """F8b fix 2026-05-14: NF com business_key já existente não pode quebrar
    o modal com UniqueViolation. Caminho gracioso: marca upload_file como
    'duplicado', pending como 'resolvido', retorna outcome='duplicado'."""
    from app.normalization import build_business_key
    from datetime import date as _date

    prefilled = {
        "descricao": "Produto repetido",
        "ncm": "84.21",
        "quant": "1",
        "preco_unitario": "200,00",
        "tipo_nota": "produto",
        "data_emissao": "08/10/2024",
        "fornecedor": "Fornecedor Repetido",
        "valor": "200,00",
        "numero_nf": "NF-DUP-1",
    }
    filled = {"cnpj": "12.345.678/0001-90"}

    # Pré-insere a NF (com business_key idêntica à que o /resolve vai construir).
    row_for_key = {**prefilled, **filled, "contrato": "ECFS PEND/2026"}
    business_key = build_business_key(row_for_key)

    pending_id = _seed_pending(prefilled=prefilled, missing=["cnpj"])

    with get_session() as db:
        pending = db.get(NfPending, pending_id)
        pre_existing = NfEntry(
            business_key=business_key,
            numero_nf="NF-DUP-1",
            cnpj="12345678000190",
            data_emissao=_date(2024, 10, 8),
            tipo_nota="produto",
            fornecedor="Fornecedor Repetido",
            descricao="Produto repetido",
            ncm="84.21",
            quantidade=1,
            preco_unitario="200.00",
            valor_total="200.00",
            contrato="ECFS PEND/2026",
            contrato_id=pending.contrato_id,
            raw_payload={},
        )
        db.add(pre_existing)
        db.commit()
        pre_existing_id = pre_existing.id

    pending_registry.register(pending_id)
    authenticate(client)
    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": filled},
    )

    # Não explode com 500; resolve gracioso com outcome=duplicado.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "duplicado"
    assert body["nf_entry_id"] == pre_existing_id  # devolve a NF existente

    with get_session() as db:
        # Pending resolvido (operador não precisa retentar).
        pending = db.get(NfPending, pending_id)
        assert pending.status == "resolvido"

        # UploadFile marcado como duplicado, com mensagem clara.
        upload_file = db.get(UploadFile, pending.upload_file_id)
        assert upload_file.status == "duplicado"
        assert "arquivado" in (upload_file.status_reason or "").lower()
        assert upload_file.duplicate_count == 1
        assert upload_file.inserted_count == 0

        # Banco continua com apenas UMA NfEntry — sem dupe.
        entries = db.scalars(select(NfEntry).where(NfEntry.business_key == business_key)).all()
        assert len(entries) == 1

    # signal_resolve foi chamado igualmente — generator pode prosseguir.
    desfecho = pending_registry.consume_desfecho(pending_id)
    assert desfecho.resolved is True


def test_resolve_em_pendencia_ja_resolvida_retorna_409(client):
    pending_id = _seed_pending(status="resolvido")
    authenticate(client)

    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": {"cnpj": "12.345.678/0001-90"}},
    )
    assert response.status_code == 409
    assert "resolvido" in response.json()["detail"]


def test_resolve_em_pendencia_cancelada_retorna_409(client):
    pending_id = _seed_pending(status="cancelado")
    authenticate(client)

    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": {"cnpj": "12.345.678/0001-90"}},
    )
    assert response.status_code == 409


def test_resolve_sem_filled_quando_ha_missing_retorna_400(client):
    """filled vazio + missing não-vazio = nada pra preencher. Bloqueia
    cedo para evitar gerar nf_entry com NOT NULL faltando."""
    pending_id = _seed_pending(missing=["cnpj"])
    authenticate(client)

    response = client.post(
        f"/api/uploads/pending/{pending_id}/resolve",
        json={"filled": {}},
    )
    assert response.status_code == 400


# ------------- /cancel -------------

def test_cancel_sem_auth_retorna_401(client):
    response = client.post("/api/uploads/pending/qualquer/cancel")
    assert response.status_code == 401


def test_cancel_marca_pending_e_sinaliza_registry(client):
    pending_id = _seed_pending()
    pending_registry.register(pending_id)

    authenticate(client)
    response = client.post(f"/api/uploads/pending/{pending_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelado"

    with get_session() as db:
        pending = db.get(NfPending, pending_id)
        assert pending.status == "cancelado"
        assert pending.resolved_at is not None

    desfecho = pending_registry.consume_desfecho(pending_id)
    assert desfecho.cancelled is True


def test_cancel_pendencia_de_outro_usuario_retorna_404(client):
    pending_id = _seed_pending(owner_username="outro_usuario")
    authenticate(client)

    response = client.post(f"/api/uploads/pending/{pending_id}/cancel")
    assert response.status_code == 404


def test_cancel_em_pendencia_ja_terminal_retorna_409(client):
    pending_id = _seed_pending(status="cancelado")
    authenticate(client)

    response = client.post(f"/api/uploads/pending/{pending_id}/cancel")
    assert response.status_code == 409
