"""F1 Fase B2 — testes dos endpoints de auth real.

Cobre:
- register: cria user com email_confirmed=False + token + envio "stub" de e-mail.
- register: 409 se email duplicado, 422 se senha < 10 chars.
- confirm: token válido → email_confirmed=True; inválido/expirado → 400.
- resend-confirmation: sempre 200 (não vaza); regenera token se user existe.
- login: rejeita user não confirmado (403), e-mail inexistente (401), senha errada (401).
- forgot-password: sempre 200 (não vaza); gera reset_token se user existe.
- reset-password: token válido → senha trocada + login antiga falha; inválido → 400.
- legacy compat: login com `user/password` continua funcionando em APP_ENV=development.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import email_service
from app.db import get_session
from app.models import User


@pytest.fixture(autouse=True)
def _clear_email_buffer():
    email_service.reset_sent_buffer()
    yield
    email_service.reset_sent_buffer()


def _register(client, email: str = "alice@example.com", password: str = "senha123456"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def _login(client, **kwargs):
    return client.post("/api/auth/login", json=kwargs)


# ─────────────────────────────────────────────────────────────────── register

def test_register_creates_user_unconfirmed_and_sends_email(client) -> None:
    response = _register(client)
    assert response.status_code == 201

    with get_session() as db:
        user = db.scalar(__import__("sqlalchemy").select(User).where(User.email == "alice@example.com"))
        assert user is not None
        assert user.email_confirmed is False
        assert user.confirmation_token_hash is not None
        assert user.token_expires_at is not None

    sent = email_service.last_sent_for("alice@example.com")
    assert sent is not None
    # F1 Fase C — link aponta para a SPA com ?confirm=
    assert "?confirm=" in sent.body


def test_register_rejects_short_password(client) -> None:
    response = client.post("/api/auth/register", json={"email": "a@b.com", "password": "curta"})
    assert response.status_code == 422


def test_register_rejects_duplicate_email(client) -> None:
    _register(client)
    response = _register(client)
    assert response.status_code == 409


# ─────────────────────────────────────────────────────────────────── confirm

def _extract_token_from_last_email(email: str) -> str:
    sent = email_service.last_sent_for(email)
    assert sent is not None
    # F1 Fase C — link usa ?confirm=XXX ou ?reset=XXX (rota SPA).
    import re
    m = re.search(r"\?(?:confirm|reset|token)=([0-9a-f]+)", sent.body)
    assert m is not None, f"token não encontrado em: {sent.body!r}"
    return m.group(1)


def test_confirm_valid_token_marks_email_confirmed(client) -> None:
    _register(client)
    token = _extract_token_from_last_email("alice@example.com")

    response = client.get(f"/api/auth/confirm?token={token}")
    assert response.status_code == 200

    with get_session() as db:
        import sqlalchemy as sa
        user = db.scalar(sa.select(User).where(User.email == "alice@example.com"))
        assert user.email_confirmed is True
        assert user.confirmation_token_hash is None
        assert user.token_expires_at is None


def test_confirm_invalid_token_returns_400(client) -> None:
    _register(client)
    response = client.get("/api/auth/confirm?token=tokenfalso123abc")
    assert response.status_code == 400


def test_confirm_expired_token_returns_400(client) -> None:
    _register(client)
    # Força expiração para o passado
    with get_session() as db:
        import sqlalchemy as sa
        user = db.scalar(sa.select(User).where(User.email == "alice@example.com"))
        user.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

    token = _extract_token_from_last_email("alice@example.com")
    response = client.get(f"/api/auth/confirm?token={token}")
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────── resend-confirmation

def test_resend_confirmation_for_unconfirmed_user(client) -> None:
    _register(client)
    email_service.reset_sent_buffer()  # esvazia para não confundir

    response = client.post(
        "/api/auth/resend-confirmation",
        json={"email": "alice@example.com"},
    )
    assert response.status_code == 200

    sent = email_service.last_sent_for("alice@example.com")
    assert sent is not None  # novo e-mail enviado


def test_resend_confirmation_for_nonexistent_email_returns_200(client) -> None:
    """Não vaza enumeração: sempre 200, mesmo se e-mail não existir."""
    response = client.post(
        "/api/auth/resend-confirmation",
        json={"email": "nao_existe@example.com"},
    )
    assert response.status_code == 200
    assert email_service.last_sent_for("nao_existe@example.com") is None


# ─────────────────────────────────────────────────────────────────── login

def test_login_rejects_unconfirmed_user_with_403(client) -> None:
    _register(client)
    response = _login(client, email="alice@example.com", password="senha123456")
    assert response.status_code == 403


def test_login_with_email_inexistente_returns_401(client) -> None:
    response = _login(client, email="ninguem@example.com", password="qualquer123")
    assert response.status_code == 401


def test_login_with_wrong_password_returns_401(client) -> None:
    _register(client)
    token = _extract_token_from_last_email("alice@example.com")
    client.get(f"/api/auth/confirm?token={token}")

    response = _login(client, email="alice@example.com", password="senhaerrada")
    assert response.status_code == 401
    # Mensagem idêntica para os dois casos (não vaza)
    assert "incorretos" in response.json()["detail"].lower()


def test_login_with_confirmed_user_returns_200(client) -> None:
    _register(client)
    token = _extract_token_from_last_email("alice@example.com")
    client.get(f"/api/auth/confirm?token={token}")

    response = _login(client, email="alice@example.com", password="senha123456")
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "alice@example.com"


# ─────────────────────────────────────────────────────────────────── forgot + reset

def test_forgot_password_sends_email_for_existing_user(client) -> None:
    _register(client)
    email_service.reset_sent_buffer()

    response = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert response.status_code == 200

    sent = email_service.last_sent_for("alice@example.com")
    assert sent is not None
    assert "redefinição" in sent.subject.lower() or "reset" in sent.body.lower()


def test_forgot_password_for_nonexistent_returns_200(client) -> None:
    response = client.post("/api/auth/forgot-password", json={"email": "fantasma@example.com"})
    assert response.status_code == 200
    assert email_service.last_sent_for("fantasma@example.com") is None


def test_reset_password_with_valid_token_updates_hash(client) -> None:
    _register(client)
    # confirma o user
    token_conf = _extract_token_from_last_email("alice@example.com")
    client.get(f"/api/auth/confirm?token={token_conf}")
    email_service.reset_sent_buffer()

    # pede reset
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token_reset = _extract_token_from_last_email("alice@example.com")

    # reseta
    response = client.post(
        "/api/auth/reset-password",
        json={"token": token_reset, "new_password": "novasenha999"},
    )
    assert response.status_code == 200

    # senha antiga NÃO funciona
    r_old = _login(client, email="alice@example.com", password="senha123456")
    assert r_old.status_code == 401

    # senha nova FUNCIONA
    r_new = _login(client, email="alice@example.com", password="novasenha999")
    assert r_new.status_code == 200


def test_reset_password_with_invalid_token_returns_400(client) -> None:
    response = client.post(
        "/api/auth/reset-password",
        json={"token": "tokeninexistente", "new_password": "senha123456"},
    )
    assert response.status_code == 400


def test_reset_password_rejects_short_password(client) -> None:
    response = client.post(
        "/api/auth/reset-password",
        json={"token": "abc", "new_password": "curta"},
    )
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────── legacy compat

def test_legacy_username_password_still_works_in_development(client) -> None:
    """Compat: em APP_ENV=development (default em testes), o login legacy
    `user/password` continua funcionando para preservar testes existentes."""
    response = _login(client, username="user", password="password")
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "user"
