"""F1 — seed do usuário de desenvolvimento.

Em `APP_ENV=development`, cria automaticamente no boot um usuário pronto
para login direto pela UI, sem precisar passar pelo fluxo de cadastro +
confirmação a cada reset do servidor:

    email='dev@local'  ·  senha='password'  ·  email_confirmed=True

Idempotente — não recria se o usuário já existir. Não roda em produção
(`APP_ENV != "development"`). Decisão F1-e mantida: produção exige
cadastro real para todos os usuários; este seed é só conveniência local.
"""
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password


DEV_USER_EMAIL = "dev@local"
DEV_USER_PASSWORD = "password"


def seed_dev_user(db: Session) -> bool:
    """Cria o usuário de dev se possível. Retorna True se criou,
    False se pulou (env != development OU já existia)."""
    if os.getenv("APP_ENV", "development") != "development":
        return False

    existing = db.scalar(select(User).where(User.email == DEV_USER_EMAIL))
    if existing is not None:
        return False

    user = User(
        email=DEV_USER_EMAIL,
        username=None,  # email é o identificador agora; username é opcional pós-F1
        display_name="Usuário de desenvolvimento",
        password_hash=hash_password(DEV_USER_PASSWORD),
        email_confirmed=True,
    )
    db.add(user)
    db.commit()
    return True
