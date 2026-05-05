# Repository Guidelines

## Project Structure & Module Organization

This repository contains a FastAPI backend and a React/Vite frontend. Backend source lives in `backend/app/`, with the active parser in `backend/app/main.py`, the web app in `backend/app/server.py`, and integration helpers such as `parser_adapter.py`, `db.py`, and `models.py`. Backend tests are in `backend/tests/`. Frontend code lives in `frontend/src/`, mainly `App.jsx`, `main.jsx`, and `styles.css`; see `frontend/AGENTS.md` for UI-specific constraints. Operational scripts are in `scripts/`, documentation in `docs/`, and planning notes in `planning/`. Static frontend builds are emitted to `backend/app/static/`.

## Build, Test, and Development Commands

- `.\scripts\start.ps1`: installs frontend dependencies, builds the frontend, and starts Docker Compose services.
- `.\scripts\stop.ps1`: stops the local Docker stack.
- `.\scripts\reset.ps1`: stops services, removes PostgreSQL volumes, and clears saved local PDFs.
- `cd frontend; npm install; npm run build`: builds frontend assets into the backend static directory.
- `cd backend; pytest`: runs backend tests. Tests use temporary SQLite databases via fixtures.
- `docker compose up --build -d`: starts the backend and PostgreSQL using `docker-compose.yml`.

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation, snake_case for functions and variables, and clear module names that match their responsibility. Keep FastAPI route logic in `server.py` thin; place parsing, persistence, and normalization behavior in dedicated modules. Frontend uses JavaScript modules with React components in PascalCase and helpers in camelCase. Keep the current SPA structure unless a task explicitly calls for broader componentization. Prefer direct, readable code over new abstractions unless duplication or complexity justifies them.

## Testing Guidelines

Backend tests use `pytest` and FastAPI `TestClient`. Add tests under `backend/tests/` with names like `test_uploads.py` and test functions named `test_<behavior>`. Cover API status codes, persistence behavior, upload flows, and parser edge cases when touched. There is no configured frontend test runner; verify frontend changes with `npm run build` and manual testing against the local app.

## Commit & Pull Request Guidelines

Recent commit messages are short Portuguese summaries, for example `ajustes da versao main` and `mvp final para enviar para o vps`. Keep commits concise and outcome-focused. Pull requests should include a brief description, affected areas (`backend`, `frontend`, `docs`, etc.), test/build commands run, linked issues or planning notes, and screenshots or screen recordings for visible UI changes.

## Security & Configuration Tips

Do not commit real secrets. Local configuration belongs in `.env`; Docker Compose provides development PostgreSQL defaults. MVP credentials documented in `docs/LOCAL_DEV.md` are development-only and valid only with `DEBUG=true`.
