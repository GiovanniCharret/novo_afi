# OBJECTIVE

Estruturar o desenvolvimento via arquitetura de projetos com IA para tornar eficazes os outputs.

## Glossário

a - anulado
f - Revisão Futura
x - concluído
n - Não se aplica
r - Rollback - falhou

## Fases

[x] - Construir pasta planning E criar arquivo PLAN.md
[x] - Escrever no CLAUDE.md que toda a documentação estará em `planning` directory e o key document is PLAN.md
[x] - Criar o hook de revisão por outra IA (Kimi, Codex) e escrever em REVIEW.md

[a] - Criar uma pesquisa do plano equivalente ao texto abaixo:
    - "Realize uma pesquisa abrangente(...) e escreva documentos no diretório de planejamento em XXX_API.md"
    - "Pesquise API. Escreva a documentação com exemplos de código"
    - "Use isso para projetar a API em Python que deve ser usada para XXXX. Documente isso em XXX.md"
    - Por fim, documente a estrutura de código para [OBJETIVO]
[a] - Criar novo arquivo com a estrutura do backend em detalhes, com code snippets mais exemplo, de todas funcionalidades, escreva tudo em XXX_BACKEND.md
[a] - Subplanos dentro do plano para cada grande marco de implementação com certificação de bons testes em cada subplano
[x] - Prepara o Github
[x] - Preparar o gitignore
[x] - Crie a pasta bug_fix
[a] - Usar Skill SDD para planejas as fases e subfases. GSD, feature-dev e superpowers são bons exemplos
[n] - Definir se o projeto usará single ou mult agents
[x] - Adicionar BEHVIORAL_GUIDELINES à pasta do projeto e no claude.
[r] - Após o /init - Leia todo o conteúdo de planning/. Depois, escreva o planning/ADVERSARIAL_REVIEW.md, que testa as falhas e ambiguidades do script: "Aja como um adversário maximamente competente. Sua tarefa é encontrar todas as ambiguidades, lacunas semânticas e formulações suaves neste documento que permiritiram a você seguir tecnicamente a refra enquanto viala seu espírito. Liste cada brecha com o caminho de exploração específico".
[a] - Avaliar o plugin caveman no projeto
[x] - Explicar: `PLAN.md` governa escopo; `CLAUDE.md` governa estilo; `BEHAVIORAL_GUIDELINES.md` governa processo; `outros.md` ; para evitar aconflitos que falham alto. — ver "Hierarquia de documentos" abaixo.
[ ] - Comparar arquitetura atual e clean Architecture
[x] - Criar a seção `estado atual do respositório` com `Estado atual do repositório` e `Próxima tarefa concreta proposta pelo Claude` — ver "Estado atual do repositório" abaixo.
[ ] - sinalizar arquivos da raiz que NÃO SÃO entradas
[a] - Avaliar usar sandbox e WSL2/VSCODE Ubuntu para execução
[a] - Criar e instalar dependências
[x] - Governança de desenvolvimento - Explica critérios de sucesso de cada fase em `definition of done.md` para humanos poderem acompanhar.



---

## Hierarquia de documentos (qual arquivo manda em qual decisão)

Para evitar conflitos entre arquivos de instrução, cada um tem domínio definido:

| Arquivo | Governa | Tipo |
|---|---|---|
| `planning/PLAN.md` | **Escopo**: o que será construído (F1–F8), critérios de sucesso, schema, decisões resolvidas e deferidas | Roadmap |
| `CLAUDE.md` | **Estilo + arquitetura**: como o código se organiza, comandos, env vars, regras específicas (ex.: refactor de `main.py`) | Guia técnico |
| `planning/BEHAVIORAL_GUIDELINES.md` | **Processo**: como pensar antes de codar, simplicidade, mudanças cirúrgicas | Postura |
| `planning/PENDING_DECISIONS.md` | **Decisões deferidas** institucionais (não decisões em aberto) | Lista de espera |
| `planning/PROJECT_BUILDING.md` | **Meta-projeto**: como o projeto está sendo conduzido (este arquivo) | Auto-tracking |
| `docs/MAIN_PROD_CHANGES.md` | **Changelog do parser** (`backend/app/main.py`) | Tracking de adaptações |
| `docs/PLAN.md` | **Histórico**: plano do MVP entregue (Partes 1–7). Não é roadmap. | Histórico |
| `docs/DB_MODEL.md` | **Schema do banco**: schema vigente + planejado | Referência |
| `docs/FRONTEND.md` | **UI/UX**: paleta, componentes, telas planejadas | Referência |
| `docs/LOCAL_DEV.md` | **Onboarding**: como subir/parar/resetar a stack | Operação |
| `frontend/AGENTS.md` | **Frontend stack + limitações da fase** | Frontend overview |

