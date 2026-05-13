"""F1 Fase B3 — testes da camada de envio de e-mail.

Cobre:
- Sem env SMTP → cai no stub (armazena buffer + opcionalmente loga).
- Com env SMTP completo → dispatch_smtp é chamado (mockado, não conecta real).
- Falha de SMTP propaga exceção (caller decide).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app import email_service


@pytest.fixture(autouse=True)
def _clean_buffer():
    email_service.reset_sent_buffer()
    yield
    email_service.reset_sent_buffer()


# ─────────────────────────────────────────── stub mode (sem env)

def test_dispatch_uses_stub_when_smtp_envs_missing(monkeypatch) -> None:
    """Sem nenhuma env SMTP setada, deve usar o stub (não tenta conectar)."""
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)

    email_service.send_confirmation_email("teste@example.com", "tokenraw123")

    sent = email_service.last_sent_for("teste@example.com")
    assert sent is not None
    assert "tokenraw123" in sent.body


def test_dispatch_falls_back_to_stub_if_one_env_missing(monkeypatch) -> None:
    """SMTP_HOST setada mas faltam outras → stub (não tenta envio incompleto)."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    for k in ("SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)

    email_service.send_reset_email("teste@example.com", "resettoken456")

    sent = email_service.last_sent_for("teste@example.com")
    assert sent is not None


# ─────────────────────────────────────────── SMTP real (mockado)

def test_dispatch_uses_smtp_when_all_envs_present(monkeypatch) -> None:
    """Com todas as envs SMTP setadas, _dispatch_smtp é chamado e o stub
    NÃO armazena nada (buffer fica vazio)."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")

    with patch("app.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        email_service.send_confirmation_email("destino@example.com", "tokenABC")

    # smtplib.SMTP foi instanciado com host/port + timeout
    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user@example.com", "secret")
    mock_server.send_message.assert_called_once()
    # Verifica que o conteúdo tem o token (MIMEText com UTF-8 codifica em
    # base64 por causa dos acentos; decoda antes de comparar)
    sent_msg = mock_server.send_message.call_args[0][0]
    body_decoded = sent_msg.get_payload(decode=True).decode("utf-8")
    assert "tokenABC" in body_decoded

    # Buffer in-memory ficou vazio (não caiu no stub)
    assert email_service.last_sent_for("destino@example.com") is None


def test_dispatch_propagates_smtp_failure(monkeypatch) -> None:
    """Se smtplib levantar (rede caiu, auth errada), a exceção sobe pro
    caller — a endpoint da auth decide se faz rollback ou conta órfã (F1-d)."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")

    with patch("app.email_service.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = ConnectionRefusedError("simulação")
        with pytest.raises(ConnectionRefusedError):
            email_service.send_confirmation_email("destino@example.com", "tok")
