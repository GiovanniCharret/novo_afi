import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .db import Base


JsonType = JSON().with_variant(JSONB, "postgresql")


class Contrato(Base):
    """F2 — contratos seedados de `base_contratos.json` (~140 entradas).

    `id` é UUID5 determinístico derivado de `numero` (ver
    `backend/app/seeds/seed_contratos.py` em B2). Re-seed mantém IDs estáveis
    entre ambientes/runs.
    """

    __tablename__ = "contratos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    numero: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    sigla: Mapped[str] = mapped_column(String(255), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)
    tranche: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    valor_contrato: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    valor_cde: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    participacao_cde: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0"))
    tipo_contrato: Mapped[str] = mapped_column(String(16), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    # F2 — NULLABLE para preservar batches pré-F2; novos exigem via require_contrato.
    contrato_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("contratos.id"), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NfEntry(Base):
    __tablename__ = "nf_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    numero_nf: Mapped[str] = mapped_column(String(255), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(32), nullable=False)
    data_emissao: Mapped[date] = mapped_column(Date, nullable=False)
    tipo_nota: Mapped[str] = mapped_column(String(64), nullable=False)
    fornecedor: Mapped[str | None] = mapped_column(Text, nullable=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    ncm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    preco_unitario: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    contrato: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # F2 — NULLABLE para preservar entries pré-F2; novos exigem via fluxo de upload.
    contrato_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("contratos.id"), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UploadFile(Base):
    __tablename__ = "upload_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("upload_batches.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
