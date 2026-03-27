import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .db import get_db, init_db
from .models import NfEntry, UploadBatch, UploadFile as UploadFileRecord, User
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
SESSION_SECRET = os.getenv("SESSION_SECRET", "novo-afi-dev-secret")
AUTH_USERNAME = "user"
AUTH_PASSWORD = "password"
DEFAULT_PASSWORD_HASH = "mvp-user-password-placeholder"


class LoginPayload(BaseModel):
    username: str
    password: str


class NfEntryResponse(BaseModel):
    id: str
    numero_nf: str
    cnpj: str
    data_emissao: str
    tipo_nota: str
    fornecedor: str | None
    descricao: str
    ncm: str | None
    quantidade: float | None
    preco_unitario: float | None
    valor_total: float
    contrato: str | None


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
    return {
        "id": entry.id,
        "numero_nf": entry.numero_nf,
        "cnpj": entry.cnpj,
        "data_emissao": entry.data_emissao.isoformat(),
        "tipo_nota": entry.tipo_nota,
        "fornecedor": entry.fornecedor,
        "descricao": entry.descricao,
        "ncm": entry.ncm,
        "quantidade": float(entry.quantidade) if entry.quantidade is not None else None,
        "preco_unitario": float(entry.preco_unitario) if entry.preco_unitario is not None else None,
        "valor_total": float(entry.valor_total),
        "contrato": entry.contrato,
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


def create_nf_entry(session: Session, row: dict) -> NfEntry:
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
        raw_payload=row,
    )
    session.add(entry)
    session.flush()
    return entry


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
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
    def login(payload: LoginPayload, request: Request) -> dict[str, object]:
        if payload.username != AUTH_USERNAME or payload.password != AUTH_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        user = {
            "username": AUTH_USERNAME,
            "display_name": "Usuario de teste",
        }
        request.session["user"] = user
        return {"ok": True, "user": user}

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
    def list_nf_entries(request: Request, db: DbSession):
        get_authenticated_user(request)
        entries = db.scalars(select(NfEntry).order_by(NfEntry.created_at.desc())).all()
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

    @app.post("/api/uploads")
    async def upload_pdfs(
        request: Request,
        db: DbSession,
        files: list[UploadFile] = File(...),
    ) -> dict[str, object]:
        user_data = get_authenticated_user(request)
        user = get_or_create_user(db, user_data["username"])

        batch = UploadBatch(user_id=user.id)
        db.add(batch)
        db.flush()

        parser = LegacyParserAdapter()
        results = []

        for upload in files:
            filename = upload.filename or "arquivo.pdf"
            file_bytes = await upload.read()
            sha256 = compute_sha256(file_bytes)

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
                results.append(
                    {
                        "filename": filename,
                        "status": record.status,
                        "status_reason": record.status_reason,
                        "parser_error": None,
                        "inserted_count": 0,
                        "duplicate_count": 0,
                    }
                )
                continue

            outcome = parser.parse_pdf_bytes(filename, file_bytes)

            if outcome.status != "processado":
                record = UploadFileRecord(
                    upload_batch_id=batch.id,
                    original_filename=filename,
                    file_sha256=sha256,
                    status=outcome.status,
                    status_reason=outcome.reason,
                    parser_error=outcome.error,
                    inserted_count=0,
                    duplicate_count=0,
                )
                db.add(record)
                results.append(
                    {
                        "filename": filename,
                        "status": record.status,
                        "status_reason": record.status_reason,
                        "parser_error": record.parser_error,
                        "inserted_count": 0,
                        "duplicate_count": 0,
                    }
                )
                continue

            inserted_count = 0
            duplicate_count = 0

            for row in outcome.rows:
                business_key = build_business_key(row)
                existing = db.scalar(select(NfEntry).where(NfEntry.business_key == business_key))
                if existing is not None:
                    duplicate_count += 1
                    continue

                create_nf_entry(db, row)
                inserted_count += 1

            file_status = "processado" if inserted_count > 0 else "duplicado"
            status_reason = None
            if file_status == "duplicado":
                status_reason = "Todas as linhas extraidas deste arquivo ja existiam na base."

            record = UploadFileRecord(
                upload_batch_id=batch.id,
                original_filename=filename,
                file_sha256=sha256,
                status=file_status,
                status_reason=status_reason,
                inserted_count=inserted_count,
                duplicate_count=duplicate_count,
            )
            db.add(record)
            results.append(
                {
                    "filename": filename,
                    "status": file_status,
                    "status_reason": status_reason,
                    "parser_error": None,
                    "inserted_count": inserted_count,
                    "duplicate_count": duplicate_count,
                }
            )

        db.commit()

        return {"batch_id": batch.id, "files": results}

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(INDEX_FILE)

    return app


app = create_app()
