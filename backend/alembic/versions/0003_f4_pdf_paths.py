"""f4 — stored_filename em upload_files + upload_file_id em nf_entries

F4 introduz visualização/download do PDF original. Para isso:

1. `upload_files.stored_filename` (TEXT nullable): nome com que o PDF está
   gravado em disco dentro de `UPLOAD_STORAGE_DIR/<batch_id>/`. Separado
   de `original_filename` para suportar arquivos renomeados por
   conflito (`{sha[:12]}_{nome}`) e migrações futuras para object storage.
2. `nf_entries.upload_file_id` (FK nullable → upload_files.id): liga cada
   NF ao arquivo de origem para que o frontend possa abrir o PDF.

Backfill agressivo (Decisão F4-a): durante o upgrade, faz `os.listdir`
em cada batch_dir do `UPLOAD_STORAGE_DIR` e popula `stored_filename`
para todos os `upload_files` pré-F4 que existem em disco. Resolver
em runtime fica simples (sem fallback heurístico no caminho quente).

Se `UPLOAD_STORAGE_DIR` não existir ou um batch_dir sumir, a row fica
com `stored_filename = NULL` e o endpoint retorna 404 — frontend mostra
botão disabled. Não bloqueia a migration.

Revision ID: 0003_f4_pdf_paths
Revises: 0002_f2_contratos
Create Date: 2026-05-12
"""
import os
from pathlib import Path

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_f4_pdf_paths"
down_revision = "0002_f2_contratos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Schema ---
    with op.batch_alter_table("upload_files") as batch_op:
        batch_op.add_column(sa.Column("stored_filename", sa.Text(), nullable=True))

    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.add_column(sa.Column("upload_file_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_nf_entries_upload_file_id",
            "upload_files",
            ["upload_file_id"],
            ["id"],
        )

    # --- Backfill agressivo (F4-a) ---
    # Resolve o storage dir do mesmo jeito que `server.py` faz.
    # Fora de Docker (dev local), a env não vem setada; cai no default.
    storage_dir = Path(
        os.getenv(
            "UPLOAD_STORAGE_DIR",
            str(Path(__file__).resolve().parent.parent.parent / "banco_de_nf"),
        )
    ).resolve()

    conn = op.get_bind()
    if not storage_dir.exists():
        return

    # Para cada batch_dir presente, lista arquivos e tenta casar com
    # `upload_files` daquele batch (heurística: original_filename ou
    # variante com prefixo SHA).
    rows = conn.execute(sa.text(
        "SELECT id, upload_batch_id, original_filename, file_sha256 "
        "FROM upload_files "
        "WHERE stored_filename IS NULL"
    )).fetchall()

    for row in rows:
        batch_dir = storage_dir / row.upload_batch_id
        if not batch_dir.exists():
            continue
        files_on_disk = {p.name for p in batch_dir.iterdir() if p.is_file()}

        # Candidatos em ordem de preferência:
        candidates = [row.original_filename]
        if row.file_sha256:
            candidates.append(f"{row.file_sha256[:12]}_{row.original_filename}")

        match = next((c for c in candidates if c in files_on_disk), None)
        if match is None:
            continue

        conn.execute(
            sa.text("UPDATE upload_files SET stored_filename = :name WHERE id = :id"),
            {"name": match, "id": row.id},
        )


def downgrade() -> None:
    with op.batch_alter_table("nf_entries") as batch_op:
        batch_op.drop_constraint("fk_nf_entries_upload_file_id", type_="foreignkey")
        batch_op.drop_column("upload_file_id")

    with op.batch_alter_table("upload_files") as batch_op:
        batch_op.drop_column("stored_filename")
