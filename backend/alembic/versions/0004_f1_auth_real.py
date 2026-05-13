"""f1 — auth real: email + email_confirmed + tokens de confirmação e reset

F1 introduz cadastro real com e-mail. Esta migration:

1. Adiciona em `users`:
   - `email VARCHAR(255) NULL UNIQUE` — identificador de login (não NOT NULL
     para preservar legado em APP_ENV=development; novos cadastros sempre
     têm email).
   - `email_confirmed BOOLEAN NOT NULL DEFAULT FALSE` — gate de login pós-F1.
   - `confirmation_token_hash VARCHAR(64) NULL` — sha256 hex do token de
     confirmação. Raw vive só no e-mail.
   - `token_expires_at TIMESTAMPTZ NULL` — validade do confirmation_token (24h).
   - `reset_token_hash VARCHAR(64) NULL` — sha256 hex do token de reset.
   - `reset_expires_at TIMESTAMPTZ NULL` — validade do reset_token (1h).

2. Altera `username` para NULL (Decisão #5: login passa a ser por email;
   username só persiste para o seed legado em development).

Decisão F1-e (2026-05-13): sem migração dos usuários atuais. Em produção,
todos criam conta nova via fluxo /api/auth/register. Esta migration não
backfilla emails.

Revision ID: 0004_f1_auth_real
Revises: 0003_f4_pdf_paths
Create Date: 2026-05-13
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0004_f1_auth_real"
down_revision = "0003_f4_pdf_paths"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        # username deixa de ser obrigatório; novos cadastros usam email.
        batch_op.alter_column("username", existing_type=sa.String(255), nullable=True)

        # email — UNIQUE NULL. Adicionar como nullable preserva linhas
        # existentes (legado pré-F1). Constraint UNIQUE é instalada
        # depois da coluna estar criada.
        batch_op.add_column(sa.Column("email", sa.String(255), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])

        batch_op.add_column(sa.Column(
            "email_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))

        batch_op.add_column(sa.Column("confirmation_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True))

        batch_op.add_column(sa.Column("reset_token_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("reset_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("reset_expires_at")
        batch_op.drop_column("reset_token_hash")
        batch_op.drop_column("token_expires_at")
        batch_op.drop_column("confirmation_token_hash")
        batch_op.drop_column("email_confirmed")
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("email")

        # Reverter username para NOT NULL exige que todas as linhas
        # tenham username preenchido. Em prod com usuários só-email,
        # downgrade quebraria — mas isso é esperado para reversão F1.
        batch_op.alter_column("username", existing_type=sa.String(255), nullable=False)
