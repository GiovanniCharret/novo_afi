"""Alembic environment.

Lê DATABASE_URL do mesmo lugar que `app/db.py` para evitar duplicação de
configuração. Usa `Base.metadata` como target para que `--autogenerate`
detecte mudanças nos modelos automaticamente.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Adiciona `backend/` ao sys.path para que `from app.db import ...` resolva
# (alembic é invocado de `backend/`, mas `app/` é um pacote irmão de
# `alembic/`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Base, get_database_url  # noqa: E402
from app import models  # noqa: F401, E402  — registra todos os modelos no metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sobrescreve sqlalchemy.url do alembic.ini com o valor real do ambiente.
config.set_main_option("sqlalchemy.url", get_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Roda migrations em modo 'offline' (gera SQL sem conectar)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Roda migrations conectando ao banco real."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
