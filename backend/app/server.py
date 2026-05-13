import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .db import get_db, get_session, init_db
from .dependencies import require_contrato
from .email_service import send_confirmation_email, send_reset_email
from .models import Contrato, NfEntry, UploadBatch, UploadFile as UploadFileRecord, User
from .security import (
    MIN_PASSWORD_LENGTH,
    generate_token,
    hash_password,
    is_expired,
    needs_rehash,
    token_expiry,
    verify_password,
    verify_token,
)
from .storage import get_pdf_path
from .normalization import (
    build_business_key,
    compute_sha256,
    normalize_cnpj,
    normalize_nullable_text,
    normalize_text,
    parse_brazilian_date,
    parse_brazilian_decimal,
)
from .parser_adapter import LegacyParserAdapter


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
PARSER_DEBUG_DIR = BASE_DIR / "parser_debug"
UPLOAD_STORAGE_DIR = Path(
    os.getenv("UPLOAD_STORAGE_DIR", str(BASE_DIR.parent / "banco_de_nf"))
).resolve()
SESSION_SECRET = os.getenv("SESSION_SECRET", "recebedor-nfs-dev-secret")
AUTH_USERNAME = "user"
AUTH_PASSWORD = "password"
DEFAULT_PASSWORD_HASH = "mvp-user-password-placeholder"


class LoginPayload(BaseModel):
    # F1 (2026-05-13) — `email` é o caminho principal (novos cadastros).
    # `username` permanece opcional para suportar o legacy seed
    # `user/password` em APP_ENV=development (Decisão F1-e).
    email: str | None = None
    username: str | None = None
    password: str


class RegisterPayload(BaseModel):
    email: str
    password: str


class ConfirmTokenPayload(BaseModel):
    token: str


class EmailOnlyPayload(BaseModel):
    """Para `forgot-password` e `resend-confirmation` — sempre retornam 200,
    independente de o e-mail existir, para não vazar enumeração."""
    email: str


class ResetPasswordPayload(BaseModel):
    token: str
    new_password: str


class ContratoSelectPayload(BaseModel):
    contrato_id: str


def serialize_contrato(c: Contrato) -> dict[str, object]:
    return {
        "id": c.id,
        "numero": c.numero,
        "sigla": c.sigla,
        "uf": c.uf,
        "tranche": c.tranche,
        "tipo_contrato": c.tipo_contrato,
        "valor_contrato": str(c.valor_contrato),
        "valor_cde": str(c.valor_cde),
        "participacao_cde": str(c.participacao_cde),
        "ativo": c.ativo,
    }


class NfEntryResponse(BaseModel):
    id: str
    numero_nf: str | int | float | None
    cnpj: str | int | float | None
    data_emissao: str | int | float | None
    tipo_nota: str | int | float | None
    fornecedor: str | int | float | None
    descricao: str | int | float | None
    ncm: str | int | float | None
    quantidade: str | int | float | None
    preco_unitario: str | int | float | None
    valor_total: str | int | float | None
    contrato: str | int | float | None
    contrato_id: str | None
    upload_file_id: str | None


DbSession = Annotated[Session, Depends(get_db)]


def get_authenticated_user(request: Request) -> dict[str, str]:
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


def serialize_nf_entry(entry: NfEntry) -> dict[str, object]:
    raw_payload = entry.raw_payload or {}

    return {
        "id": entry.id,
        "numero_nf": raw_payload.get("numero_nf", entry.numero_nf),
        "cnpj": raw_payload.get("cnpj", entry.cnpj),
        "data_emissao": raw_payload.get("data_emissao", entry.data_emissao.isoformat()),
        "tipo_nota": raw_payload.get("tipo_nota", entry.tipo_nota),
        "fornecedor": raw_payload.get("fornecedor", entry.fornecedor),
        "descricao": raw_payload.get("descricao", entry.descricao),
        "ncm": raw_payload.get("ncm", entry.ncm),
        "quantidade": raw_payload.get(
            "quant",
            float(entry.quantidade) if entry.quantidade is not None else None,
        ),
        "preco_unitario": raw_payload.get(
            "preco_unitario",
            float(entry.preco_unitario) if entry.preco_unitario is not None else None,
        ),
        "valor_total": raw_payload.get("valor", float(entry.valor_total)),
        "contrato": raw_payload.get("contrato", entry.contrato),
        "contrato_id": entry.contrato_id,
        "upload_file_id": entry.upload_file_id,
    }


