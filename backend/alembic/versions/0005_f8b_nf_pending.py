"""f8b — tabela nf_pending + 5 colunas obrigatórias de nf_entries NOT NULL

F8b introduz pendência interativa de preenchimento manual quando o parser
não consegue extrair campo obrigatório. Esta migration entrega:

1. Tabela `nf_pending` para registros aguardando preenchimento. Campos:
   - `id` PK UUID, `upload_file_id`/`upload_batch_id` FKs ON DELETE CASCADE
     (se o batch sumir, a pendência some junto), `contrato_id` FK obrigatório.
   - `prefilled_json` / `missing_fields_json` carregam o payload do parser
     (`pending_rows.json` da Fase B1).
   - `status` em {aguardando | resolvido | cancelado | expirado}.
   - `expires_at` = created_at + 30min (Decisão F8b-c). Job de startup
     da Fase B3 varre rows com `status='aguardando' AND expires_at < now()`
     e marca como expirado (recovery cross-reboot).

2. **DELETE direto** (Decisão F8b-f) de rows em `nf_entries` com NULL ou
   string vazia em qualquer das 5 colunas que vão virar NOT NULL. As
   outras 6 colunas do `default_nf_template` (`descricao`, `numero_nf`,
   `tipo_nota`, `data_emissao`, `cnpj`, `valor_total`) já são NOT NULL
   desde o baseline — invariant já garantida em código + DB.

   Colunas afetadas pelo DELETE (5):
   - `ncm` (String 64 → NOT NULL)
   - `quantidade` (Numeric 18,4 → NOT NULL, parser field `quant`)
   - `preco_unitario` (Numeric 18,4 → NOT NULL)
   - `fornecedor` (Text → NOT NULL)
   - `contrato` (String 255 → NOT NULL)

   `quantidade` e `preco_unitario` são Numeric — checa só `IS NULL`
   (strings vazias não se aplicam). As 3 textuais checam `IS NULL OR = ''`.

   Contagem deletada vai pro stdout (`print`) para auditoria. Snapshot
   manual do DB antes de rodar em produção é recomendado (Risco MÉDIO
   no spec). Diagnóstico hoje em dev (2026-05-14): banco local tem ~150
   linhas, indeterminado quantas têm NULL — verificar no log da migration.

Revision ID: 0005_f8b_nf_pending
Revises: 0004_f1_auth_real
Create Date: 2026-05-14
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0005_f8b_nf_pending"
down_revision = "0004_f1_auth_real"
branch_labels = None
depends_on = None


# Colunas de nf_entries que viram NOT NULL nesta migration. As outras 6
# (descricao, numero_nf, tipo_nota, data_emissao, cnpj, valor_total) já
# são NOT NULL desde o baseline.
TEXT_COLS_TO_NOT_NULL = ["ncm", "fornecedor", "contrato"]
NUMERIC_COLS_TO_NOT_NULL = ["quantidade", "preco_unitario"]


def upgrade() -> None:
    # 1. Tabela nf_pending.
    op.create_table(
        "nf_pending",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "upload_file_id",
            sa.String(36),
            sa.ForeignKey("upload_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "upload_batch_id",
            sa.String(36),
            sa.ForeignKey("upload_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contrato_id",
            sa.String(36),
            sa.ForeignKey("contratos.id"),
            nullable=False,
        ),
        sa.Column("prefilled_json", sa.Text(), nullable=False),
        sa.Column("missing_fields_json", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="aguardando",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_nf_pending_status", "nf_pending", ["status"])
    op.create_index("idx_nf_pending_upload_batch", "nf_pending", ["upload_batch_id"])
    op.create_index("idx_nf_pending_expires_at", "nf_pending", ["expires_at"])

    # 2. DELETE rows pré-F8 com NULL/'' nas 5 colunas obrigatórias.
    conn = op.get_bind()
    where_parts = []
    for col in TEXT_COLS_TO_NOT_NULL:
        where_parts.append(f"{col} IS NULL OR {col} = ''")
    for col in NUMERIC_COLS_TO_NOT_NULL:
        where_parts.append(f"{col} IS NULL")
    where_clause = " OR ".join(where_parts)

    result = conn.execute(sa.text(f"DELETE FROM nf_entries WHERE {where_clause}"))
    deleted = result.rowcount if result.rowcount is not None else "?"
    print(
        f"[migration 0005] Deletadas {deleted} rows de nf_entries com NULL/'' "
        f"nas 5 colunas que viraram NOT NULL "
        f"({', '.join(TEXT_COLS_TO_NOT_NULL + NUMERIC_COLS_TO_NOT_NULL)})."
    )

    # 3. SET NOT NULL nas 5 colunas. batch_alter_table garante compat SQLite.
    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.alter_column("ncm", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column("quantidade", existing_type=sa.Numeric(18, 4), nullable=False)
        batch_op.alter_column("preco_unitario", existing_type=sa.Numeric(18, 4), nullable=False)
        batch_op.alter_column("fornecedor", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("contrato", existing_type=sa.String(255), nullable=False)


def downgrade() -> None:
    # 1. Reverte NOT NULL das 5 colunas (não recupera dados deletados — DELETE
    # do upgrade não tem rollback automático; restore exige snapshot externo).
    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.alter_column("contrato", existing_type=sa.String(255), nullable=True)
        batch_op.alter_column("fornecedor", existing_type=sa.Text(), nullable=True)
        batch_op.alter_column("preco_unitario", existing_type=sa.Numeric(18, 4), nullable=True)
        batch_op.alter_column("quantidade", existing_type=sa.Numeric(18, 4), nullable=True)
        batch_op.alter_column("ncm", existing_type=sa.String(64), nullable=True)

    # 2. Drop nf_pending (cascade no schema garante limpeza de FKs).
    op.drop_index("idx_nf_pending_expires_at", table_name="nf_pending")
    op.drop_index("idx_nf_pending_upload_batch", table_name="nf_pending")
    op.drop_index("idx_nf_pending_status", table_name="nf_pending")
    op.drop_table("nf_pending")
