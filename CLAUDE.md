# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Documentation lives in `planning/` and `docs/`:

- `planning/PROJECT_BUILDING.md` — active scope e meta-plan (TODOs, what's next).
- `planning/PLAN.md` — **roadmap das próximas 7 features** (F1 auth real, F2 seleção de contratos, F3 consulta de contratos, F4 visualizar/baixar PDF, F5 limite 550 notas, F6 totalizadores, F7 e-mails) + seção transversal "Migração do Parser" (F8) + 10 Decisões Pendentes (9 resolvidas, 1 deferida em 2026-05-05). Ler antes de iniciar qualquer feature nova. Inclui modelo de execução por fases (Spec → Backend → Frontend → DoD) com checkpoint humano obrigatório entre cada fase.
- `planning/DEFINITION_OF_DONE.md` — checklist transversal de conclusão (testes, schema, build, docs, critérios negativos, aprovação humana). Aplicada na Fase D de toda feature.
- `planning/ADVERSARIAL_REVIEW.md` — revisão adversarial de `planning/` (ambiguidades, lacunas, brechas que permitem violar o espírito das regras). Consultar ao redigir/alterar regras de processo.
- `planning/PENDING_DECISIONS.md` — itens **explicitamente deferidos** para decisão institucional futura (não decisões em aberto neste ciclo).
- `bug_fix/` — artefatos de bugs em investigação (PDFs problemáticos, screenshots, planilhas comparativas). Convencionado em `planning/PROJECT_BUILDING.md`.
- `docs/PARSER_RUNNER.md` — **arquitetura do parser**: `backend/app/leitor_pdf/` (arquivos do projeto de desenvolvimento do parser) + `backend/app/parser_runner.py` (camada de produção). Ler antes de tocar no parser.
- `docs/orientacoes_dev.md` — **instruções para o projeto de dev do parser** (`leitor_de_pdf/`): o que `main.py` e `ocr_reader.py` precisam expor (`ParserCampoFaltante`) para rodar em produção aqui. (`docs/MAIN_PROD_CHANGES.md` é o changelog do modelo antigo — editar `main.py` com marcadores — agora obsoleto.)
- `planning/BEHAVIORAL_GUIDELINES.md` — process/behavior rules; **always apply**.
- `AGENTS.md` (raiz) e `frontend/AGENTS.md` — guidelines gerais e específicas do frontend (estrutura, estilo, commits). Tem sobreposição com este arquivo; em caso de conflito, este `CLAUDE.md` é canônico.

Toda documentação está organizada em `planning/` e `docs/`. Sempre seguir `planning/BEHAVIORAL_GUIDELINES.md`.

## Project Overview

Reformar o Sistema web para recebimento e consulta de notas fiscais em PDF. No código atual, o usuário faz login, envia PDFs em lote, e consulta uma tabela persistida de lancamentos extraidos. 
A nova versão precisa de uma área para seleção de contratos, uma área de consulta de todas as notas enviadas e um painel gerenciador na área de upload de notas que informa, inclusive graficamente, o total de notas salvas no bd contra contra os valores de contrato. O projeto atual também receberá pequenos upgrades de usabilidade.

## Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (psycopg3) — servido em `http://localhost:8000`
- **Frontend**: React 19 + Vite 7 (build estatico servido pelo FastAPI)
- **Parser**: vive em `backend/app/leitor_pdf/` — `main.py`, `ocr_reader.py`, `description_cleaner.py` e o dado `block_cnpj.json`, do projeto de desenvolvimento do parser (repo `leitor_de_pdf`). Os módulos irmãos `cnpj_lookup.py` e `contrato_config.py` ficam em `backend/app/`. **Não receber lógica de produção** — a única interface que o parser expõe para a produção é `_solicitar_campo_humano` levantar `ParserCampoFaltante(campo, prefilled)` (campo faltante; classe definida em `ocr_reader.py`). A adaptação de produção (non-interactive, exit codes 2/3, `pending_rows.json`) vive em `backend/app/parser_runner.py`, que roda o `leitor_pdf/main.py` via `runpy` e é invocado como subprocess pelo `LegacyParserAdapter` (`backend/app/parser_adapter.py`). Exit 2 = campo faltante → pendência interativa (`nf_pending`, endpoints `/resolve`/`/cancel`, modal, recovery cross-reboot — ver "Pendências de preenchimento F8b"). **Ler `docs/PARSER_RUNNER.md` antes de mexer no parser** — reestruturação de 2026-05-19 (Opção A), substitui o modelo antigo de editar `main.py` com marcadores `FASE DEV`/`FASE PROD`.
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
npm run dev     # HMR via Vite (porta 5173) — não substitui o build servido pelo FastAPI
```

O build emite `assets/index-<hash>.js` + `assets/index-<hash>.css` com hash de conteúdo no nome (vite.config.js usa `[name]-[hash]` no rollupOptions). O `index.html` gerado referencia os nomes com hash automaticamente — cada build muda a URL do bundle, então o navegador nunca serve um bundle velho do cache após um deploy. Como o FastAPI serve o build estático em produção/Docker, **alterações em `frontend/src/` só aparecem na app servida pelo backend após `npm run build`**. Para iteração rápida de UI, `npm run dev` sobe o Vite dev server com HMR — chamadas à API precisam apontar para o backend em `localhost:8000` (configurar proxy no `vite.config.js` se ainda não estiver). O backend roda com `--reload`, então mudanças em Python recarregam automaticamente.

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
| `tests/test_nf_entries_filters.py` | F3b — filtros de `GET /api/nf-entries` |
| `tests/test_pdf_endpoint.py` | F4 — serve PDF do disco, isolamento por dono |
| `tests/test_totais_contrato.py` | F6 — agregação `GET /api/contratos/{id}/totais` |
| `tests/test_auth_real.py` | F1 — login/registro/confirmação/reset reais |
| `tests/test_email_service.py` | F1/F7 — envio SMTP + stub in-memory |
| `tests/test_duplicate_reason.py` | dedup — mensagem enriquecida por contrato |
| `tests/test_sha256_dedup.py` | dedup — re-upload byte-idêntico |
| `tests/test_parser_runner.py` | parser_runner — interface (import, exit codes, `--help`, campo faltante) |
| `tests/test_nf_pending_schema.py` | F8b — schema da tabela `nf_pending` |
| `tests/test_pending_endpoints.py` | F8b — endpoints `/resolve` e `/cancel` |
| `tests/test_pending_registry.py` | F8b — registry in-memory de `asyncio.Event` |
| `tests/test_pending_recovery.py` | F8b — job `expire_orphan_pendings` (recovery) |

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
              ├── pending_registry (backend/app/pending_registry.py — Events F8b)
              └── LegacyParserAdapter (backend/app/parser_adapter.py)
                    └── subprocess → parser_runner.py
                          └── runpy → leitor_pdf/main.py (parser, do projeto de dev)
```

### Fluxo de upload

0. (Após F5/F2) `POST /api/uploads` valida que `len(files) <= 550` (caso contrário 422) e que há `contrato_id` na sessão (caso contrário 400).
1. Frontend envia `POST /api/uploads` com lista de arquivos PDF.
2. O backend salva cada PDF em `backend/banco_de_nf/<batch_id>/<stored_filename>`. **Após F4**: `stored_filename` é UUID4 + `.pdf` gerado por `save_uploaded_pdf` (separado de `original_filename`); ambos vão pro `UploadFileRecord`.
3. **Após F4**: `UploadFileRecord` é criado upfront com `status="processando"` e `db.flush()` antes do parser rodar, para que `nf_entries.upload_file_id` (FK) tenha um id válido durante a inserção das linhas. O status final é setado depois.
4. `LegacyParserAdapter.parse_pdf_bytes(filename, content, debug_dir, contrato_numero)` invoca `backend/app/parser_runner.py` via subprocess (timeout 180s) com flags `--non-interactive --contrato N --input-dir X --output-dir Y`. O `parser_runner` roda o `leitor_pdf/main.py` via `runpy` em modo non-interactive (ver `docs/PARSER_RUNNER.md`). Adapter classifica `process.returncode`: 2 = campo faltante (Tipo 1), 3 = erro estrutural (Tipo 2), outros != 0 = falha genérica. Exit 2 vira uma `nf_pending` + evento SSE `file_pending_input` + modal de preenchimento (em vez de `erro_parsing`).
5. O parser gera um `.xlsx` em `output_dfs/` que é lido como DataFrame. **Seleção da planilha** (`LegacyParserAdapter._find_output_spreadsheet`, regressão fixada em 2026-05-22): o parser pode gravar mais de um xlsx em `output_dfs/` quando rodando uma versão de dev com `arquivo_investigado` ativo (dumps de debug com colunas do pdfplumber, não do schema da NF). O adapter prefere o nome canônico `tabela_de_lancamentos_consolidado_*.xlsx` e, em fallback, escolhe a primeira `.xlsx` cujas colunas contenham as chaves do `nf_template` (`_NF_KEY_COLUMNS`) — pegar `glob("*.xlsx")[0]` faz a consolidação falhar com "Data invalida". Ver `docs/PARSER_RUNNER.md`. Os artefatos (`log.json`, `output_dfs/`, `stdout.txt`, `stderr.txt`) são copiados para `backend/app/parser_debug/<batch_id>/<arquivo>/` para diagnóstico.
6. Cada linha do DataFrame é inserida em `nf_entries` se a `business_key` for inédita; caso contrário, conta como `duplicado`. **Após F2/F4**: novas `nf_entries` recebem `contrato_id` (da sessão) e `upload_file_id` (do record criado no passo 3).
7. O resultado por arquivo (`processado`, `duplicado`, `rejeitado`, `erro_parsing`) atualiza o `UploadFileRecord` existente — não cria um novo.

### Deduplicação

A `business_key` é derivada de `numero_nf|cnpj|data_emissao|valor_total|descricao` (ver `backend/app/normalization.py`). A coluna tem constraint `UNIQUE` no banco — a verificação no backend é a primeira linha de defesa; o banco é o reforço.

**Mensagem de duplicidade enriquecida** (2026-05-12): quando o upload detecta duplicidade, `status_reason` informa em qual contrato a NF original foi arquivada. Implementado em `server.py:507-525` — durante o loop de dedup, coleta `existing.contrato_id` dos duplicados num set; ao final, uma query batched resolve os IDs para `numero` e compõe o texto. 4 cenários cobertos em `tests/test_duplicate_reason.py`:

- Todos sob o mesmo contrato → `"Já foi arquivado no contrato ECFS X/YYYY."`
- Espalhados em N contratos → `"Já foi arquivado nos contratos: A, B, ..."`
- Pré-F2 (`contrato_id NULL`) → `"Já existe na base (sem contrato registrado, anterior à F2)."`
- Mistura → `"Já foi arquivado (em A, B + outras anteriores à F2)."`

Frontend não muda: `App.jsx:606` já renderiza `item.status_reason`.

### Banco de dados

Tabelas principais:

| Tabela | Responsabilidade |
|---|---|
| `users` | Usuários autenticados. **F1 ✅** (2026-05-13/14, migration 0004): tem `email VARCHAR(255) UNIQUE NULL`, `email_confirmed BOOLEAN`, `confirmation_token_hash VARCHAR(64)`, `token_expires_at`, `reset_token_hash VARCHAR(64)`, `reset_expires_at`. `username` virou `nullable=True`. Tokens armazenados como `sha256(raw)` — raw só sai pelo e-mail (Decisão F1-c). |
| `upload_batches` | Agrupamento de um envio em lote por usuário. **F2 ✅**: tem `contrato_id FK → contratos.id` (nullable — preserva batches pré-F2; novos exigem via `require_contrato`). Coluna `status` (`processando`/`concluido`/`abandonado`) ainda **não implementada** — planejada. |
| `upload_files` | Resultado por arquivo dentro de um lote. Status: `processando` (transitório, F4+) \| `processado` \| `duplicado` \| `rejeitado` \| `erro_parsing` \| `aguardando_preenchimento` (transitório enquanto o modal F8b está aberto). **F4 ✅**: tem `stored_filename` (TEXT nullable, UUID4 em disco; backfill na migration 0003) ao lado de `original_filename`; `file_sha256` para dedup byte-idêntico. |
| `nf_entries` | Lancamentos consolidados — tabela principal consultada pelo frontend. **F2 ✅**: tem `contrato_id` (FK nullable; populado em uploads pós-F2). **F4 ✅**: tem `upload_file_id` (FK nullable → `upload_files.id`; populado em uploads pós-F4 — pré-F4 fica NULL, ver Decisão F4-d). **F8b ✅**: as 11 colunas de `default_nf_template` são todas `NOT NULL` (migration 0005 deletou rows com NULL/vazio nas 5 que ainda faltavam — Decisão #8 / F8b-f). |
| `contratos` *(F2 ✅)* | Contratos da base, populados via seed do `base_contratos.json` no `lifespan`. ~140 entradas. PK é UUID5 determinístico derivado de `numero` (re-seed mantém IDs estáveis). Coluna `ativo BOOLEAN` permite filtrar sem deletar. |
| `nf_pending` *(F8b ✅, migration 0005)* | NFs com campo obrigatório faltando aguardando preenchimento manual via modal. `id` PK UUID, `upload_file_id`/`upload_batch_id` FKs `ON DELETE CASCADE`, `contrato_id` FK obrigatório, `prefilled_json`/`missing_fields_json` (payload do parser), `status ∈ {aguardando, resolvido, cancelado, expirado}`, `expires_at` = `created_at + 30min` (Decisão F8b-c). |

**Schema management**: Alembic ativo em produção/dev. `scripts/start.ps1` roda `alembic upgrade head` antes de subir o backend (`docker compose run --rm backend alembic upgrade head` — idempotente). Migrations em `backend/alembic/versions/` (`0001_baseline.py`, `0002_f2_contratos.py`, `0003_f4_pdf_paths.py`, `0004_f1_auth_real.py`, `0005_f8b_nf_pending.py`). **Testes não rodam migrations** — `tests/conftest.py` chama `init_db()` (`create_all`) direto sobre SQLite temporário, então qualquer mudança de schema precisa coexistir nas duas trilhas (modelos + nova revision Alembic) ou o teste fica defasado em relação ao banco real.

**Migration 0003 detalhe**: roda backfill agressivo (`os.listdir` em cada batch_dir) para popular `upload_files.stored_filename` em rows pré-F4. Em ambientes sem `UPLOAD_STORAGE_DIR` ou sem o dir físico, a migration apenas cria as colunas e segue (sem erro). Operação é idempotente — re-rodar não duplica.

### Autenticação F1 ✅ (concluída 2026-05-14)

Fluxo real com e-mail + bcrypt + token de confirmação 24h + reset 1h. Decisões #1, #2, #5 + F1-a/b/c/d/e/f.

- **Login pela UI**: `{email, password}` via `POST /api/auth/login`. Exige `email_confirmed=True` → 403 com mensagem orientando. 401 idêntico para email inexistente ou senha errada (não vaza enumeração).
- **Cadastro**: `POST /api/auth/register` cria user com `email_confirmed=False`, token UUID4 hex (32 chars) + `sha256(token)` no DB (Decisão F1-c). E-mail enviado via `email_service.py`. Falha de SMTP **não** faz rollback (Decisão F1-d — conta órfã; tela "Reenviar e-mail" no frontend).
- **Hash de senha**: `passlib[bcrypt]` cost 10 (Decisão #2). `CryptContext` multi-scheme em `backend/app/security.py` permite migração futura para argon2 trocando o `default=`. **Dependency pin importante**: `bcrypt<4.0.0` no `requirements.txt` — passlib 1.7.4 quebra com bcrypt 5.x. Não remover o pin sem atualizar passlib.
- **Política de senha**: ≥10 caracteres, **sem blocklist nem complexidade** (Decisão F1-a — aceita `1234567890` se atender o tamanho; alinhado a OWASP 2024 / NIST SP 800-63B). Truncamento bcrypt em 72 bytes documentado.
- **Tokens**: `uuid.uuid4().hex` (122 bits, Decisão F1-b). Verificação via `secrets.compare_digest` constant-time. Confirmação expira em 24h; reset em 1h. Raw token só existe no e-mail.
- **Dev seed** (`backend/app/seeds/seed_dev_user.py`, F1 follow-up 2026-05-14): em `APP_ENV=development`, cria automaticamente `dev@local` / `password` com `email_confirmed=True` no boot. Idempotente. Hint discreta na UI mostra essas credenciais quando hostname é `localhost`. **Não roda em produção** — Decisão F1-e mantida.
- **Legado** `user`/`password` (hardcoded em `AUTH_USERNAME`/`AUTH_PASSWORD`): aceito **somente via API** em `APP_ENV=development`, para preservar a suíte legada de testes que envia `{username, password}`. UI nova manda `{email, password}` — esse caminho é inalcançável pela tela.

### Seed de dados (F2 ✅)

`base_contratos.json` na raiz do projeto é a fonte de verdade dos contratos (~140 entradas, campos `sigla, cnpj, tranche, uf, valor_contrato, valor_cde, participacao_cde, tipo_contrato` — valores `LPT` ou `MLA`). O `docker-compose.yml:22` faz bind mount read-only de `./base_contratos.json` para `/app/backend/app/base_contratos.json` dentro do container — assim tanto o seed F2 (`seed_contratos.py:23`) quanto o `contrato_config.py` (módulo do parser, em `backend/app/`) leem do mesmo arquivo sem precisar duplicar conteúdo. **Truncar/apagar o arquivo da raiz quebra o startup do FastAPI** (JSONDecodeError no `lifespan`). Seed roda automaticamente no `lifespan` com `INSERT ... ON CONFLICT (numero) DO UPDATE`. Contratos com `valor_contrato = 0` são inseridos normalmente e filtráveis na UI via `?com_valor=true`.

### Storage de PDFs (Decisão #4 + F4 ✅)

PDFs originais salvos em `backend/banco_de_nf/<batch_id>/<stored_filename>` (configurável via `UPLOAD_STORAGE_DIR`). **Sem object storage** nesta fase — Hostinger é semi-produção; migração para S3/MinIO fica adiada até definição de políticas pelo servidor institucional.

**Estrutura pós-F4** (2026-05-12):
- Pasta = `batch_id` (UUID4) — agrupa todos os PDFs de um upload em lote.
- Arquivo = `stored_filename` (UUID4 + `.pdf`) — separado de `original_filename` (gravado no DB) para evitar colisão e dispensar sanitização. Para batches pré-F4, a migration `0003_f4_pdf_paths` fez backfill via `os.listdir` + match com `original_filename` (cobertura 100% dos 339 `upload_files` no momento da migration).
- Resolver: `backend/app/storage.py:get_pdf_path(upload_file, base_dir)` — preferência por `stored_filename`, fallback heurístico para legados que escaparam do backfill.

**Endpoint** `GET /api/uploads/files/{upload_file_id}/pdf?download=` (autenticado). JOIN com `users` filtra por dono do batch — usuário A recebe 404 (não 403) ao tentar acessar PDF de B, para não vazar existência. `Content-Disposition: inline` default; `?download=true` força `attachment`. `X-Content-Type-Options: nosniff`.

**Limitação aceita (Decisão F4-d)**: `nf_entries` pré-F4 não têm `upload_file_id` (a relação NF→arquivo nunca foi armazenada no schema antigo). Botões PDF na aba Notas ficam **desabilitados** para esses registros com tooltip "PDF não disponível (anterior à F4)". Backfill via timestamp foi descartado por ser frágil em batches grandes (existe 1 batch com 126 PDFs no DB onde timestamps quase iguais inviabilizam o match). PDFs continuam em disco — só a navegação direta NF → PDF é que não funciona para legacy. Daqui pra frente, 100% dos uploads novos têm `upload_file_id`.

**Backup operacional** (TODO de ops, fora do escopo das 7 features): rsync semanal de `UPLOAD_STORAGE_DIR` para destino externo.

## Variáveis de ambiente relevantes

| Variável | Default | Descrição |
|---|---|---|
| `APP_ENV` *(F1 ✅)* | `development` | `production` em deploy real. Em `production`, **bloqueia o login legado** `user`/`password` e o seed `dev@local` não roda. |
| `DATABASE_URL` | `sqlite:///...` (testes) | URL do banco; em produção usa `postgresql+psycopg://...` |
| `UPLOAD_STORAGE_DIR` | `backend/banco_de_nf` | Diretório onde os PDFs originais são salvos |
| `SESSION_SECRET` | `recebedor-nfs-dev-secret` | Chave do `SessionMiddleware`. **Obrigatório trocar em produção.** |
| `PUBLIC_BASE_URL` *(F1 ✅)* | `http://localhost:8000` | Base dos links em e-mails (`?confirm=` e `?reset=`). Em produção, **obrigatório** apontar para o domínio real (`https://seu-dominio.com`), senão os links chegam quebrados ao usuário. |
| `SMTP_HOST` *(F1 ✅, F7)* | — | Servidor SMTP (Hostinger inicial — Decisão #1). Se vazio, `email_service` cai no stub (loga + buffer in-memory). |
| `SMTP_PORT` *(F1 ✅, F7)* | `587` | Porta SMTP (STARTTLS; alternativa 465 SSL). |
| `SMTP_USER` *(F1 ✅, F7)* | — | Usuário SMTP (caixa criada no painel Hostinger). |
| `SMTP_PASSWORD` *(F1 ✅, F7)* | — | Senha da caixa SMTP. |
| `SMTP_FROM` *(F1 ✅, F7)* | — | Endereço remetente. Hostinger pode exigir = `SMTP_USER`. |
| `ADMIN_EMAIL` *(F7)* | — | Destinatário dos alertas de erro tipo 2 do parser (Decisão #8). |
| `OPENROUTER_API_KEY` *(parser_IA — DESATIVADO)* | — | Chave OpenRouter para `description_cleaner`. Chamada está comentada em `backend/app/leitor_pdf/main.py` — variável não é lida hoje. |
| `OPENROUTER_MODEL` *(parser_IA — DESATIVADO)* | `openai/gpt-oss-120b` | Modelo via OpenRouter. Idem acima. |
| `DEBUG` | `false` | Legado pré-F1 — foi substituído por `APP_ENV` para distinguir dev/prod. Mantido por compat com scripts antigos, mas não usado pelo backend hoje. |

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
| `file_pending_input` *(F8b ✅)* | `nf_pending_id, prefilled_fields, missing_fields, original_filename` | Parser detectou NF com campo obrigatório faltando — frontend abre modal. **Bloqueia o batch** até `POST /api/uploads/pending/{id}/resolve` ou `/cancel`. |
| `batch_done` | `batch_id` | Todos os arquivos do lote concluídos (incluindo pendências resolvidas) |
| `error` | `message` | Falha geral antes de qualquer arquivo |

**Por que `get_session()` em vez de `Depends(get_db)`**: o FastAPI fecha sessões de `Depends` quando o objeto de resposta é criado, antes de o stream ser consumido. O `get_session()` (context manager manual em `db.py`) mantém a sessão aberta durante todo o `generate()`.

**Por que `asyncio.to_thread`**: `subprocess.run` com `capture_output=True` pode bloquear até 180s. Rodar em thread pool libera o event loop para enviar os eventos SSE entre arquivos.

### Pendências de preenchimento F8b ✅

Quando o parser sai com exit 2 (`ParserCampoFaltante`), o backend cria uma row `nf_pending` (`status='aguardando'`, `expires_at` = +30min) e o generator SSE emite `file_pending_input`, **bloqueando o batch**. O generator então aguarda um `asyncio.Event` registrado em `backend/app/pending_registry.py` — registry **in-memory** porque o Event sincroniza duas tasks do mesmo processo (generator awaiting + endpoint resolve/cancel acordando). O frontend resolve a pendência via `POST /api/uploads/pending/{id}/resolve` (preenche os campos faltantes → insere a `nf_entry`) ou `/cancel` (descarta). Ambos setam o Event, liberando o generator.

**Recovery cross-reboot**: se o processo cai com pendências abertas, o Event some mas a row `nf_pending` permanece no DB. O job `expire_orphan_pendings` roda no `lifespan` do FastAPI e marca rows `aguardando` com `expires_at < now()` como `expirado`. Mono-réplica hoje — o registry in-memory vira insuficiente em multi-processo (documentado no docstring do módulo).

## API — endpoints relevantes

| Endpoint | Notas |
|---|---|
| `GET /api/contratos` | F3 ✅: query params `?q&numero&sigla&uf&tranche&tipo_contrato&com_valor&incluir_inativos`. Defaults `None`/`False` preservam regressão (ContratoSelector F2 e dropdown da Notas F3b). `q` faz `ILIKE` em `numero OR sigla`. `numero`/`sigla` são ILIKE individuais. Demais filtros = igualdade exata combinada por AND. Sempre retorna `nfs_count` (F4 follow-up) e `ativo` (F3-c — usado pelo frontend para desabilitar clique em inativos). |
| `GET /api/session/contrato` / `POST /api/session/contrato` | F2 — leitura/escrita do contrato ativo na sessão. 404 para inativo/inexistente. |
| `POST /api/uploads` | SSE de upload em lote. F2 ✅ exige contrato. F5 ✅ limite 550. F4 ✅ retorna `stored_filename` no record. |
| `GET /api/nf-entries` | F3b ✅: query params `?contrato_id&q&data_inicio&data_fim&valor_min&valor_max&tipo_nota`. Defaults `None` preservam regressão (tabela_persistida da Upload). `q` faz `ILIKE` em `numero_nf | fornecedor | cnpj | descricao` via `OR`. Payload inclui `contrato_id` e `upload_file_id` (F4 ✅). |
| `GET /api/uploads/files/{id}/pdf?download=` | F4 ✅: serve PDF do disco. JOIN com `users` filtra por dono — outro usuário recebe 404 (não 403). `Content-Disposition: inline` default. |
| `GET /api/contratos/{id}/totais` | F6 ✅: agregação por contrato (`SUM(valor_total)` + `COUNT(DISTINCT numero_nf)` em `nf_entries.contrato_id`). Retorna `soma_nfs_enviadas`, `total_nfs_no_banco`, `pct_enviado_sobre_contrato`, `pct_enviado_sobre_cde`. Helper `_pct` retorna `null` quando denominador é 0 (frontend renderiza empty state em vez de NaN). |
| `POST /api/uploads/pending/{id}/resolve` | F8b ✅: recebe os campos faltantes de uma `nf_pending`, insere a `nf_entry` e libera o generator SSE bloqueado (seta o `asyncio.Event`). |
| `POST /api/uploads/pending/{id}/cancel` | F8b ✅: descarta a `nf_pending` (`status='cancelado'`) e libera o generator SSE. |
| `POST /api/auth/register` | F1 ✅: cria user com `email_confirmed=False` + token UUID4 hex + e-mail. 409 se email duplicado, 422 se senha < 10 chars. |
| `GET /api/auth/confirm?token=...` | F1 ✅: confirma e-mail via `sha256(token)` + check de expiry (24h). 400 inválido/expirado (mesma mensagem — não vaza). |
| `POST /api/auth/login` | F1 ✅ refeito: `{email, password}`. 401 idêntico para email inexistente e senha errada. 403 se `email_confirmed=False`. Compat: `{username:"user",password:"password"}` continua em `APP_ENV=development` (Decisão F1-e). |
| `POST /api/auth/forgot-password` | F1 ✅: sempre 200 (não vaza enumeração). Se email existe, gera reset_token (1h) e envia e-mail. |
| `POST /api/auth/reset-password` | F1 ✅: `{token, new_password}`. Valida hash + expiry, atualiza senha, limpa token. |
| `POST /api/auth/resend-confirmation` | F1 ✅: sempre 200; regenera token e reenvia e-mail. Usado pela tela "Verifique seu e-mail" pós-registro (Decisão F1-d — falha SMTP não rola back o user). |

## Regras de validação de upload

- **Limite hard de 550 PDFs por batch** (F5): validado no backend no início do endpoint, antes de qualquer IO. Retorna `HTTP 422` se excedido. O frontend também avisa ao selecionar mais de 550 arquivos, mas a validação canônica é a do backend.
- **Contrato obrigatório** (F2 ✅, Decisão #9): `POST /api/uploads` exige `contrato_id` na sessão. Sem contrato → `HTTP 400 {"detail": "Nenhum contrato selecionado."}`. Implementado via dependency centralizada `require_contrato(request)` em `backend/app/dependencies.py`. Frontend chama `GET /api/session/contrato` no boot pós-login; se 404, redireciona para `/contratos`. O 400 do upload é rede de segurança, não fluxo principal.
- **Validação de magic bytes (`%PDF-`)**: deferida (Decisão #10). Virá com a próxima versão do `main.py` (refactor do `description_cleaner`). Hoje, arquivo com extensão `.pdf` mas conteúdo inválido cai em `erro_parsing` após tentativa do parser.

## Frontend

O frontend é uma SPA cujo núcleo ainda é monolítico: upload, tabela_persistida, status badges e SSE consumer vivem em `frontend/src/App.jsx`. Componentes extraídos ficam em `frontend/src/components/`:

- `AuthScreen.jsx` *(F1, 2026-05-13/14)* — state machine com 7 views: `login`, `register`, `confirm-needed`, `confirm-result`, `forgot`, `forgot-sent`, `reset`. Detecta `?confirm=X` e `?reset=X` na URL no mount e roteia. `history.replaceState` limpa params após uso. Hint discreta em localhost mostra credenciais do dev seed (`dev@local`/`password`).
- `ContratoSelector.jsx` *(F2)* — tela intermediária de seleção de contrato pós-login. Refatorado para 2 níveis (Estado → Contrato) em 2026-05-11.
- `NfsBrowser.jsx` *(F3b)* — aba "Notas" para consulta filtrada de NFs por contrato, com dropdown, filtros (busca livre, data, valor, tipo), tabela e footer com soma BRL. Inclui coluna PDF com botões 👁/⬇ (F4) — disabled para NFs pré-F4 sem `upload_file_id`.
- `ContratosBrowser.jsx` *(F3, 2026-05-13)* — aba "Contratos", browser da base estática. Filtros: busca livre `q`, selects de UF/Tipo/Tranche (derivados do payload no mount), toggles "apenas com valor definido" e "incluir inativos". **Clique em linha dispara `POST /api/session/contrato` + leva para Upload** (Decisão F3-c revisada em 2026-05-13). Linhas inativas têm cursor `not-allowed`.
- `TotalizadoresCard.jsx` *(F6, 2026-05-13)* — strip compacto horizontal (não card) que aparece entre filter bar e tabela na aba Notas. Grid 3 colunas: contagem de NFs distintas + barra `vs. contrato` + barra `vs. CDE` (com `(Z% do contrato)` na meta line). Tom discreto — não compete por atenção. Empty state inline quando `valor_contrato = 0`.

Funções utilitárias em `frontend/src/lib/`:

- `exportExcel.js` — duas variantes: `exportEntriesCompletas` (11 colunas, usado pela tabela_persistida da Upload) e `exportNfsResumo` (7 colunas, usado pela aba Notas).
- `describeContrato.js` *(2026-05-13)* — formato canônico `SIGLA · Xª Tranche · LPT (ECFS 123/2024)`. Usado pelo topbar (label do contrato ativo), dropdown da Notas e tooltip do ContratosBrowser.
- `ufNomes.js` *(2026-05-13)* — mapa UF → nome completo + constantes `SEM_UF_KEY`/`SEM_UF_NOME`. Usado pelo ContratoSelector e ContratosBrowser.
- `parseBR.js` *(2026-05-13, F6)* — converte string BR (`"1.234,56"`) para Number. Reuso entre NfsBrowser (soma do footer da tabela) e App.jsx (footer do Anexo I).

App.jsx tem state `currentView ∈ {"upload","notas","contratos"}` que comuta entre as três telas via 3 links no topbar (não há menu de tabs — removido em 2026-05-12 por poluição visual). Contrato pode ser trocado **sem logout** clicando numa linha do ContratosBrowser.

### Cache de sessão por contrato (F3-c upgrade, 2026-05-13)

`App.jsx` mantém um Map `contratoSlices: { [contratoId]: { entries: { rows }, upload: { results, batchId, updatedAt } } }`. Cada contrato preserva, dentro da sessão, o último painel de status por arquivo e a lista de entries — trocar de contrato troca o snapshot exibido sem perder a memória do anterior. `handleLogout` zera o Map em definitivo. Operação atual de upload (`uploadProgress` — submitting/phase/progress/progressMessage) e fetch state global de entries (`entriesGlobal.loading/error`) permanecem fora do Map porque referem-se a uma ação em andamento, não a um contrato específico.

O SSE faz **snapshot do `selectedContrato.id`** no início do `handleUploadSubmit` — trocar de contrato no meio do upload não bagunça os slices, os eventos sempre escrevem no slice do contrato onde o upload começou. `refreshEntries(contratoId)` recebe o id como argumento pelo mesmo motivo.

Badge sutil no header do card "Status por arquivo": `Último upload {tempo relativo}` via helper `formatRelativeTime` no topo de `App.jsx`. Sinaliza ao operador que o painel mostra dados de uma jornada anterior na mesma sessão.

A tabela_persistida da Upload filtra por `contrato_id` ativo na sessão (não mostra NFs de outros contratos). Antes do fix de 2026-05-12 ela mostrava todas as NFs do banco — bug visual sutil onde "trocar contrato" parecia persistir dados.

Logo abaixo da tabela_persistida aparece um **rodapé compacto** (`.anexo-footer`) com: `N NFs distintas · Total: R$ X · Y% do contrato · Z% da CDE`. Cálculo client-side via `parseBR(row.valor_total)`. Equivalente discreto do `TotalizadoresCard` (que vive na aba Notas) — Upload prefere informação inline em vez de card próprio. Decisão tomada após primeira versão do TotalizadoresCard ter sido movida para a Notas em 2026-05-13.

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

- **Os arquivos do parser em `backend/app/leitor_pdf/` não recebem lógica de produção.** Toda adaptação de produção vai em `backend/app/parser_runner.py`. A única interface parser↔produção é `_solicitar_campo_humano` levantar `ParserCampoFaltante(campo, prefilled)` — isso é design do parser, mantido também no projeto de dev (`leitor_de_pdf/`). Atualizar o parser = copiar os arquivos novos de dev para `leitor_pdf/` (conferindo que o contrato `ParserCampoFaltante` segue valendo). Ver `docs/PARSER_RUNNER.md`. (O modelo antigo — editar `main.py` com marcadores `FASE DEV`/`FASE PROD` e registrar em `docs/MAIN_PROD_CHANGES.md` — foi substituído por esta estrutura em 2026-05-19, Opção A.)
- `backend/app/main_v9.deprecated.py` é a versão histórica do parser, mantida só como referência (o sufixo `.deprecated.` torna o módulo não-importável).
- A lógica de deduplicação deve viver no backend, não no frontend.
- O banco é a fonte de verdade — a sessão do usuário não é.
- Não usar `position: sticky` em `th` dentro de container `overflow-x: auto` — causa sobreposição entre cabeçalho e linhas. Usar `background` opaco no `th` como alternativa.
- Tabela usa `table-layout: fixed` + `<colgroup>` com larguras explícitas + `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` nas células para evitar quebra de layout.
- Bug fixes em andamento devem ser registrados em `bug_fix/` (diretório acordado em `planning/PROJECT_BUILDING.md`).

## Hook de revisão automática (atualmente inerte)

`.claude/settings.json` registra um hook `Stop` que executa `.claude/hooks/code-reviewer.sh` ao final de cada turno (timeout 600s, statusMessage: "code-reviewer: revisando aderência ao PLAN.md..."). O script chama o CLI externo `codex exec` (LLM da OpenAI) em sandbox read-only para gerar `CODE-REVIEW.md` comparando o código contra `planning/PLAN.md`.

**Status atual**: o hook continua registrado mas é tratado como inerte — não confiar nele. Razões: (a) `codex` pode não estar instalado no host (PowerShell/Windows; o `.sh` depende do shell encontrar `bash`), (b) custo de uma LLM externa rodando a cada turno é proibitivo para uso contínuo. O script sempre retorna `exit 0` para não bloquear o ciclo do Claude, então a única consequência de estar quebrado é não gerar o `CODE-REVIEW.md` — nada falha visivelmente. Se quiser reativar, validar instalação do `codex`, ajustar shebang para shell disponível no host e considerar o custo.
