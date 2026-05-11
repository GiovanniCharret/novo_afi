# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Documentation lives in `planning/` and `docs/`:

- `planning/PROJECT_BUILDING.md` — active scope e meta-plan (TODOs, what's next).
- `planning/PLAN.md` — **roadmap das próximas 7 features** (F1 auth real, F2 seleção de contratos, F3 consulta de contratos, F4 visualizar/baixar PDF, F5 limite 550 notas, F6 totalizadores, F7 e-mails) + seção transversal "Migração do Parser" (F8) + 10 Decisões Pendentes (9 resolvidas, 1 deferida em 2026-05-05). Ler antes de iniciar qualquer feature nova. Inclui modelo de execução por fases (Spec → Backend → Frontend → DoD) com checkpoint humano obrigatório entre cada fase.
- `planning/DEFINITION_OF_DONE.md` — checklist transversal de conclusão (testes, schema, build, docs, critérios negativos, aprovação humana). Aplicada na Fase D de toda feature.
- `planning/ADVERSARIAL_REVIEW.md` — revisão adversarial de `planning/` (ambiguidades, lacunas, brechas que permitem violar o espírito das regras). Consultar ao redigir/alterar regras de processo.
- `planning/PENDING_DECISIONS.md` — itens **explicitamente deferidos** para decisão institucional futura (não decisões em aberto neste ciclo).
- `docs/PLAN.md` — phase-by-phase plan do MVP já entregue (Partes 1–7). Histórico, não roadmap.
- `docs/MAIN_PROD_CHANGES.md` — changelog canônico das adaptações de produção sobre `backend/app/main.py` (parser). **Toda mudança em `main.py` é registrada aqui** — ver "Regras específicas de desenvolvimento".
- `planning/BEHAVIORAL_GUIDELINES.md` — process/behavior rules; **always apply**.
- `AGENTS.md` (raiz) e `frontend/AGENTS.md` — guidelines gerais e específicas do frontend (estrutura, estilo, commits). Tem sobreposição com este arquivo; em caso de conflito, este `CLAUDE.md` é canônico.

Toda documentação está organizada em `planning/` e `docs/`. Sempre seguir `planning/BEHAVIORAL_GUIDELINES.md`.

## Project Overview

Reformar o Sistema web para recebimento e consulta de notas fiscais em PDF. No código atual, o usuário faz login, envia PDFs em lote, e consulta uma tabela persistida de lancamentos extraidos. 
A nova versão precisa de uma área para seleção de contratos, uma área de consulta de todas as notas enviadas e um painel gerenciador na área de upload de notas que informa, inclusive graficamente, o total de notas salvas no bd contra contra os valores de contrato. O projeto atual também receberá pequenos upgrades de usabilidade.

## Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (psycopg3) — servido em `http://localhost:8000`
- **Frontend**: React 19 + Vite 7 (build estatico servido pelo FastAPI)
- **Parser ativo (v10)**: `backend/app/main.py` — invocado como subprocess pelo `LegacyParserAdapter` (`backend/app/parser_adapter.py`). Importa módulos irmãos `ocr_reader.py`, `cnpj_lookup.py`, `description_cleaner.py`, `contrato_config.py`. **Após F8a (2026-05-06)** o parser roda non-interactive: bloco `if __name__ == "__main__":` aceita `--contrato NUMERO --input-dir PATH --output-dir PATH --non-interactive`; `_solicitar_campo_humano` levanta `ParserCampoFaltante` em modo non-interactive em vez de `input()`; 17 `raise ValueError` estruturais convertidos para `ParserEstruturaQuebrada(ValueError)`; classificação no adapter via `isinstance` + exit codes (2 = campo faltante, 3 = estrutural). **Pendente em F8b**: tabela `nf_pending` + endpoint `/resolve` + modal — hoje `ParserCampoFaltante` cai em `erro_parsing` em vez de pendência interativa. **Refactor segue regras de preservação** — não apaga funções, mantém versão DEV comentada acima da PROD; toda mudança registrada em `docs/MAIN_PROD_CHANGES.md`.
- **Parser legado (deprecated)**: `backend/app/main_v9.deprecated.py` — versão anterior, mantida só como referência histórica. O sufixo `.deprecated.` torna o módulo não-importável de propósito.
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

# Iterar por padrão de nome / verbose
pytest -k contrato
pytest -v
```

O pytest precisa ser executado a partir de `backend/` — `tests/conftest.py` faz `from app.db import ...` e `from app.server import app`, então `app/` precisa estar no path.

Suítes existentes:

| Arquivo | Cobertura |
|---|---|
| `tests/test_app.py` | endpoints gerais (login, listagem) |
| `tests/test_uploads.py` | `POST /api/uploads` (SSE, deduplicação, debug dir) |
| `tests/test_upload_limit.py` | F5 — limite hard de 550 PDFs |
| `tests/test_upload_with_contrato.py` | F2 — contrato obrigatório na sessão |
| `tests/test_contratos_endpoints.py` | F2 — endpoints de contratos |
| `tests/test_seed_contratos.py` | F2 — seed idempotente do `base_contratos.json` |
| `tests/test_parser_non_interactive.py` | F8a — exit codes 2/3 do parser e exceções tipadas |

Os testes usam SQLite em arquivo temporário (`tmp_path/test.db`) por teste, com `reset_db_state()` + `init_db()` na fixture `client`. A fixture também aponta `UPLOAD_STORAGE_DIR` para um diretório temporário, então testes de upload não poluem `backend/banco_de_nf/`. Não dependem de Docker e **não rodam migrations Alembic** — usam `create_all` direto.

### Backend sem Docker

O `docker-compose.yml` executa `uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload` a partir de `/app/backend`. Para iterar apenas no backend sem subir o Compose:

```powershell
cd backend
uvicorn app.server:app --reload
```

Com `DATABASE_URL` apontando para um Postgres acessível, ou sem a variável definida para cair no SQLite.

## Arquitetura

```
browser
  └── frontend (React, build em backend/app/static)
        └── API FastAPI (backend/app/server.py)
              ├── SessionMiddleware (autenticação por cookie de sessão)
              ├── PostgreSQL via SQLAlchemy (backend/app/db.py + models.py)
              └── LegacyParserAdapter (backend/app/parser_adapter.py)
                    └── subprocess → backend/app/main.py (parser v10)
```

### Fluxo de upload

0. (Após F5/F2) `POST /api/uploads` valida que `len(files) <= 550` (caso contrário 422) e que há `contrato_id` na sessão (caso contrário 400).
1. Frontend envia `POST /api/uploads` com lista de arquivos PDF.
2. O backend salva cada PDF em `backend/banco_de_nf/<batch_id>/`.
3. `LegacyParserAdapter.parse_pdf_bytes(filename, content, debug_dir, contrato_numero)` invoca `backend/app/main.py` via subprocess (timeout 180s) com flags `--non-interactive --contrato N --input-dir X --output-dir Y`. **Após F8a**: `contrato_numero=None` cai no placeholder `DEFAULT_CONTRATO_PRE_F2 = "ECFS 101/2005"` (vira código morto após F2 wirear `request.session["contrato_id"]`). Adapter classifica `process.returncode`: 2 = `ParserCampoFaltante` (Tipo 1), 3 = `ParserEstruturaQuebrada` (Tipo 2), outros != 0 = falha genérica. Em F8b, exit 2 vai virar `nf_pending` + modal em vez de `erro_parsing`.
4. O parser gera um `.xlsx` em `output_dfs/` que é lido como DataFrame. Os artefatos (`log.json`, `output_dfs/`, `stdout.txt`, `stderr.txt`) são copiados para `backend/app/parser_debug/<batch_id>/<arquivo>/` para diagnóstico.
5. Cada linha do DataFrame é inserida em `nf_entries` se a `business_key` for inédita; caso contrário, conta como `duplicado`.
6. O resultado por arquivo (`processado`, `duplicado`, `rejeitado`, `erro_parsing`) é persistido em `upload_files`.

### Deduplicação

A `business_key` é derivada de `numero_nf|cnpj|data_emissao|valor_total|descricao` (ver `backend/app/normalization.py`). A coluna tem constraint `UNIQUE` no banco — a verificação no backend é a primeira linha de defesa; o banco é o reforço.

### Banco de dados

Tabelas principais:

| Tabela | Responsabilidade |
|---|---|
| `users` | Usuários autenticados. **Após F1**: ganha `email UNIQUE NOT NULL`, `email_confirmed`, `confirmation_token`, `token_expires_at`, `reset_token`, `reset_expires_at`. `username` vira `nullable=True` (mantido por compat com seed legado em `DEBUG=true`). |
| `upload_batches` | Agrupamento de um envio em lote por usuário. **F2 ✅**: tem `contrato_id FK → contratos.id` (nullable — preserva batches pré-F2; novos exigem via `require_contrato`). **Após F8**: ganha `status` (`processando` \| `concluido` \| `abandonado`). |
| `upload_files` | Resultado por arquivo dentro de um lote. Status: `processado` \| `duplicado` \| `rejeitado` \| `erro_parsing` \| `aguardando_preenchimento` (novo, após F8). |
| `nf_entries` | Lancamentos consolidados — tabela principal consultada pelo frontend. **Após F2/F4**: ganha `contrato_id` e `upload_file_id`. **Após F8**: as 11 colunas de `default_nf_template` viram `NOT NULL` (Decisão #8). |
| `contratos` *(F2 ✅)* | Contratos da base, populados via seed do `base_contratos.json` no `lifespan`. ~140 entradas. PK é UUID5 determinístico derivado de `numero` (re-seed mantém IDs estáveis). Coluna `ativo BOOLEAN` permite filtrar sem deletar. |
| `nf_pending` *(F8)* | NFs com campo obrigatório faltando aguardando preenchimento manual via modal. Schema completo em `planning/PLAN.md` → "Mudanças Transversais de Schema". |

**Schema management**: Alembic ativo em produção/dev. `scripts/start.ps1` roda `alembic upgrade head` antes de subir o backend (`docker compose run --rm backend alembic upgrade head` — idempotente). Migrations em `backend/alembic/versions/` (`0001_baseline.py`, `0002_f2_contratos.py`). **Testes não rodam migrations** — `tests/conftest.py` chama `init_db()` (`create_all`) direto sobre SQLite temporário, então qualquer mudança de schema precisa coexistir nas duas trilhas (modelos + nova revision Alembic) ou o teste fica defasado em relação ao banco real.

### Credenciais do MVP (legado — será removido em F1)

- Usuário: `user` / Senha: `password` — válido apenas em ambiente com `DEBUG=true` (seed condicional).
- Removidas em produção quando F1 entrar. Novo fluxo (Decisão #2 e #5 resolvidas):
  - `POST /api/auth/register` body `{email, password}` (sem `username`); senha hasheada via `passlib[bcrypt]` cost 10 (configuração multi-scheme em `backend/app/security.py` permite migração futura para argon2id sem mudar código).
  - `POST /api/auth/login` body `{email, password}`. Exige `email_confirmed=True`.
  - `POST /api/auth/forgot-password` + `POST /api/auth/reset-password` com tokens de 1h.
  - Política de senha: ≥10 caracteres, sem regras de complexidade obrigatórias (alinhado a OWASP 2024 / NIST SP 800-63B). Truncamento bcrypt em 72 bytes documentado no endpoint de registro.

### Seed de dados (F2 ✅)

`base_contratos.json` na raiz do projeto é a fonte de verdade dos contratos (~140 entradas, campos `sigla, cnpj, tranche, uf, valor_contrato, valor_cde, participacao_cde, tipo_contrato` — valores `LPT` ou `MLA`). O `docker-compose.yml:22` faz bind mount read-only de `./base_contratos.json` para `/app/backend/app/base_contratos.json` dentro do container — assim tanto o seed F2 (`seed_contratos.py:23`) quanto o `contrato_config.py:16` (parser DEV) leem do mesmo arquivo sem precisar duplicar conteúdo, e a regra de preservação do parser não é violada. **Truncar/apagar o arquivo da raiz quebra o startup do FastAPI** (JSONDecodeError no `lifespan`). Seed roda automaticamente no `lifespan` com `INSERT ... ON CONFLICT (numero) DO UPDATE`. Contratos com `valor_contrato = 0` são inseridos normalmente e filtráveis na UI via `?com_valor=true`.

### Storage de PDFs (Decisão #4)

PDFs originais salvos em `backend/banco_de_nf/<batch_id>/<stored_filename>` (configurável via `UPLOAD_STORAGE_DIR`). **Sem object storage** nesta fase — Hostinger é semi-produção; migração para S3/MinIO fica adiada até definição de políticas pelo servidor institucional.

Em F4, acesso a PDF via função abstrata `get_pdf_path(upload_file)` em `backend/app/storage.py` (a criar). `upload_files` ganha `stored_filename` (UUID no disco) além de `original_filename` para que o caminho seja reconstrutível mesmo movendo o diretório base.

**Backup operacional** (TODO de ops, fora do escopo das 7 features): rsync semanal de `UPLOAD_STORAGE_DIR` para destino externo.

## Variáveis de ambiente relevantes

| Variável | Default | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///...` (testes) | URL do banco; em produção usa `postgresql+psycopg://...` |
| `UPLOAD_STORAGE_DIR` | `backend/banco_de_nf` | Diretório onde os PDFs originais são salvos |
| `SESSION_SECRET` | `recebedor-nfs-dev-secret` | Chave do `SessionMiddleware`. **Obrigatório trocar em produção.** |
| `SMTP_HOST` *(F1/F7)* | `smtp.hostinger.com` | Servidor SMTP (Hostinger inicial — Decisão #1). Se ausente, envio de e-mails é silenciosamente ignorado. |
| `SMTP_PORT` *(F1/F7)* | `587` | Porta SMTP (STARTTLS; alternativa 465 SSL). |
| `SMTP_USER` *(F1/F7)* | — | Usuário SMTP (caixa criada no painel Hostinger). |
| `SMTP_PASSWORD` *(F1/F7)* | — | Senha da caixa SMTP. |
| `SMTP_FROM` *(F1/F7)* | — | Endereço remetente. Hostinger pode exigir = `SMTP_USER`. |
| `ADMIN_EMAIL` *(F7)* | — | Destinatário dos alertas de erro tipo 2 do parser (Decisão #8). |
| `OPENROUTER_API_KEY` *(parser_IA — DESATIVADO)* | — | Chave OpenRouter para `description_cleaner`. Chamada está comentada em `backend/app/main.py:2000` — variável não é lida hoje. |
| `OPENROUTER_MODEL` *(parser_IA — DESATIVADO)* | `openai/gpt-oss-120b` | Modelo via OpenRouter. Idem acima. |
| `DEBUG` | `false` | Se `true`, habilita seed do usuário legado `user`/`password` (proibido em produção). |

**Pré-requisito de produção** (Decisão #1): SPF + DKIM + DMARC configurados no DNS Hostinger antes do primeiro envio. Sem isso, e-mails de confirmação caem em spam.

## Fluxo de upload com SSE

O endpoint `POST /api/uploads` retorna um `StreamingResponse` com `media_type="text/event-stream"`. O frontend consome o stream via `fetch()` + `response.body.getReader()` (o `EventSource` nativo não suporta POST).

**Eventos emitidos pelo backend (wire format: `data: {json}\n\n`)**:

| Evento | Payload | Quando |
|---|---|---|
| `file_queued` | `filename` | Arquivo enfileirado |
| `file_saved` | `filename` | PDF salvo em `banco_de_nf/<batch_id>/` |
| `file_parsing` | `filename` | Parser iniciado |
| `file_done` | `filename, status, inserted_count, duplicate_count, ...` | Parser concluído |
| `file_pending_input` *(F8)* | `nf_pending_id, prefilled_fields, missing_fields, original_filename` | Parser detectou NF com campo obrigatório faltando — frontend abre modal. **Bloqueia o batch** até `POST /api/uploads/pending/{id}/resolve`. |
| `batch_done` | `batch_id` | Todos os arquivos do lote concluídos (incluindo pendências resolvidas) |
| `error` | `message` | Falha geral antes de qualquer arquivo |

**Por que `get_session()` em vez de `Depends(get_db)`**: o FastAPI fecha sessões de `Depends` quando o objeto de resposta é criado, antes de o stream ser consumido. O `get_session()` (context manager manual em `db.py`) mantém a sessão aberta durante todo o `generate()`.

**Por que `asyncio.to_thread`**: `subprocess.run` com `capture_output=True` pode bloquear até 180s. Rodar em thread pool libera o event loop para enviar os eventos SSE entre arquivos.

## Regras de validação de upload

- **Limite hard de 550 PDFs por batch** (F5): validado no backend no início do endpoint, antes de qualquer IO. Retorna `HTTP 422` se excedido. O frontend também avisa ao selecionar mais de 550 arquivos, mas a validação canônica é a do backend.
- **Contrato obrigatório** (F2 ✅, Decisão #9): `POST /api/uploads` exige `contrato_id` na sessão. Sem contrato → `HTTP 400 {"detail": "Nenhum contrato selecionado."}`. Implementado via dependency centralizada `require_contrato(request)` em `backend/app/dependencies.py`. Frontend chama `GET /api/session/contrato` no boot pós-login; se 404, redireciona para `/contratos`. O 400 do upload é rede de segurança, não fluxo principal.
- **Validação de magic bytes (`%PDF-`)**: deferida (Decisão #10). Virá com a próxima versão do `main.py` (refactor do `description_cleaner`). Hoje, arquivo com extensão `.pdf` mas conteúdo inválido cai em `erro_parsing` após tentativa do parser.

## Frontend

O frontend é uma SPA cujo núcleo ainda é monolítico: login, upload, tabela, status badges e SSE consumer vivem em `frontend/src/App.jsx`. Componentes extraídos ficam em `frontend/src/components/` — atualmente `ContratoSelector.jsx` (F2 — tela intermediária de seleção de contrato pós-login). Ao procurar lógica de fluxo principal, comece em `App.jsx`; só os componentes nomeados é que estão isolados.

Documentação relacionada:

- `frontend/AGENTS.md` — stack atual (React 19 / Vite 7), estrutura de `src/` e limitações da fase
- `docs/FRONTEND.md` — paleta, layout, decisões CSS específicas (sticky/table-layout, SSE)
- `docs/DB_MODEL.md` — schema e justificativa da `business_key`
- `docs/LOCAL_DEV.md` — fluxo de subir/parar a stack
- `docs/code_review.md` — revisões anteriores

## Design e paleta visual

A interface segue a identidade visual institucional do governo federal brasileiro, com referência em `www.enbpar.gov.br`. Ver `docs/FRONTEND.md` para detalhes completos.

- Paleta: navy `#0d3558` (topbar/footer) + blue `#1b80c4` (accent) + branco/`#f0f4f8` (conteúdo)
- Fonte: Open Sans (Google Fonts)
- Sem glassmorphism, sem gradientes decorativos, sem `backdrop-filter`
- `border-radius` máximo: 6px (estilo institucional)

## Regras específicas de desenvolvimento

- Reaproveitar o parser (`backend/app/main.py`, v10) em vez de reescrevê-lo. A versão anterior fica em `main_v9.deprecated.py` apenas como referência.
- **Refactor de `backend/app/main.py` segue regras especiais** (preservar versão de desenvolvimento): não apagar funções/variáveis existentes, adicionar versão de produção logo abaixo da DEV com marcador `# FASE PROD`, comentar (não deletar) chamadas substituídas com marcador `# FASE DEV`. Cada mudança deve ser registrada em `docs/MAIN_PROD_CHANGES.md`. Razão: o parser evolui fora deste repositório e novas versões são puxadas periodicamente — mudanças destrutivas quebram o tracking. Detalhes em `planning/PLAN.md` → "Migração do Parser".
- A lógica de deduplicação deve viver no backend, não no frontend.
- O banco é a fonte de verdade — a sessão do usuário não é.
- Não usar `position: sticky` em `th` dentro de container `overflow-x: auto` — causa sobreposição entre cabeçalho e linhas. Usar `background` opaco no `th` como alternativa.
- Tabela usa `table-layout: fixed` + `<colgroup>` com larguras explícitas + `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` nas células para evitar quebra de layout.
- Bug fixes em andamento devem ser registrados em `bug_fix/` (diretório acordado em `planning/PROJECT_BUILDING.md`).

## Hook de revisão automática (atualmente inerte)

`.claude/settings.json` registra um hook `Stop` que executa `.claude/hooks/code-reviewer.sh` ao final de cada turno (timeout 600s, statusMessage: "code-reviewer: revisando aderência ao PLAN.md..."). O script chama o CLI externo `codex exec` (LLM da OpenAI) em sandbox read-only para gerar `CODE-REVIEW.md` comparando o código contra `docs/PLAN.md`.

**Status atual**: o hook continua registrado mas é tratado como inerte — não confiar nele. Razões: (a) `codex` pode não estar instalado no host (PowerShell/Windows; o `.sh` depende do shell encontrar `bash`), (b) custo de uma LLM externa rodando a cada turno é proibitivo para uso contínuo. O script sempre retorna `exit 0` para não bloquear o ciclo do Claude, então a única consequência de estar quebrado é não gerar o `CODE-REVIEW.md` — nada falha visivelmente. Se quiser reativar, validar instalação do `codex`, ajustar shebang para shell disponível no host e considerar o custo.
