# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reformar o Sistema web para recebimento e consulta de notas fiscais em PDF. No código atual, o usuário faz login, envia PDFs em lote, e consulta uma tabela persistida de lancamentos extraidos. 
A nova versão precisa de uma área para seleção de contratos, uma área de consulta de todas as notas enviadas e um painel gerenciador na área de upload de notas que informa, inclusive graficamente, o total de notas salvas no bd contra contra os valores de contrato. O projeto atual também receberá pequenos upgrades de usabilidade.

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

O build emite `assets/app.js` + `assets/app.css` (vite.config.js renomeia `style.css` → `app.css` via rollup). Como o FastAPI serve o build estático, **alterações em `frontend/src/` só aparecem após `npm run build`**. O backend roda com `--reload`, então mudanças em Python recarregam automaticamente.

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
3. `LegacyParserAdapter.parse_pdf_bytes` invoca `main_v9.py` via subprocess em diretório temporário (timeout 180s).
4. O parser gera um `.xlsx` em `output_dfs/` que é lido como DataFrame. Os artefatos (`log.json`, `output_dfs/`, `stdout.txt`, `stderr.txt`) são copiados para `backend/app/parser_debug/<batch_id>/<arquivo>/` para diagnóstico.
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

## Fluxo de upload com SSE

O endpoint `POST /api/uploads` retorna um `StreamingResponse` com `media_type="text/event-stream"`. O frontend consome o stream via `fetch()` + `response.body.getReader()` (o `EventSource` nativo não suporta POST).

**Eventos emitidos pelo backend (wire format: `data: {json}\n\n`)**:

| Evento | Payload | Quando |
|---|---|---|
| `file_queued` | `filename` | Arquivo enfileirado |
| `file_saved` | `filename` | PDF salvo em `banco_de_nf/<batch_id>/` |
| `file_parsing` | `filename` | Parser iniciado |
| `file_done` | `filename, status, inserted_count, duplicate_count, ...` | Parser concluído |
| `batch_done` | `batch_id` | Todos os arquivos do lote concluídos |
| `error` | `message` | Falha geral antes de qualquer arquivo |

**Por que `get_session()` em vez de `Depends(get_db)`**: o FastAPI fecha sessões de `Depends` quando o objeto de resposta é criado, antes de o stream ser consumido. O `get_session()` (context manager manual em `db.py`) mantém a sessão aberta durante todo o `generate()`.

**Por que `asyncio.to_thread`**: `subprocess.run` com `capture_output=True` pode bloquear até 180s. Rodar em thread pool libera o event loop para enviar os eventos SSE entre arquivos.

## Frontend

O frontend é uma SPA monolítica: **todo o app vive em `frontend/src/App.jsx`** (login, upload, tabela, status badges, SSE consumer). Ao procurar um componente, é nesse arquivo.

Documentação relacionada em `docs/`:

- `FRONTEND.md` — paleta, layout, decisões CSS específicas (sticky/table-layout, SSE)
- `DB_MODEL.md` — schema e justificativa da `business_key`
- `LOCAL_DEV.md` — fluxo de subir/parar a stack
- `code_review.md` — revisões anteriores

## Design e paleta visual

A interface segue a identidade visual institucional do governo federal brasileiro, com referência em `www.enbpar.gov.br`. Ver `docs/FRONTEND.md` para detalhes completos.

- Paleta: navy `#0d3558` (topbar/footer) + blue `#1b80c4` (accent) + branco/`#f0f4f8` (conteúdo)
- Fonte: Open Sans (Google Fonts)
- Sem glassmorphism, sem gradientes decorativos, sem `backdrop-filter`
- `border-radius` máximo: 6px (estilo institucional)

## Regras específicas de desenvolvimento

- Reaproveitar o parser (`main_v9.py`) em vez de reescrevê-lo.
- A lógica de deduplicação deve viver no backend, não no frontend.
- O banco é a fonte de verdade — a sessão do usuário não é.
- Não usar `position: sticky` em `th` dentro de container `overflow-x: auto` — causa sobreposição entre cabeçalho e linhas. Usar `background` opaco no `th` como alternativa.
- Tabela usa `table-layout: fixed` + `<colgroup>` com larguras explícitas + `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` nas células para evitar quebra de layout.
