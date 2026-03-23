# Desenvolvimento Local

## Requisitos

- Docker
- Docker Compose
- Node.js e npm, caso voce queira buildar o frontend fora do Docker

## Subir a stack

No PowerShell, a partir da raiz do projeto:

```powershell
.\scripts\start.ps1
```

Esse script instala as dependencias do frontend, gera o build estatico e depois sobe os containers.

## Parar a stack

```powershell
.\scripts\stop.ps1
```

## Endpoints iniciais

- Aplicacao: `http://localhost:8000/`
- Healthcheck: `http://localhost:8000/api/health`
- Exemplo de API: `http://localhost:8000/api/hello`
- Sessao atual: `http://localhost:8000/api/auth/session`
- Login: `POST http://localhost:8000/api/auth/login`
- Logout: `POST http://localhost:8000/api/auth/logout`

## O que esta pronto nesta fase

- Backend FastAPI com ponto de entrada em `backend/app/main.py`
- Frontend React + Vite em `frontend/`
- Build estatico do frontend servido pelo backend em `/`
- Chamada de frontend para a API em `/api/hello`
- Login simples por sessao com credenciais ficticias
- PostgreSQL preparado no `docker-compose.yml` para as proximas etapas

## Observacao

O parser legado continua em `backend/app/main_v9.py` e ainda nao foi integrado ao backend web nesta fase.

## Credenciais do MVP

- Usuario: `user`
- Senha: `password`

## Build local do frontend

Se quiser gerar os assets localmente fora do Docker:

```powershell
cd frontend
npm install
npm run build
```

O build e emitido em `backend/app/static`, que e o diretorio servido pelo FastAPI.
