"""F1 — serviço de envio de e-mail.

**B3 (2026-05-13)**: SMTP real via `smtplib` com STARTTLS, controlado pelas
envs `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Se
qualquer uma delas estiver vazia/ausente, **cai automaticamente no stub**
(loga e armazena no buffer in-memory). Isso preserva o comportamento do B2
para dev local sem SMTP configurado e para testes (que jamais setam SMTP).

Em produção com SMTP configurado: envio real. Falha de SMTP **propaga** —
o endpoint da auth tem try/except que loga e segue (Decisão F1-d: conta
órfã). Não há fallback ao stub em produção.

Timeout de 10s no socket SMTP. Sem isso, registro hangs até 30s se o
servidor estiver inacessível.
"""
from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_S = 10
DEFAULT_SMTP_PORT = 587


@dataclass
class SentEmail:
    to: str
    subject: str
    body: str


# F1 B2 — buffer in-memory dos últimos e-mails "enviados" pelo stub.
# Testes acessam via `email_service.last_sent_for(email)`.
_sent: list[SentEmail] = []


def _has_smtp_config() -> bool:
    """True se TODAS as envs SMTP necessárias estão setadas e não-vazias."""
    return all(
        os.getenv(k)
        for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")
    )


def _dispatch_smtp(to: str, subject: str, body: str) -> None:
    """Envio real via Hostinger SMTP (Decisão #1) ou outro provider via env.
    STARTTLS na porta 587 (default; alternativa 465 SSL deve mudar o caminho).
    Levanta exceção se algo falhar — caller (endpoint) loga e segue.
    """
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ["SMTP_FROM"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_S) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def _dispatch_stub(to: str, subject: str, body: str) -> None:
    """Fallback usado em dev sem SMTP e em testes. Armazena no buffer
    in-memory para `last_sent_for(email)` e (opcionalmente) imprime no log."""
    sent = SentEmail(to=to, subject=subject, body=body)
    _sent.append(sent)
    if os.getenv("EMAIL_LOG_TO_STDOUT", "true").lower() == "true":
        print(f"[email_service stub] to={to!r} subject={subject!r}")
        print("--- body ---")
        print(body)
        print("--- end ---")


def _dispatch(to: str, subject: str, body: str) -> None:
    """Despacho: SMTP real se env configurado; stub caso contrário.
    Quem chama (endpoints de auth) já tem try/except para falhas — Decisão F1-d.
    """
    if _has_smtp_config():
        _dispatch_smtp(to, subject, body)
    else:
        _dispatch_stub(to, subject, body)


def _build_link(query_key: str, token: str) -> str:
    """Monta o link absoluto. `PUBLIC_BASE_URL` controla o host; em dev cai
    em http://localhost:8000 (mesma porta que o uvicorn).

    F1 Fase C — links apontam para `/` (rota da SPA) com query string que
    a SPA reconhece e exibe a tela apropriada. Evita criar catch-all no
    backend para servir HTML em paths SPA.
    """
    base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/?{query_key}={token}"


def send_confirmation_email(to: str, raw_token: str) -> None:
    """E-mail com link de confirmação (validade 24h)."""
    link = _build_link("confirm", raw_token)
    body = (
        f"Olá,\n\n"
        f"Recebemos um pedido de cadastro com este e-mail no sistema GFIP de "
        f"Recebimento de Notas Fiscais.\n\n"
        f"Para ativar sua conta, clique no link abaixo (válido por 24 horas):\n\n"
        f"{link}\n\n"
        f"Se você não fez este cadastro, ignore este e-mail.\n"
    )
    _dispatch(to, subject="Confirme seu e-mail — GFIP", body=body)


def send_reset_email(to: str, raw_token: str) -> None:
    """E-mail com link de redefinição de senha (validade 1h)."""
    link = _build_link("reset", raw_token)
    body = (
        f"Olá,\n\n"
        f"Recebemos um pedido de redefinição de senha para este e-mail.\n\n"
        f"Para definir uma nova senha, clique no link abaixo (válido por 1 hora):\n\n"
        f"{link}\n\n"
        f"Se você não fez este pedido, ignore este e-mail — sua senha atual "
        f"continua válida.\n"
    )
    _dispatch(to, subject="Redefinição de senha — GFIP", body=body)


def last_sent_for(email: str) -> SentEmail | None:
    """Helper para testes: retorna o último e-mail "enviado" para `email`,
    ou None. Em B3 (SMTP real), esta função vira no-op em produção e
    fica disponível apenas em testes via fixture."""
    for sent in reversed(_sent):
        if sent.to == email:
            return sent
    return None


def reset_sent_buffer() -> None:
    """Limpa o buffer in-memory (útil em fixtures de teste para isolamento)."""
    _sent.clear()