def get_or_create_user(session: Session, username: str) -> User:
    user = session.scalar(select(User).where(User.username == username))
    if user is not None:
        return user

    user = User(
        username=username,
        password_hash=DEFAULT_PASSWORD_HASH,
        display_name="Usuario de teste",
    )
    session.add(user)
    session.flush()
    return user


def create_nf_entry(
    session: Session,
    row: dict,
    contrato_id: str | None = None,
    upload_file_id: str | None = None,
) -> NfEntry:
    entry = NfEntry(
        business_key=build_business_key(row),
        numero_nf=normalize_text(row.get("numero_nf")),
        cnpj=normalize_cnpj(row.get("cnpj")),
        data_emissao=parse_brazilian_date(row.get("data_emissao")),
        tipo_nota=normalize_text(row.get("tipo_nota")),
        fornecedor=normalize_nullable_text(row.get("fornecedor")),
        descricao=normalize_text(row.get("descricao")),
        ncm=normalize_nullable_text(row.get("ncm")),
        quantidade=parse_brazilian_decimal(row.get("quant")),
        preco_unitario=parse_brazilian_decimal(row.get("preco_unitario")),
        valor_total=parse_brazilian_decimal(row.get("valor")) or 0,
        contrato=normalize_nullable_text(row.get("contrato")),
        contrato_id=contrato_id,
        upload_file_id=upload_file_id,
        raw_payload=row,
    )
    session.add(entry)
    session.flush()
    return entry


def save_uploaded_pdf(batch_id: str, filename: str, file_bytes: bytes) -> tuple[Path, str]:
    """Salva o PDF em disco com nome UUID4 + extensão original (F4).

    Returna `(path, stored_filename)`. `stored_filename` é o nome em disco,
    persistido em `upload_files.stored_filename` para que o endpoint de
    visualização reconstrua o caminho sem ambiguidade.
    """
    import uuid as _uuid
    batch_dir = UPLOAD_STORAGE_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix or ".pdf"
    stored_filename = f"{_uuid.uuid4()}{ext}"
    target_path = batch_dir / stored_filename
    target_path.write_bytes(file_bytes)
    return target_path, stored_filename


