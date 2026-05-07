"""baseline — schema atual antes de F2

Captura o schema vigente em 2026-05-07 (commit 210d6f4): tabelas users,
upload_batches, upload_files, nf_entries. Equivale ao que `init_db()` /
`Base.metadata.create_all` produz hoje.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


# JSONB no Postgres, JSON no SQLite (mesma estratégia do models.py:13).
JsonType = JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "upload_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "upload_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("upload_batch_id", sa.String(36), sa.ForeignKey("upload_batches.id"), nullable=False),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("status_reason", sa.Text, nullable=True),
        sa.Column("parser_error", sa.Text, nullable=True),
        sa.Column("inserted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "nf_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_key", sa.Text, unique=True, nullable=False),
        sa.Column("numero_nf", sa.String(255), nullable=False),
        sa.Column("cnpj", sa.String(32), nullable=False),
        sa.Column("data_emissao", sa.Date, nullable=False),
        sa.Column("tipo_nota", sa.String(64), nullable=False),
        sa.Column("fornecedor", sa.Text, nullable=True),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("ncm", sa.String(64), nullable=True),
        sa.Column("quantidade", sa.Numeric(18, 4), nullable=True),
        sa.Column("preco_unitario", sa.Numeric(18, 4), nullable=True),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("contrato", sa.String(255), nullable=True),
        sa.Column("raw_payload", JsonType, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("nf_entries")
    op.drop_table("upload_files")
    op.drop_table("upload_batches")
    op.drop_table("users")
