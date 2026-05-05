from passlib.context import CryptContext

# Multi-scheme: bcrypt é o default agora; argon2 fica reservado para
# quando a instituição definir o algoritmo institucional. Marcar bcrypt
# como deprecated faz com que `needs_update()` retorne True após a troca,
# e o login re-hashea automaticamente para o novo default.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    default="bcrypt",
    deprecated=["bcrypt"],
    bcrypt__rounds=10,
)

MIN_PASSWORD_LENGTH = 10
BCRYPT_MAX_BYTES = 72  # bcrypt trunca silenciosamente acima disso


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def needs_rehash(hashed: str) -> bool:
    return pwd_context.needs_update(hashed)
