import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
SESSION_SECRET = os.getenv("SESSION_SECRET", "novo-afi-dev-secret")
AUTH_USERNAME = "user"
AUTH_PASSWORD = "password"


class LoginPayload(BaseModel):
    username: str
    password: str


def get_authenticated_user(request: Request) -> dict[str, str]:
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


def create_app() -> FastAPI:
    app = FastAPI(
        title="Novo AFI",
        version="0.1.0",
        description="Scaffolding inicial do backend web do projeto.",
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

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(INDEX_FILE)

    return app


app = create_app()
