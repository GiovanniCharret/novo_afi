import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .db import get_db, get_session, init_db
from .dependencies import require_contrato
from .models import Contrato, NfEntry, UploadBatch, UploadFile as UploadFileRecord, User
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
    username: str
    password: str


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


def create_nf_entry(session: Session, row: dict, contrato_id: str | None = None) -> NfEntry:
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
        raw_payload=row,
    )
    session.add(entry)
    session.flush()
    return entry


def save_uploaded_pdf(batch_id: str, filename: str, file_bytes: bytes, sha256: str) -> Path:
    batch_dir = UPLOAD_STORAGE_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(filename).name or "arquivo.pdf"
    target_path = batch_dir / safe_name
    if target_path.exists():
        target_path = batch_dir / f"{sha256[:12]}_{safe_name}"

    target_path.write_bytes(file_bytes)
    return target_path


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

    @app.get("/api/contratos")
    def list_contratos(request: Request, db: DbSession) -> list[dict[str, object]]:
        """Lista contratos ativos ordenados por número. Autenticação obrigatória."""
        get_authenticated_user(request)
        rows = db.scalars(
            select(Contrato)
            .where(Contrato.ativo.is_(True))
            .order_by(Contrato.numero.asc())
        ).all()
        return [serialize_contrato(c) for c in rows]

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

                        saved_path = save_uploaded_pdf(batch.id, filename, file_bytes, sha256)
                        debug_dir = build_parser_debug_dir(saved_path)

                        yield _sse({"event": "file_saved", "filename": filename})
                        yield _sse({"event": "file_parsing", "filename": filename})

                        try:
                            # Parser roda em thread para nao bloquear o event loop.
                            # F2 — contrato_numero vem do contrato selecionado na sessão.
                            outcome = await asyncio.to_thread(
                                parser.parse_pdf_bytes, filename, file_bytes, debug_dir, contrato_numero
                            )

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

                            for row in outcome.rows:
                                business_key = build_business_key(row)
                                existing = db.scalar(select(NfEntry).where(NfEntry.business_key == business_key))
                                if existing is not None:
                                    duplicate_count += 1
                                    continue
                                create_nf_entry(db, row, contrato_id=contrato_id)
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
                            record = UploadFileRecord(
                                upload_batch_id=batch.id,
                                original_filename=filename,
                                file_sha256=sha256,
                                status="erro_parsing",
                                status_reason="Erro ao consolidar o retorno do parser.",
                                parser_error=parser_error,
                                inserted_count=0,
                                duplicate_count=0,
                            )
                            db.add(record)
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
