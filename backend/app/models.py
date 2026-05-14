import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, false as sa_false, func
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
    # F1 — username vira nullable: novos cadastros usam email; username
    # persiste só para o seed legado em APP_ENV=development.
    username: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # F1 — campos de auth real (migration 0004).
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false())
    confirmation_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # F8b — 5 colunas viraram NOT NULL na migration 0005. Antes disso rows
    # pré-F8 podiam ter NULL aqui (parser legado tolerava); a migration deleta
    # tais rows e enforce o invariante NfEntry = NF completa.
    fornecedor: Mapped[str] = mapped_column(Text, nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    ncm: Mapped[str] = mapped_column(String(64), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    contrato: Mapped[str] = mapped_column(String(255), nullable=False)
    # F2 — NULLABLE para preservar entries pré-F2; novos exigem via fluxo de upload.
    contrato_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("contratos.id"), nullable=True)
    # F4 — FK para o PDF de origem. Nullable: pré-F4 não tem, ou parser pode
    # devolver linhas sem associar a um arquivo específico (raro).
    upload_file_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("upload_files.id"), nullable=True)
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
    # F4 — nome em disco (UUID4 + extensão para novos uploads). Nullable para
    # preservar rows pré-F4 cujo backfill da migration 0003 não casou.
    stored_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # F8b — enum de status expandido:
    #   processando | processado | duplicado | rejeitado | erro_parsing
    #   aguardando_preenchimento (Fase B3, transitório enquanto modal aberto)
    #   cancelado (operador cancelou o batch — esse PDF descartado)
    #   cancelado_pelo_lote (arquivos restantes da fila após cancel)
    #   rejeitado_pendencia_expirada (timeout 30min sem preenchimento)
    # Sem CHECK constraint — operadores antigos podem ter outros valores;
    # invariante de fluxo é garantido em código.
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NfPending(Base):
    """F8b — NFs aguardando preenchimento manual de campo obrigatório.

    O parser dispara `ParserCampoFaltante`; o adapter (Fase B3) cria uma
    row aqui e o frontend abre o modal. `expires_at = created_at + 30min`
    (Decisão F8b-c). Resolve via POST /api/uploads/pending/{id}/resolve;
    cancel/timeout via POST /api/uploads/pending/{id}/cancel ou job de
    startup que varre status='aguardando' AND expires_at < now().

    `upload_file_id` e `upload_batch_id` são `ON DELETE CASCADE`: se o
    operador deletar o batch (futuro endpoint), a pendência some junto.
    """

    __tablename__ = "nf_pending"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("upload_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    upload_batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("upload_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    contrato_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("contratos.id"),
        nullable=False,
    )
    # JSON serializado como Text (não JsonType) para preservar payload literal
    # vindo do parser sem reinterpretação de tipos pelo SQLAlchemy. Frontend
    # parsea no consumo.
    prefilled_json: Mapped[str] = mapped_column(Text, nullable=False)
    missing_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Enum: aguardando | resolvido | cancelado | expirado
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="aguardando")
    expires_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
