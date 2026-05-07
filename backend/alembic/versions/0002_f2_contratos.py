"""f2 — tabela contratos + colunas FK em upload_batches e nf_entries

F2 introduz a tabela de contratos (~140 entradas vindas de
base_contratos.json) e as FKs em upload_batches e nf_entries. As FKs são
NULLABLE para preservar batches/entries pré-F2; novos registros pós-F2
exigem FK via validação aplicacional (Depends(require_contrato) em
POST /api/uploads).

Revision ID: 0002_f2_contratos
Revises: 0001_baseline
Create Date: 2026-05-07
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_f2_contratos"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contratos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("numero", sa.String(32), nullable=False),
        sa.Column("sigla", sa.String(255), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("tranche", sa.String(64), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("valor_contrato", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("valor_cde", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("participacao_cde", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("tipo_contrato", sa.String(16), nullable=False),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("numero", name="uq_contratos_numero"),
    )

    # FKs NULLABLE: batches/entries pré-F2 ficam NULL, novos exigem via app layer.
    with op.batch_alter_table("upload_batches") as batch_op:
        batch_op.add_column(sa.Column("contrato_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_upload_batches_contrato_id",
            "contratos",
            ["contrato_id"],
            ["id"],
        )

    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.add_column(sa.Column("contrato_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_nf_entries_contrato_id",
            "contratos",
            ["contrato_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.drop_constraint("fk_nf_entries_contrato_id", type_="foreignkey")
        batch_op.drop_column("contrato_id")

    with op.batch_alter_table("upload_batches") as batch_op:
        batch_op.drop_constraint("fk_upload_batches_contrato_id", type_="foreignkey")
        batch_op.drop_column("contrato_id")

    op.drop_table("contratos")
