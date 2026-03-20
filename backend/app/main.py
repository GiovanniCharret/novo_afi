from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Novo AFI",
        version="0.1.0",
        description="Scaffolding inicial do backend web do projeto.",
    )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/hello")
    def hello() -> dict[str, str]:
        return {
            "message": "hello world",
            "app": "novo_afi",
            "layer": "fastapi",
        }

    @app.get("/")
    def root() -> FileResponse:
        return FileResponse(INDEX_FILE)

    return app


app = create_app()
