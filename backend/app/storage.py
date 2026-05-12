"""F4 — abstração de path para PDFs persistidos.

`get_pdf_path` é o único ponto de entrada. Resolve o caminho em disco
de um `UploadFile` row a partir de `stored_filename` (gravado pelo upload
desde a migration 0003) ou de heurística para legados pré-F4 que não
casaram no backfill.

Razão de existir: isolar a lógica de path do `server.py` para suportar
migração futura para object storage (S3/MinIO) — Decisão #4 do PLAN.md.
Trocar implementação aqui é suficiente.
"""
from pathlib import Path


def get_pdf_path(upload_file, base_dir: Path) -> Path:
    """Retorna o `Path` em disco para o PDF de um `upload_files` row.

    Preferência: `stored_filename` (F4+). Fallback: original_filename e
    variante com prefixo SHA (legados pré-F4 que escaparam do backfill).
    Levanta `FileNotFoundError` se nenhuma variante existir.
    """
    batch_dir = base_dir / upload_file.upload_batch_id

    if upload_file.stored_filename:
        p = batch_dir / upload_file.stored_filename
        if p.exists():
            return p

    # Fallback heurístico — só para rows pré-F4 onde o backfill da
    # migration 0003 não encontrou o arquivo (renomeado externamente,
    # caractere unicode etc).
    candidates = [batch_dir / upload_file.original_filename]
    if upload_file.file_sha256:
        candidates.append(
            batch_dir / f"{upload_file.file_sha256[:12]}_{upload_file.original_filename}"
        )
    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        f"PDF não encontrado para upload_file {upload_file.id} "
        f"(stored_filename={upload_file.stored_filename!r}, "
        f"original_filename={upload_file.original_filename!r})"
    )