Em caso de conflito explícito: `PLAN.md` > `CLAUDE.md` > demais. `BEHAVIORAL_GUIDELINES.md` é ortogonal — sempre se aplica.

---

## Estado atual do repositório (snapshot 2026-05-14)

### O que já existe e funciona

- Backend FastAPI com upload + persistência + SSE (Partes 1–7 do MVP — `docs/PLAN.md` foi removido em 2026-05-14; histórico em commits).
- Frontend SPA com 3 abas comutadas no topbar: **Upload** (App.jsx, fluxo herdado + rodapé de totais no Anexo I), **Notas** (`components/NfsBrowser.jsx`, F3b + strip de Totais F6) e **Contratos** (`components/ContratosBrowser.jsx`, F3).
- Auth real: cadastro com e-mail, bcrypt, confirmação por token 24h, reset por token 1h (F1). UI via `components/AuthScreen.jsx` com 7 sub-telas.
- Dev seed automático: `dev@local`/`password` criado no boot em `APP_ENV=development` (idempotente). Hint visual em localhost.
- Cache de sessão por contrato: trocar contrato preserva o snapshot do painel de status e da tabela (zerado no logout). Badge "Último upload {relativo}" para sinalizar dados de uma jornada anterior.
- Totais por contrato (`GET /api/contratos/{id}/totais`) — `TotalizadoresCard` strip na Notas + rodapé inline no Anexo I da Upload.
- Parser v10 ✅ non-interactive desde F8a (2026-05-06). Parser DEV preservado conforme regra; PROD lives ao lado com marcadores `# FASE PROD`/`# FASE DEV`.
- Tabela `contratos` ✅ seedada (110 entradas) — F2 (2026-05-11).
- Endpoints F3b ✅: `/api/nf-entries` com filtros (`?contrato_id&q&data_inicio&data_fim&valor_min&valor_max&tipo_nota`), `/api/contratos` com `nfs_count` + filtros F3 (`?q&numero&sigla&uf&tranche&tipo_contrato&com_valor&incluir_inativos`).
- F4 ✅: visualização/download de PDF via `GET /api/uploads/files/{id}/pdf` + coluna PDF na aba Notas com botões 👁/⬇.
- F3 ✅: clicar em linha da aba Contratos troca o contrato ativo sem logout (Decisão F3-c revisada).
- Schema gerenciado via Alembic (3 migrations aplicadas), `start.ps1` roda `alembic upgrade head` no boot.
- `backend/app/security.py` com esqueleto de hash de senha (Decisão #2 — aguarda F1).
- 9 das 10 Decisões Pendentes resolvidas; Decisão #10 deferida.

### O que está pendente

- ~~**F5** (limite 550 PDFs/batch): concluída 2026-05-07.~~
- ~~**F2** (seleção de contrato + tabela `contratos` + seed): concluída 2026-05-11.~~
- ~~**F3b** (consulta de NFs por contrato): concluída 2026-05-12.~~
- ~~**F4** (visualizar/baixar PDF): concluída 2026-05-12.~~
- ~~**F3** (browser de contratos + cache por contrato): concluída 2026-05-13.~~
- ~~**F6** (totalizadores): concluída 2026-05-13.~~
- ~~**F1** (auth real + e-mails de confirmação): concluída 2026-05-14.~~ Pendente apenas smoke real em produção com SMTP Hostinger + SPF/DKIM/DMARC.
- ~~**F8a** (parser non-interactive): concluída 2026-05-06.~~
- **F7** (e-mails transacionais — depende da infra SMTP de F1, já existente). Adiciona templates de "upload concluído com sucesso" para o usuário + alerta de `erro_parsing` para `ADMIN_EMAIL`.
- **F8b** (tabela `nf_pending` + modal + schema NOT NULL com backfill): refina UX de NFs com campo faltante. Hoje cai em `erro_parsing`.

### F8a — concluída em 2026-05-06

Parser non-interactive entregue. Itens que cobriam:
- `main.py` aceita `--contrato/--input-dir/--output-dir/--non-interactive` (bloco `if __name__ == "__main__":`)
- Exceções tipadas `ParserCampoFaltante` e `ParserEstruturaQuebrada(ValueError)`
- 14 chamadas de `_solicitar_campo_humano` cobertas por modificação na função (checa flag)
- 17 `raise ValueError` estruturais convertidos para `ParserEstruturaQuebrada`
- Adapter classifica via exit codes 2/3, aceita `contrato_numero` como 4º arg
- Bind mount de `base_contratos.json` no compose; `opencv-python-headless` em `requirements.txt`
- 6 testes novos em `tests/test_parser_non_interactive.py` passando
- Smoke visual no Docker validado: NFs limpas → `processado`, NFs com campo faltante → `erro_parsing` com mensagem `ParserCampoFaltante: campo='...' contexto='...'`
- Detalhes em `docs/MAIN_PROD_CHANGES.md` (entrada 2026-05-06)

### Arquivos da raiz que **não são** entrypoints

- `base_contratos.json` — fonte de verdade dos contratos. Lido pelo seed em F2.
- `index.html` na raiz (separado de `frontend/index.html`) — vestígio de teste antigo, **não usado** pelo build.
- `.env` — variáveis de ambiente locais. Não comitado.
- `docker-compose.yml` — orquestração local. Entrypoint é o backend container.

### Próxima tarefa concreta proposta

Após F1 entregue (2026-05-14), o caminho crítico restante é **F7 → F8b**.

**F7** (e-mails transacionais) é a próxima — reusa a infra SMTP que F1 já estabeleceu (`email_service.py` com fallback stub). Adiciona dois templates: (a) confirmação de upload bem-sucedido para o usuário (após `batch_done` do SSE); (b) alerta de erro de parser para `ADMIN_EMAIL` quando `status = erro_parsing`. Envio em background para não bloquear o stream. Decisão #1 e #8 já resolvidas.

Antes de F7, vale completar a **Fase D do F1** com o smoke real no Hostinger (registrar conta com e-mail institucional, validar DNS, confirmar via link real, login). Depende de credenciais SMTP reais da Hostinger.




git push --set-upstream origin "banco_nf_com_contratos_filtro"

---

## F2 — Fase A (Spec) — Tela de seleção de contrato

> **Status**: aguardando aprovação do dono. Nenhum código será escrito até confirmação explícita.
> Esta spec é vinculante durante B1/B2/B3/B4/C/D.

### Escopo

Passo obrigatório entre login e área de upload. Usuário escolhe contrato; contrato fica na sessão e é associado ao `UploadBatch`. Implica schema novo (`contratos` + colunas FK em `upload_batches` e `nf_entries`), seed do `base_contratos.json` (~140 entradas), 3 endpoints novos, integração com `/api/uploads`, e frontend novo (rota + redirect + tela + topbar).

### Pré-requisito desta feature

**Alembic precisa ser introduzido no projeto** (Decisão #3, já resolvida em 2026-05-05). F2 é a primeira migration "real" após o baseline. Hoje o projeto usa `init_db()` (`create_all`) no `lifespan` — vamos manter para testes, mas adicionar Alembic para produção.

### Sub-fases de execução

Estimativa total: ~600-800 linhas. Divisão em 4 sub-fases B + C + D para respeitar o limite de ~400 linhas/fase do DoD.

| Sub-fase | Conteúdo | Diff estimado |
|---|---|---|
| **B1** — Alembic + schema | Setup Alembic em `backend/`, baseline migration capturando schema atual (`users`, `upload_batches`, `upload_files`, `nf_entries`), migration F2 (tabela `contratos` + colunas `contrato_id` NULLABLE em `upload_batches` e `nf_entries`). `models.py` ganha novo modelo `Contrato` e FKs. `start.ps1` ganha `alembic upgrade head` antes do `docker compose up`. Smoke test de migration contra banco vazio. | ~250 linhas |
| **B2** — Seed | `backend/app/seeds/seed_contratos.py` lê `base_contratos.json`, valida shape básico (campos esperados, tipos), gera UUID5 estável a partir de `numero`, faz `INSERT ... ON CONFLICT (numero) DO UPDATE`. Integra ao `lifespan` após `init_db()`. Tests: seed idempotente (rodar 2x não duplica), JSON malformado falha cedo, ID estável entre runs. | ~150 linhas |
| **B3** — Endpoints | `GET /api/contratos` (autenticado, lista ativos ordenados). `POST /api/session/contrato` (recebe id, valida, persiste). `GET /api/session/contrato` (retorna atual ou 404). Dependency `require_contrato` em `backend/app/dependencies.py` (a criar) que lê `request.session["contrato_id"]` e levanta `HTTPException(400)`. Tests: cada endpoint sem auth (401), com auth (200/404), id inválido (404). | ~200 linhas |
| **B4** — Integração com upload | `POST /api/uploads` usa `Depends(require_contrato)`. Adapter passa contrato real (`request.session["contrato_id"]` → busca `numero` → subprocess). **Remove `DEFAULT_CONTRATO_PRE_F2`** do `parser_adapter.py`. Associa `contrato_id` ao `UploadBatch` criado. Tests: upload sem contrato → 400; upload com contrato → batch.contrato_id preenchido. | ~150 linhas |
| **C** — Frontend | Nova rota React `/contratos` (manter SPA monolítica em `App.jsx` por ora; criar componente local em `frontend/src/components/` para a tela conforme adversarial #29). Após login, `GET /api/session/contrato` no boot; se 404 → redirect `/contratos`. Tela: lista + filtro por `numero`/`sigla`/`uf` + botão confirmar (chama `POST /api/session/contrato`). Topbar mostra contrato ativo. `npm run build`. | ~250 linhas |
| **D** | DoD checklist + commit | — |

### Decisões internas para confirmar antes de B1

1. **ID do contrato**: schema diz `VARCHAR(36) PRIMARY KEY`. Recomendo **UUID5 determinístico** derivado de `numero` (`uuid.uuid5(NAMESPACE_DNS, numero)`). Justificativa: re-seeds não criam IDs novos (adversarial #31), e a relação `numero ↔ id` fica estável entre ambientes (dev/prod compartilham IDs). Aceito?

2. **Validação do `base_contratos.json` no seed**: dois caminhos:
   - **Pragmático** (recomendo): checagem manual dos campos esperados (`sigla`, `cnpj`, `tranche`, `uf`, `valor_contrato`, `valor_cde`, `participacao_cde`, `tipo_contrato`); falha cedo com erro claro. ~10 linhas.
   - **Robusto**: pydantic schema. ~30 linhas + dependência implícita já presente via FastAPI.
   
   Recomendo pragmático — JSON é estático, ~140 entradas, validação manual é suficiente. Pydantic é overkill aqui.

3. **`require_contrato` aplicado a quais endpoints na F2**:
   - **Apenas `POST /api/uploads`** nesta feature.
   - F3 (consulta de contratos) **não** exige contrato selecionado (lista geral).
   - F4 (PDF download) e F6 (totalizadores) terão suas próprias decisões na hora.
   
   Adversarial #4 quer lista exaustiva. Aceitável manter só `/api/uploads` por enquanto e atualizar PROJECT_BUILDING.md quando outros entrarem?

4. **Frontend — rotas**: SPA monolítica hoje. Adicionar React Router OU usar state interno (`page = 'login' | 'contratos' | 'upload'`)?
   - **Recomendo state interno** — preserva monólito e evita dependência nova. Adversarial #29 permite componentes locais em `frontend/src/components/` sem reestruturação, o que é compatível com state interno.
   - React Router seria certo se houvessem 5+ rotas; para 3, é overkill.
   
   Aceito state interno?

5. **Persistência da seleção entre sessões**: Decisão #6 diz **somente sessão, sem persistência** — confirmação só.

6. **Contrato inativo (`ativo = FALSE`)**: nesta fase não há UI para tornar inativo (não está no escopo). Mas seed pode marcar inativo via JSON manualmente. `GET /api/contratos` filtra `WHERE ativo`. `POST /api/session/contrato` com id de contrato inativo → 404 (não 403, não vazar existência — adversarial #21). Aceito?

### Critérios de sucesso (verificáveis)

- [ ] `alembic upgrade head` em banco vazio cria todas as tabelas sem erro.
- [ ] Seed roda no `lifespan` e popula ~140 contratos. Re-rodar não duplica.
- [ ] `GET /api/contratos` autenticado → 200 com lista ordenada por `numero`. Anônimo → 401.
- [ ] `POST /api/session/contrato` com id válido → 200. Inativo/inexistente → 404.
- [ ] `GET /api/session/contrato` sem seleção → 404. Com seleção → 200 + objeto.
- [ ] `POST /api/uploads` sem contrato na sessão → 400 (`"Nenhum contrato selecionado."`).
- [ ] `POST /api/uploads` com contrato → `upload_batches.contrato_id` preenchido + parser recebe `--contrato N`.
- [ ] Frontend pós-login: sem contrato → tela `/contratos`. Com contrato → área de upload com topbar.
- [ ] Filtro por `numero`/`sigla`/`uf` na tela funciona.
- [ ] Tests cobrem: cada endpoint sem auth (401), id inválido (404), seed idempotente, upload sem contrato (400).

### Critérios negativos transversais (DoD §5)

- [ ] Sem auth → 401 antes de qualquer rota de contrato.
- [ ] Contrato inativo selecionado → 404, não exposição.
- [ ] Double-click no botão "selecionar contrato" → idempotente (`POST /api/session/contrato` pode ser chamado múltiplas vezes sem dano).
- [ ] Refresh durante seleção → ou retoma `request.session["contrato_id"]` (se já selecionado), ou volta para `/contratos`.
- [ ] Sessão expirada durante upload → 401, frontend redireciona para login (sem perda da seleção atual ainda na sessão expirada — preserva semântica).
- [ ] Migration roda 2x → idempotente (Alembic gerencia).
- [ ] Seed em DB com contratos preexistentes → `ON CONFLICT DO UPDATE` atualiza valores sem duplicar.

### Fora de escopo

- **Permissões por usuário/contrato** (adversarial #5): nesta fase, todos os autenticados veem todos os contratos. Risco aceito — registrado em `planning/PENDING_DECISIONS.md`.
- **Pré-seleção do último contrato** (Decisão #6): parqueada para servidor institucional.
- **CRUD de contratos**: contratos vêm do JSON. Edição/criação via UI fica para outra feature.
- **Auditoria do seed `ON CONFLICT DO UPDATE`**: adversarial #32 quer log de diff. Por ora, log textual no console do `lifespan` (não estruturado). Defense-in-depth completo fica para futuro.
- **Migração de batches antigos**: `upload_batches.contrato_id` é NULLABLE; batches pré-F2 ficam NULL. Sem backfill.
- **Validação aplicacional "novos registros pós-F2 exigem FK"** (adversarial #7): será adicionada como check no `POST /api/uploads` (já vem via `require_contrato`), mas sem trigger DB ou enforcement no schema. Aceito.

### Ambiente-alvo

**Local/dev** para esta feature, com Hostinger semi-prod recebendo o mesmo código quando o branch for promovido. Schema e seed funcionam em SQLite (testes) e PostgreSQL (Docker/prod).

### ⏸ CHECKPOINT FASE A

Aguardo:

1. **"ok, segue para B1"** — aprovado integralmente, escolhas recomendadas nas decisões 1-6 aceitas.
2. **"ajuste X"** — aprovado com ressalvas; aplico ajustes na spec antes de iniciar B1.
3. **"refazer"** — spec não bate com o escopo; volto a estudar.

---

## F5 — Spec da Fase A — Limite de 550 PDFs por batch

> **Status**: ✅ concluída em 2026-05-07. 2ª passada — primeira tentativa em 2026-05-06 foi descartada no rollback após incidente com arquivos do parser sumirem do disco. Spec idêntica à aprovada na primeira tentativa. Smoke visual aprovado pelo dono.
>
> **Resumo do diff**:
> - Backend: `if len(files) > 550 → HTTPException(422)` em `server.py:262-269`, após auth e antes de IO
> - Frontend: constante `MAX_FILES_PER_BATCH = 550` + alerta inline (texto enxuto, sem repetir count) + `disabled` no botão de envio quando excedido
> - CSS: `margin-top: 12px` em `.inline-error` (corrige UX detectada na 1ª tentativa, beneficia também o uso na tabela de entries)
> - Tests: 3 novos em `tests/test_upload_limit.py` (551 → 422 com contagem, 550 → não rejeita, 0 → preserva)
> - Build: `npm run build` regenerou `backend/app/static/`

### Escopo

Cirúrgico. Adiciona uma única validação de quantidade de arquivos no endpoint `POST /api/uploads` (canônico) e um aviso de UX no `App.jsx` (rede de segurança).

### Backend (sub-fase B)

1. Em `backend/app/server.py`, dentro de `upload_pdfs`, **antes** de `await upload.read()`:
   ```python
   if len(files) > 550:
       raise HTTPException(
           status_code=422,
           detail=f"Limite de 550 arquivos por lote excedido. Recebido: {len(files)}",
       )
   ```
2. Posição: depois de `get_authenticated_user(request)`, antes do loop que lê os bytes. Roda só após auth (critério negativo "sem auth retorna 401" preservado).
3. Teste em `backend/tests/test_upload_limit.py`:
   - `test_upload_with_551_files_returns_422_with_count`
   - `test_upload_with_550_files_does_not_reject_at_limit`
   - `test_upload_with_zero_files_preserves_existing_behavior`

### Frontend (sub-fase C)

Em `frontend/src/App.jsx`:
1. Constante `MAX_FILES_PER_BATCH = 550` no topo do módulo.
2. Alerta inline (classe `inline-error` com `margin-top: 12px` adicionado em `styles.css`) quando `selectedFiles.length > MAX_FILES_PER_BATCH`. Texto: `"Excedeu o limite de {MAX_FILES_PER_BATCH} arquivos por lote. Reduza a seleção para enviar."` (sem repetir a contagem que já aparece em `file-status`).
3. Botão "Enviar PDFs" `disabled` quando excedido.
4. `npm run build` ao final.

### Critérios de sucesso (verificáveis)

- [ ] 551 arquivos → 422 com contagem na mensagem
- [ ] 550 arquivos → não rejeita no limite
- [ ] Frontend desabilita o botão e exibe alerta quando excedido
- [ ] 3 testes em `test_upload_limit.py` passam
- [ ] Smoke visual com >550 arquivos: alerta aparece, botão desabilitado

### Fora de escopo

- Limite de tamanho/content-type por arquivo (Decisão #10, deferida)
- Limite de payload no proxy/nginx (responsabilidade ops)
- Validação no contrato selecionado (não interage com `request.session["contrato_id"]` — F2)

### Ambiente-alvo

Local/dev. Limite canônico no backend é independente de ambiente; Hostinger semi-prod ganha a proteção quando o branch for promovido.

### Sub-fases de execução

| Sub-fase | Conteúdo | Diff estimado |
|---|---|---|
| **B** | `server.py` validação + `test_upload_limit.py` | ~30 linhas |
| **C** | `App.jsx` alerta + `disabled` + `styles.css` margin + `npm run build` | ~30 linhas |
| **D** | DoD checklist + commit (vai junto com a deleção pendente de `bug_fix/main.py`) | — |

### ⏸ Status

Spec re-registrada. Iniciando **B** imediatamente (autorização do dono já concedida via "Pode seguir para a F5").

---

## F8a — Spec da Fase A — Parser non-interactive + exceções tipadas

> **Status**: ✅ concluída em 2026-05-06. Spec ficou vinculante durante B1/B2/B3/B4/B5/D conforme regra 6 do "Modelo de execução por fases" em `PLAN.md`. Sub-fases B4 e B5 foram fixes de infra detectados durante o smoke (Fase C) — `opencv-python-headless` em `requirements.txt` e bind mount de `base_contratos.json` no compose. Detalhes do diff em `docs/MAIN_PROD_CHANGES.md` (entrada 2026-05-06).

### Proposta de corte: F8a + F8b

F8 inteiro (Decisão #8) é grande demais para uma única feature dentro do limite de ~400 linhas por fase do DoD. Proposta:

- **F8a** (esta feature) — **mínimo para desbloquear F2**: parser roda non-interactive com `--contrato`, exceções tipadas (`ParserCampoFaltante`, `ParserEstruturaQuebrada`), adapter classifica por `isinstance`, ambos os tipos caem em `erro_parsing` por enquanto. Sem modal, sem `nf_pending`, sem schema NOT NULL.
- **F8b** (feature seguinte na ordem, antes de F1) — **fluxo completo de pendência**: tabela `nf_pending`, endpoint `/resolve`, SSE event `file_pending_input`, modal no frontend, schema NOT NULL nas 11 colunas de `nf_entries` com migration de backfill.

Justificativa: F8a é suficiente para a aresta dura `F8 → F2`. Sem `nf_pending`, NF com campo faltando vira `erro_parsing` — usuário reenvia depois de corrigir manualmente. F8b refina UX mas não bloqueia nada do roadmap até F1. Reordenando: F8a → F5 → F2 → F3 → F4 → F6 → **F8b** → F1 → F7.

### Escopo de F8a

**Backend — refactor de `backend/app/main.py`** (sub-fase B1):

1. Definir duas exceções no topo do arquivo (após imports, antes de `arquivo_investigado`):
   ```python
   # FASE PROD — exceções tipadas para classificação de erro pelo adapter
   class ParserCampoFaltante(Exception):
       def __init__(self, campo, contexto, prefilled=None):
           self.campo = campo
           self.contexto = contexto
           self.prefilled = prefilled or {}
           super().__init__(f"Campo '{campo}' não extraído em {contexto}")

   class ParserEstruturaQuebrada(Exception):
       pass
   ```
2. Envolver **todo** o código de topo executável (`main.py:78-92` em diante) em `if __name__ == "__main__":` para que o módulo possa ser importado sem efeitos colaterais. **Sem apagar nada** — apenas indentar dentro do bloco guarda. (Atende item #16 do adversarial review.)
3. Adicionar parsing de argumentos no novo bloco `if __name__ == "__main__":`:
   ```python
   # FASE PROD — flags non-interactive
   import argparse
   parser_args = argparse.ArgumentParser()
   parser_args.add_argument("--contrato", type=str)
   parser_args.add_argument("--input-dir", type=str)
   parser_args.add_argument("--output-dir", type=str)
   parser_args.add_argument("--non-interactive", action="store_true")
   args = parser_args.parse_args()
   ```
4. Para cada uma das **14 chamadas** de `_solicitar_campo_humano` (linhas 1024, 1030, 1191, 1206-1210, 1923, 1928, 1945, 1951, 1957, 1963, 1988):
   - Manter chamada original como `# FASE DEV (terminal):` comentada acima
   - Substituir por `raise ParserCampoFaltante(campo=..., contexto=...)` quando `args.non_interactive`
5. Para cada um dos **17 `raise ValueError`** estruturais (linhas 687, 761, 903, 1008, 1046, 1164, 1168, 1235, 1309, 1317, 1319, 1343, 1369, 1381, 1558, 1599, 1901):
   - Trocar `ValueError` por `ParserEstruturaQuebrada`. **Linha 1599 é exceção semântica** mas estruturalmente é Tipo 2 (já documentado em `PLAN.md`).
6. Registrar **cada mudança** em `docs/MAIN_PROD_CHANGES.md` com motivo + before/after, conforme regra 4 da seção "Regras gerais de refactor".

**Backend — atualizar `parser_adapter.py`** (sub-fase B2):

1. Aceitar `contrato_numero` como argumento de `parse_pdf_bytes`.
2. Invocar subprocess com `--contrato N --input-dir X --output-dir Y --non-interactive`.
3. Classificar `process.returncode` por exit code definido no `main.py` (a definir: ex. `2` = `ParserCampoFaltante`, `3` = `ParserEstruturaQuebrada`, qualquer outro != 0 = `erro_parsing` genérico).
4. Por enquanto, ambos os exit codes 2 e 3 viram `ParserOutcome(status="erro_parsing", error=...)`. F8b refina o caso 2 para `nf_pending`.

**Backend — atualizar chamadas de `LegacyParserAdapter`** (sub-fase B2):
- `server.py` precisa passar `contrato_numero` ao adapter. **Como F2 ainda não rodou**, F8a aceita `contrato_numero=None` e nesse caso passa um número fixo placeholder (ex.: primeiro contrato do `base_contratos.json`) **apenas para o subprocess não falhar em validação**. Esse placeholder vira código morto após F2.

### Critérios de sucesso de F8a (verificáveis)

- [ ] `python backend/app/main.py --contrato "ECFS 101/2005" --input-dir /tmp/in --output-dir /tmp/out --non-interactive` roda sem `input()` em PDF que precisaria de campo (encerra com exit code 2).
- [ ] `python -c "import backend.app.main"` não dispara o menu interativo.
- [ ] `parser_adapter.parse_pdf_bytes()` em PDF "limpo" retorna `processado` como antes.
- [ ] PDF com campo faltando retorna `erro_parsing` com mensagem identificando o campo.
- [ ] PDF com erro estrutural retorna `erro_parsing` com mensagem do `ParserEstruturaQuebrada`.
- [ ] Teste backend novo em `tests/test_parser_non_interactive.py` cobre os 3 caminhos.
- [ ] `docs/MAIN_PROD_CHANGES.md` tem entrada por mudança aplicada.

### Fora de escopo (vai para F8b)

- Tabela `nf_pending` e migration
- Endpoint `POST /api/uploads/pending/{id}/resolve`
- Evento SSE `file_pending_input`
- Modal no frontend
- `nf_entries` colunas NOT NULL + backfill

### Ambiente-alvo

**Local/dev** para esta feature. Hostinger semi-prod só roda parser em produção a partir de F2.

### Critérios negativos transversais

- [ ] Subprocess sem `--non-interactive` mantém comportamento legado (não regrede dev).
- [ ] Subprocess com flag mas sem `--contrato` falha rápido com mensagem clara, não trava.
- [ ] Importar `backend.app.main` em teste não tem efeito colateral.
- [ ] Testes existentes em `backend/tests/` continuam passando sem alteração.

### Sub-fases de execução (após aprovação desta spec)

| Sub-fase | Conteúdo | Diff estimado |
|---|---|---|
| **B1** | Refactor `main.py` — exceções, `if __name__ == "__main__":`, argparse, substituição das 14 chamadas e 17 raises | ~250 linhas (com pares FASE DEV/PROD) |
| **B2** | `parser_adapter.py` + chamada em `server.py` + placeholder de contrato | ~80 linhas |
| **B3** | Testes em `tests/test_parser_non_interactive.py` + entradas em `MAIN_PROD_CHANGES.md` | ~100 linhas |
| **D**  | DoD checklist + commit | — |

C (frontend) **não se aplica** em F8a — sem mudança visível na UI.

### Pontos que precisam de decisão antes de B1

1. **Exit codes**: 2 = `ParserCampoFaltante`, 3 = `ParserEstruturaQuebrada`? Ou usar `sys.exit(json.dumps({...}))` em stdout? Recomendo exit codes — mais simples e o adapter já lê `process.returncode`.
2. **Placeholder de contrato pré-F2**: aceitar `--contrato` opcional e cair no menu interativo se ausente (preserva DEV) **OU** exigir sempre e usar primeiro contrato do JSON como default em F8a? Recomendo exigir sempre — força disciplina; o "default" vai ser removido em F2 mesmo.
3. **Linha 1599 (raise ValueError fallback)**: vira `ParserEstruturaQuebrada` (mantém PLAN.md) ou `ParserCampoFaltante` (mais coerente com a mensagem "campos não preenchidos")? Recomendo `ParserEstruturaQuebrada` — está no design como Tipo 2.

### ⏸ CHECKPOINT FASE A

Aguardo do dono uma das três respostas:

1. **"ok, segue para B1"** — aprovado integralmente, escolhas recomendadas nas decisões 1-3 aceitas.
2. **"ajuste X, Y"** — aprovado com ressalvas; aplico ajustes na spec antes de iniciar B1.
3. **"refazer"** — spec não bate com o que você quer; volto a estudar o problema.