def build_parser_debug_dir(saved_path: Path) -> Path:
    return PARSER_DEBUG_DIR / saved_path.parent.name / saved_path.stem


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # F2 — seed de contratos. Em Docker, base_contratos.json vem via bind mount.
    # Em testes/local sem mount, FileNotFoundError é capturado e o seed é pulado
    # (testes que precisam de contratos populam manualmente via fixture).
    try:
        from .seeds.seed_contratos import seed_contratos
        with get_session() as db:
            total = seed_contratos(db)
            print(f"[seed] {total} contratos seedados")
    except FileNotFoundError as exc:
        print(f"[seed] base_contratos.json ausente, seed pulado: {exc}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Novo AFI",
        version="0.1.0",
        description="Backend web com autenticacao simples, upload de PDFs e persistencia.",
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=SESSION_SECRET,
        same_site="lax",
        https_only=False,
    )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(payload: LoginPayload, request: Request, db: DbSession) -> dict[str, object]:
        """F1 (2026-05-13) — login por e-mail + bcrypt.

        Compat: em APP_ENV=development, ainda aceita `{username,password}` com
        as credenciais legadas hardcoded (Decisão F1-e). Resposta 401 é
        idêntica para e-mail inexistente E senha errada (não vaza enumeração).
        """
        # Legacy path — somente em dev, somente para o seed hardcoded.
        if (
            payload.username == AUTH_USERNAME
            and payload.password == AUTH_PASSWORD
            and os.getenv("APP_ENV", "development") == "development"
        ):
            user_payload = {
                "username": AUTH_USERNAME,
                "display_name": "Usuario de teste",
            }
            request.session["user"] = user_payload
            return {"ok": True, "user": user_payload}

        # Novo fluxo: e-mail + bcrypt.
        if not payload.email:
            raise HTTPException(401, "E-mail ou senha incorretos.")
        user = db.scalar(select(User).where(User.email == payload.email))
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "E-mail ou senha incorretos.")
        if not user.email_confirmed:
            raise HTTPException(403, "Confirme seu e-mail antes de entrar.")
        # Re-hash transparente se passlib decidir (ex.: migração futura para argon2).
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(payload.password)
            db.commit()
        user_payload = {
            "username": user.username or user.email,
            "display_name": user.display_name,
            "email": user.email,
        }
        request.session["user"] = user_payload
        return {"ok": True, "user": user_payload}

    @app.post("/api/auth/register", status_code=201)
    def register(payload: RegisterPayload, db: DbSession) -> dict[str, object]:
        """F1 — cria usuário com email_confirmed=False + gera token + dispara
        e-mail. 409 se e-mail duplicado. 422 se senha < 10 chars."""
        if len(payload.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                422,
                f"Senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.",
            )
        existing = db.scalar(select(User).where(User.email == payload.email))
        if existing is not None:
            raise HTTPException(409, "E-mail já cadastrado.")

        raw, token_hash = generate_token()
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            email_confirmed=False,
            confirmation_token_hash=token_hash,
            token_expires_at=token_expiry(24),
        )
        db.add(user)
        db.commit()

        # Decisão F1-d: falha de SMTP NÃO faz rollback. Conta órfã fica
        # aguardando; usuário pode reenviar via /resend-confirmation.
        try:
            send_confirmation_email(payload.email, raw)
        except Exception as exc:
            print(f"[auth] falha ao enviar e-mail de confirmação para {payload.email}: {exc}")

        return {"ok": True, "message": "Verifique seu e-mail."}

    @app.get("/api/auth/confirm")
    def confirm_email(token: str, db: DbSession) -> dict[str, object]:
        """F1 — confirma e-mail. 400 se token inválido OU expirado (mesma
        mensagem; não vale distinguir para o atacante).

        Lookup por hash do token (cliente passa raw; backend recalcula hash
        para encontrar o user). `verify_token` faz comparação constant-time
        como dupla checagem.
        """
        import hashlib
        token_h = hashlib.sha256(token.encode("utf-8")).hexdigest()
        user = db.scalar(select(User).where(User.confirmation_token_hash == token_h))
        if user is None or not verify_token(token, user.confirmation_token_hash):
            raise HTTPException(400, "Token inválido ou expirado.")
        if is_expired(user.token_expires_at):
            raise HTTPException(400, "Token inválido ou expirado.")

        user.email_confirmed = True
        user.confirmation_token_hash = None
        user.token_expires_at = None
        db.commit()
        return {"ok": True, "message": "E-mail confirmado."}

    @app.post("/api/auth/resend-confirmation")
    def resend_confirmation(payload: EmailOnlyPayload, db: DbSession) -> dict[str, object]:
        """F1 — sempre 200 (não vaza enumeração). Se usuário existe e não está
        confirmado, gera token novo e reenvia e-mail."""
        user = db.scalar(select(User).where(User.email == payload.email))
        if user is not None and not user.email_confirmed:
            raw, token_hash = generate_token()
            user.confirmation_token_hash = token_hash
            user.token_expires_at = token_expiry(24)
            db.commit()
            try:
                send_confirmation_email(payload.email, raw)
            except Exception as exc:
                print(f"[auth] falha ao reenviar confirmação para {payload.email}: {exc}")
        return {"ok": True, "message": "Se este e-mail estiver cadastrado, enviamos novo link."}

    @app.post("/api/auth/forgot-password")
    def forgot_password(payload: EmailOnlyPayload, db: DbSession) -> dict[str, object]:
        """F1 — sempre 200. Se usuário existe, gera reset_token (1h) e envia
        e-mail. Mensagem é idêntica para e-mail inexistente, para não vazar."""
        user = db.scalar(select(User).where(User.email == payload.email))
        if user is not None:
            raw, token_hash = generate_token()
            user.reset_token_hash = token_hash
            user.reset_expires_at = token_expiry(1)
            db.commit()
            try:
                send_reset_email(payload.email, raw)
            except Exception as exc:
                print(f"[auth] falha ao enviar reset para {payload.email}: {exc}")
        return {"ok": True, "message": "Se este e-mail estiver cadastrado, enviamos um link de redefinição."}

    @app.post("/api/auth/reset-password")
    def reset_password(payload: ResetPasswordPayload, db: DbSession) -> dict[str, object]:
        """F1 — valida reset_token + expiry, atualiza hash, limpa o token."""
        if len(payload.new_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                422,
                f"Senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.",
            )
        import hashlib
        token_h = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
        user = db.scalar(select(User).where(User.reset_token_hash == token_h))
        if user is None or not verify_token(payload.token, user.reset_token_hash):
            raise HTTPException(400, "Token inválido ou expirado.")
        if is_expired(user.reset_expires_at):
            raise HTTPException(400, "Token inválido ou expirado.")

        user.password_hash = hash_password(payload.new_password)
        user.reset_token_hash = None
        user.reset_expires_at = None
        db.commit()
        return {"ok": True, "message": "Senha redefinida."}

    @app.post("/api/auth/logout")
    def logout(request: Request) -> dict[str, bool]:
        request.session.clear()
        return {"ok": True}

    @app.get("/api/auth/session")
    def session_info(request: Request) -> dict[str, object]:
        user = get_authenticated_user(request)
        return {"authenticated": True, "user": user}

    @app.get("/api/hello")
    def hello(request: Request) -> dict[str, str]:
        user = get_authenticated_user(request)
        return {
            "message": "servidor on",
            "app": "novo_afi",
            "layer": "fastapi",
            "username": user["username"],
        }

    @app.get("/api/nf-entries", response_model=list[NfEntryResponse])
    def list_nf_entries(
        request: Request,
        db: DbSession,
        contrato_id: str | None = None,
        q: str | None = None,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        valor_min: Decimal | None = None,
        valor_max: Decimal | None = None,
        tipo_nota: str | None = None,
    ):
        """F3b — filtros opcionais. Sem params, comportamento idêntico ao da F2:
        retorna todas as NFs ordenadas por `created_at DESC` (regressão obrigatória
        para a tabela principal de upload). Frontend da F3b sorta client-side por
        `data_emissao DESC` quando precisar.
        """
        get_authenticated_user(request)
        stmt = select(NfEntry)

        if contrato_id:
            stmt = stmt.where(NfEntry.contrato_id == contrato_id)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(
                NfEntry.numero_nf.ilike(like),
                NfEntry.fornecedor.ilike(like),
                NfEntry.cnpj.ilike(like),
                NfEntry.descricao.ilike(like),
            ))
        if data_inicio:
            stmt = stmt.where(NfEntry.data_emissao >= data_inicio)
        if data_fim:
            stmt = stmt.where(NfEntry.data_emissao <= data_fim)
        if valor_min is not None:
            stmt = stmt.where(NfEntry.valor_total >= valor_min)
        if valor_max is not None:
            stmt = stmt.where(NfEntry.valor_total <= valor_max)
        if tipo_nota:
            stmt = stmt.where(NfEntry.tipo_nota == tipo_nota)

        entries = db.scalars(stmt.order_by(NfEntry.created_at.desc())).all()
        return [serialize_nf_entry(entry) for entry in entries]

    @app.get("/api/upload-batches/{batch_id}")
    def get_upload_batch(batch_id: str, request: Request, db: DbSession) -> dict[str, object]:
        get_authenticated_user(request)
        batch = db.scalar(select(UploadBatch).where(UploadBatch.id == batch_id))
        if batch is None:
            raise HTTPException(status_code=404, detail="Upload batch not found")

        files = db.scalars(
            select(UploadFileRecord)
            .where(UploadFileRecord.upload_batch_id == batch_id)
            .order_by(UploadFileRecord.created_at.asc())
        ).all()

        return {
            "batch_id": batch.id,
            "files": [
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "status": item.status,
                    "status_reason": item.status_reason,
                    "parser_error": item.parser_error,
                    "inserted_count": item.inserted_count,
                    "duplicate_count": item.duplicate_count,
                }
                for item in files
            ],
        }

    @app.get("/api/uploads/files/{upload_file_id}/pdf")
    def get_pdf(
        upload_file_id: str,
        request: Request,
        db: DbSession,
        download: bool = False,
    ):
        """F4 — serve o PDF original. JOIN com upload_batches + users garante
        que só o dono do batch pode acessar. 404 (não 403) para id inexistente
        ou de outro usuário, para não vazar existência."""
        user_data = get_authenticated_user(request)
        uf = db.scalar(
            select(UploadFileRecord)
            .join(UploadBatch, UploadFileRecord.upload_batch_id == UploadBatch.id)
            .join(User, UploadBatch.user_id == User.id)
            .where(UploadFileRecord.id == upload_file_id)
            .where(User.username == user_data["username"])
        )
        if uf is None:
            raise HTTPException(status_code=404, detail="PDF não encontrado.")
        try:
            path = get_pdf_path(uf, UPLOAD_STORAGE_DIR)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="PDF não disponível no disco.")
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=uf.original_filename,
            content_disposition_type=disposition,
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/contratos")
    def list_contratos(
        request: Request,
        db: DbSession,
        numero: str | None = None,
        sigla: str | None = None,
        q: str | None = None,
        uf: str | None = None,
        tranche: str | None = None,
        tipo_contrato: str | None = None,
        com_valor: bool = False,
        incluir_inativos: bool = False,
    ) -> list[dict[str, object]]:
        """Lista contratos com filtros opcionais e contagem de NFs por contrato.

        F3 ✅ — query params `?numero=&sigla=&q=&uf=&tranche=&tipo_contrato=&com_valor=&incluir_inativos=`.
        Defaults `None`/`False` preservam regressão: sem params, comportamento idêntico
        ao usado por ContratoSelector (F2) e dropdown da Notas (F3b).

        Semântica:
        - `q`: busca livre via ILIKE OR sobre `numero` e `sigla` (campo texto único do
          frontend que casa qualquer um dos dois).
        - `numero` / `sigla`: ILIKE individuais (uso fino via API).
        - Demais filtros: igualdade exata, combinam por AND.

        Sempre retorna `nfs_count` (F4 follow-up — LEFT JOIN com `nf_entries.contrato_id`).
        NFs pré-F2 (contrato_id NULL) não entram em nenhuma contagem.
        """
        get_authenticated_user(request)
        stmt = (
            select(Contrato, func.count(NfEntry.id).label("nfs_count"))
            .outerjoin(NfEntry, NfEntry.contrato_id == Contrato.id)
        )
        if not incluir_inativos:
            stmt = stmt.where(Contrato.ativo.is_(True))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(
                Contrato.numero.ilike(like),
                Contrato.sigla.ilike(like),
            ))
        if numero:
            stmt = stmt.where(Contrato.numero.ilike(f"%{numero}%"))
        if sigla:
            stmt = stmt.where(Contrato.sigla.ilike(f"%{sigla}%"))
        if uf:
            stmt = stmt.where(Contrato.uf == uf)
        if tranche:
            stmt = stmt.where(Contrato.tranche == tranche)
        if tipo_contrato:
            stmt = stmt.where(Contrato.tipo_contrato == tipo_contrato)
        if com_valor:
            stmt = stmt.where(Contrato.valor_contrato > 0)

        rows = db.execute(
            stmt.group_by(Contrato.id).order_by(Contrato.numero.asc())
        ).all()
        return [{**serialize_contrato(c), "nfs_count": count} for c, count in rows]

    @app.get("/api/contratos/{contrato_id}/totais")
    def totais_contrato(contrato_id: str, request: Request, db: DbSession) -> dict[str, object]:
        """F6 — totais agregados de NFs por contrato para o card do painel de upload.

        Uma única query agregada filtrando direto por `nf_entries.contrato_id`
        (sem JOIN — F2 fix populou esse FK). NFs pré-F2 (`contrato_id=NULL`) não
        entram em nenhuma soma.

        `pct_*` retorna `null` quando o denominador é 0, evitando divisão por zero.
        Frontend usa isso para renderizar "Valor contratual não definido" em vez de
        barras com 100%/NaN.
        """
        get_authenticated_user(request)
        contrato = db.get(Contrato, contrato_id)
        if contrato is None:
            raise HTTPException(status_code=404, detail="Contrato não encontrado.")

        row = db.execute(
            select(
                func.coalesce(func.sum(NfEntry.valor_total), 0),
                func.count(func.distinct(NfEntry.numero_nf)),
            ).where(NfEntry.contrato_id == contrato_id)
        ).one()
        soma, contagem = row

        def _pct(num: Decimal, den: Decimal) -> float | None:
            if den is None or Decimal(den) == 0:
                return None
            return float(Decimal(num)) / float(Decimal(den))

        return {
            "contrato_id": contrato.id,
            "numero": contrato.numero,
            "valor_contrato": str(contrato.valor_contrato),
            "valor_cde": str(contrato.valor_cde),
            "participacao_cde": str(contrato.participacao_cde),
            "soma_nfs_enviadas": str(soma),
            "pct_enviado_sobre_contrato": _pct(soma, contrato.valor_contrato),
            "pct_enviado_sobre_cde": _pct(soma, contrato.valor_cde),
            "total_nfs_no_banco": contagem,
        }

    @app.get("/api/session/contrato")
    def get_session_contrato(request: Request, db: DbSession) -> dict[str, object]:
        """Retorna o contrato selecionado na sessão atual ou 404 se nenhum.
        Frontend usa no boot pós-login para decidir entre `/contratos` e área logada.
        """
        get_authenticated_user(request)
        contrato_id = request.session.get("contrato_id")
        if not contrato_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhum contrato selecionado.",
            )
        c = db.get(Contrato, contrato_id)
        # Contrato pode ter sido removido ou desativado entre seleção e consulta —
        # 404 (não 400) preserva semântica "não há contrato válido na sessão" e
        # frontend redireciona para `/contratos`. Limpa sessão como side effect.
        if c is None or not c.ativo:
            request.session.pop("contrato_id", None)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contrato não encontrado ou inativo.",
            )
        return serialize_contrato(c)

    @app.post("/api/session/contrato")
    def set_session_contrato(
        payload: ContratoSelectPayload,
        request: Request,
        db: DbSession,
    ) -> dict[str, object]:
        """Persiste contrato selecionado em `request.session["contrato_id"]`.
        Idempotente: chamar 2x com mesmo id é seguro (último ganha).
        Inativo/inexistente → 404 (não 403, para não vazar existência —
        adversarial #21).
        """
        get_authenticated_user(request)
        c = db.get(Contrato, payload.contrato_id)
        if c is None or not c.ativo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contrato não encontrado ou inativo.",
            )
        request.session["contrato_id"] = c.id
        return serialize_contrato(c)

    @app.post("/api/uploads")
    async def upload_pdfs(
        request: Request,
        files: list[UploadFile] = File(...),
        contrato_id: str = Depends(require_contrato),
    ) -> StreamingResponse:
        user_data = get_authenticated_user(request)

        # F5 — limite hard de 550 PDFs por batch. Validação canônica no backend
        # (frontend tem rede de segurança duplicada). Roda APÓS auth e ANTES de
        # qualquer IO/leitura de bytes para não consumir memória com lotes inválidos.
        if len(files) > 550:
            raise HTTPException(
                status_code=422,
                detail=f"Limite de 550 arquivos por lote excedido. Recebido: {len(files)}",
            )

        # F2 — resolver contrato_id (da sessão, via require_contrato) para o numero
        # que o parser_adapter passa via --contrato. Validar ativo aqui também
        # protege contra estado stale (contrato desativado entre seleção e upload).
        with get_session() as db:
            contrato = db.get(Contrato, contrato_id)
            if contrato is None or not contrato.ativo:
                request.session.pop("contrato_id", None)
                raise HTTPException(
                    status_code=400,
                    detail="Contrato selecionado não está mais ativo.",
                )
            contrato_numero = contrato.numero

        # Ler todos os bytes antes de iniciar o stream (await nao funciona dentro do generator)
        file_payloads: list[tuple[str, bytes]] = []
        for upload in files:
            filename = upload.filename or "arquivo.pdf"
            file_bytes = await upload.read()
            file_payloads.append((filename, file_bytes))

        async def generate():
            with get_session() as db:
                try:
                    user = get_or_create_user(db, user_data["username"])
                    # F2 — associa contrato_id ao batch (validado acima).
                    batch = UploadBatch(user_id=user.id, contrato_id=contrato_id)
                    db.add(batch)
                    db.flush()

                    parser = LegacyParserAdapter()

                    for filename, file_bytes in file_payloads:
                        sha256 = compute_sha256(file_bytes)

                        yield _sse({"event": "file_queued", "filename": filename})

                        if not filename.lower().endswith(".pdf"):
                            record = UploadFileRecord(
                                upload_batch_id=batch.id,
                                original_filename=filename,
                                file_sha256=sha256,
                                status="rejeitado",
                                status_reason="Apenas arquivos PDF sao aceitos.",
                                inserted_count=0,
                                duplicate_count=0,
                            )
                            db.add(record)
                            yield _sse({
                                "event": "file_done",
                                "filename": filename,
                                "status": "rejeitado",
                                "status_reason": "Apenas arquivos PDF sao aceitos.",
                                "parser_error": None,
                                "inserted_count": 0,
                                "duplicate_count": 0,
                            })
                            continue

                        saved_path, stored_filename = save_uploaded_pdf(batch.id, filename, file_bytes)
                        debug_dir = build_parser_debug_dir(saved_path)

                        # F4 — record criado cedo com status placeholder "processando"
                        # para que `nf_entries.upload_file_id` possa referenciá-lo via
                        # FK durante o loop de inserção. Status final é setado depois.
                        record = UploadFileRecord(
                            upload_batch_id=batch.id,
                            original_filename=filename,
                            stored_filename=stored_filename,
                            file_sha256=sha256,
                            status="processando",
                            inserted_count=0,
                            duplicate_count=0,
                        )
                        db.add(record)
                        db.flush()

                        yield _sse({"event": "file_saved", "filename": filename})
                        yield _sse({"event": "file_parsing", "filename": filename})

                        try:
                            # Parser roda em thread para nao bloquear o event loop.
                            # F2 — contrato_numero vem do contrato selecionado na sessão.
                            outcome = await asyncio.to_thread(
                                parser.parse_pdf_bytes, filename, file_bytes, debug_dir, contrato_numero
                            )

                            if outcome.status != "processado":
                                record.status = outcome.status
                                record.status_reason = outcome.reason
                                record.parser_error = outcome.error
                                yield _sse({
                                    "event": "file_done",
                                    "filename": filename,
                                    "status": outcome.status,
                                    "status_reason": outcome.reason,
                                    "parser_error": outcome.error,
                                    "inserted_count": 0,
                                    "duplicate_count": 0,
                                })
                                continue

                            inserted_count = 0
                            duplicate_count = 0
                            # Coleta `contrato_id` dos duplicados para enriquecer
                            # a mensagem ao operador. NFs pré-F2 têm contrato_id=None,
                            # contadas separadamente.
                            duplicate_contrato_ids: set[str] = set()
                            duplicates_sem_contrato = 0

                            for row in outcome.rows:
                                business_key = build_business_key(row)
                                existing = db.scalar(select(NfEntry).where(NfEntry.business_key == business_key))
                                if existing is not None:
                                    duplicate_count += 1
                                    if existing.contrato_id:
                                        duplicate_contrato_ids.add(existing.contrato_id)
                                    else:
                                        duplicates_sem_contrato += 1
                                    continue
                                create_nf_entry(db, row, contrato_id=contrato_id, upload_file_id=record.id)
                                inserted_count += 1

                            file_status = "processado" if inserted_count > 0 else "duplicado"
                            status_reason = None
                            if file_status == "duplicado":
                                # Resolve contrato_id -> numero via uma query batched (sem N+1).
                                numeros: list[str] = []
                                if duplicate_contrato_ids:
                                    contratos_dup = db.scalars(
                                        select(Contrato).where(Contrato.id.in_(duplicate_contrato_ids))
                                    ).all()
                                    numeros = sorted({c.numero for c in contratos_dup})
                                if numeros and not duplicates_sem_contrato:
                                    if len(numeros) == 1:
                                        status_reason = f"Já foi arquivado no contrato {numeros[0]}."
                                    else:
                                        status_reason = f"Já foi arquivado nos contratos: {', '.join(numeros)}."
                                elif numeros and duplicates_sem_contrato:
                                    status_reason = f"Já foi arquivado (em {', '.join(numeros)} + outras anteriores à F2)."
                                else:
                                    # Todos duplicados são pré-F2 (contrato_id NULL).
                                    status_reason = "Já existe na base (sem contrato registrado, anterior à F2)."

                            record.status = file_status
                            record.status_reason = status_reason
                            record.inserted_count = inserted_count
                            record.duplicate_count = duplicate_count
                            yield _sse({
                                "event": "file_done",
                                "filename": filename,
                                "status": file_status,
                                "status_reason": status_reason,
                                "parser_error": None,
                                "inserted_count": inserted_count,
                                "duplicate_count": duplicate_count,
                            })

                        except Exception as error:
                            parser_error = str(error)
                            # F4 — record já existe (criado antes do try). Atualiza
                            # em vez de criar um novo para não duplicar a linha.
                            record.status = "erro_parsing"
                            record.status_reason = "Erro ao consolidar o retorno do parser."
                            record.parser_error = parser_error
                            yield _sse({
                                "event": "file_done",
                                "filename": filename,
                                "status": "erro_parsing",
                                "status_reason": "Erro ao consolidar o retorno do parser.",
                                "parser_error": parser_error,
                                "inserted_count": 0,
                                "duplicate_count": 0,
                            })

                    db.commit()
                    yield _sse({"event": "batch_done", "batch_id": batch.id})

                except Exception as error:
                    db.rollback()
                    yield _sse({"event": "error", "message": str(error)})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(INDEX_FILE)

    return app


app = create_app()
