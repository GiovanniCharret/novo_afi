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

## Resetar ambiente local

```powershell
.\scripts\reset.ps1
```

Esse script derruba a stack, remove os volumes do PostgreSQL e apaga a pasta local dos PDFs salvos em `backend/banco_de_nf`.

## Endpoints iniciais

- Aplicacao: `http://localhost:8000/`
- Healthcheck: `http://localhost:8000/api/health`
- Exemplo de API: `http://localhost:8000/api/hello`
- Sessao atual: `http://localhost:8000/api/auth/session`
- Login: `POST http://localhost:8000/api/auth/login`
- Logout: `POST http://localhost:8000/api/auth/logout`
- Lancamentos persistidos: `GET http://localhost:8000/api/nf-entries`
- Upload em lote: `POST http://localhost:8000/api/uploads`
- Detalhe de lote: `GET http://localhost:8000/api/upload-batches/{batch_id}`

## O que esta pronto nesta fase

- Backend FastAPI com ponto de entrada em `backend/app/main.py`
- Frontend React + Vite em `frontend/`
- Build estatico do frontend servido pelo backend em `/`
- Login simples por sessao com credenciais ficticias
- Endpoints protegidos para upload, listagem persistida e historico por lote
- Frontend conectado aos endpoints reais de upload e consulta persistida
- Barra de progresso visual durante upload e processamento
- Salvamento dos PDFs originais em `backend/banco_de_nf/<batch_id>/`
- PostgreSQL ativo no `docker-compose.yml`

## Observacao

O parser legado em `backend/app/main_v9.py` ja esta integrado ao backend web por meio de um adaptador interno.
O fluxo atual processa o PDF, persiste as linhas novas no banco e tambem guarda o arquivo original em disco.

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
