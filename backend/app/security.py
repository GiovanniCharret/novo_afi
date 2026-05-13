import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

# Multi-scheme: bcrypt é o default agora; argon2 fica reservado para
# quando a instituição definir o algoritmo institucional. Marcar bcrypt
# como deprecated faz com que `needs_update()` retorne True após a troca,
# e o login re-hashea automaticamente para o novo default.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="bcrypt",
    bcrypt__rounds=10,
    # NOTA: para migração futura para argon2id, trocar `default="argon2"`
    # e adicionar `deprecated=["bcrypt"]`. `needs_update()` então sinaliza
    # re-hash automático no próximo login.
)

MIN_PASSWORD_LENGTH = 10
BCRYPT_MAX_BYTES = 72  # bcrypt trunca silenciosamente acima disso


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def needs_rehash(hashed: str) -> bool:
    return pwd_context.needs_update(hashed)


# ── F1 — token utils (confirmação de e-mail + reset de senha) ───────

def generate_token() -> tuple[str, str]:
    """F1 — gera (raw, hash) para tokens de confirmação e reset.

    Raw vai no e-mail do usuário; hash vai no DB. Decisão F1-b: uuid.uuid4().hex
    (32 chars hex, 122 bits de entropia). Decisão F1-c: armazenar sha256(raw).
    """
    raw = uuid.uuid4().hex
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, token_hash


def verify_token(raw: str, stored_hash: str | None) -> bool:
    """Constant-time. `secrets.compare_digest` evita timing attacks que
    distinguem tokens parcialmente corretos."""
    if not stored_hash or not raw:
        return False
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return secrets.compare_digest(h, stored_hash)


def token_expiry(hours: int) -> datetime:
    """Calcula timestamp de expiração para tokens. F1 usa 24h (confirmação)
    e 1h (reset). Sempre UTC para evitar problemas de timezone."""
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    # Postgres TIMESTAMPTZ chega como datetime com tz; comparação tem que
    # ser entre aware datetimes.
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        # safety net: SQLite/tests podem devolver naive
        return expires_at < now.replace(tzinfo=None)
    return expires_at < now
