# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sistema web para recebimento e consulta de notas fiscais em PDF. O usuário faz login, envia PDFs em lote, e consulta uma tabela persistida de lancamentos extraidos.

## Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (psycopg3)
- **Frontend**: React + Vite (build estatico servido pelo FastAPI)
- **Parser legado**: `backend/app/main_v9.py` — invocado como subprocess pelo `LegacyParserAdapter`
- **Infra local**: Docker Compose

## Comandos

### Subir/parar o ambiente local

```powershell
.\scripts\start.ps1   # instala deps do frontend, gera build e sobe os containers
.\scripts\stop.ps1
.\scripts\reset.ps1   # derruba, remove volumes do postgres e apaga backend/banco_de_nf
```

### Build do frontend (fora do Docker)

```powershell
cd frontend
npm install
npm run build   # emite os assets em backend/app/static
```

### Testes do backend

```bash
# Rodar todos os testes (a partir de backend/)
cd backend
pytest

# Rodar um único arquivo de teste
pytest tests/test_uploads.py

# Rodar um teste específico
pytest tests/test_uploads.py::test_upload_pdf_success
```

Os testes usam SQLite em memória (via `DATABASE_URL` env) e não dependem de Docker.

## Arquitetura

```
browser
  └── frontend (React, build em backend/app/static)
        └── API FastAPI (backend/app/main.py)
              ├── SessionMiddleware (autenticação por cookie de sessão)
              ├── PostgreSQL via SQLAlchemy (backend/app/db.py + models.py)
              └── LegacyParserAdapter (backend/app/parser_adapter.py)
                    └── subprocess → backend/app/main_v9.py
```

### Fluxo de upload

1. Frontend envia `POST /api/uploads` com lista de arquivos PDF.
2. O backend salva cada PDF em `backend/banco_de_nf/<batch_id>/`.
3. `LegacyParserAdapter.parse_pdf_bytes` invoca `main_v9.py` via subprocess em diretório temporário.
4. O parser gera um `.xlsx` em `output_dfs/` que é lido como DataFrame.
5. Cada linha do DataFrame é inserida em `nf_entries` se a `business_key` for inédita; caso contrário, conta como `duplicado`.
6. O resultado por arquivo (`processado`, `duplicado`, `rejeitado`, `erro_parsing`) é persistido em `upload_files`.

### Deduplicação

A `business_key` é derivada de `numero_nf|cnpj|data_emissao|valor_total|descricao` (ver `backend/app/normalization.py`). A coluna tem constraint `UNIQUE` no banco — a verificação no backend é a primeira linha de defesa; o banco é o reforço.

### Banco de dados

Tabelas principais:

| Tabela | Responsabilidade |
|---|---|
| `users` | Usuários autenticados (MVP: credenciais fixas) |
| `upload_batches` | Agrupamento de um envio em lote por usuário |
| `upload_files` | Resultado por arquivo dentro de um lote |
| `nf_entries` | Lancamentos consolidados — tabela principal consultada pelo frontend |

O schema é criado automaticamente em `lifespan` via `init_db()` (SQLAlchemy `create_all`).

### Credenciais do MVP

- Usuário: `user` / Senha: `password`

## Variáveis de ambiente relevantes

| Variável | Default | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///...` (testes) | URL do banco; em produção usa `postgresql+psycopg://...` |
| `UPLOAD_STORAGE_DIR` | `backend/banco_de_nf` | Diretório onde os PDFs originais são salvos |
| `SESSION_SECRET` | `recebedor-nfs-dev-secret` | Chave do `SessionMiddleware` |

## Regras de desenvolvimento

- Não sobre-engenheirar. Evitar abstrações desnecessárias para o MVP.
- Reaproveitar o parser (`main_v9.py`) em vez de reescrevê-lo.
- A lógica de deduplicação deve viver no backend, não no frontend.
- O banco é a fonte de verdade — a sessão do usuário não é.
- Antes de corrigir um bug, identificar a causa raiz.
- Revisar `docs/PLAN.md` antes de iniciar mudanças relevantes de arquitetura.
