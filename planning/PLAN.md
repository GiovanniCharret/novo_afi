# PLAN.md — Roadmap de Novas Features — Banco de Notas ENBpar

Este documento descreve as 7 features do próximo ciclo de desenvolvimento, suas dependências, impactos de schema e critérios de sucesso verificáveis. As Partes 1–7 do MVP anterior estão em `docs/PLAN.md` e não são repetidas aqui.

> **Status**: rascunho — várias decisões dependem de respostas em "Decisões Pendentes" no final deste documento. Não iniciar implementação antes da aprovação do dono.

---

## Visão Geral e Ordem de Implementação

### Dependências obrigatórias (bloqueiam — não podem ser violadas)

```
F8 ──► F2     parser non-interactive precisa receber contrato da sessão;
              sem F8, F2 entrega seleção no frontend mas o parser continua
              inferindo `contrato` por menu, violando a associação real.

F2 ──► F6     totalizadores leem `nf_entries.contrato_id`; sem F2,
              só existe `contrato` texto livre legado.

F1 ──► F7     F7 reutiliza a infra SMTP introduzida em F1.
```

Violar uma aresta acima é defeito, não escolha — qualquer entrega de F2 sem F8 concluída, F6 sem F2 concluída ou F7 sem F1 concluída é considerada incompleta independentemente de critérios funcionais.

### Independências (qualquer momento, contanto que respeitem o DoD)

- **F3** — lê `contratos`; só precisa que F2 tenha rodado o seed (não a UI completa de seleção).
- **F3b** — lê `nf_entries.contrato_id`; depende de F2 ✅ concluída (caso contrário só vê NFs com `contrato_id IS NULL`).
- **F4** — usa `banco_de_nf/` já existente; independente das demais.
- **F5** — limite hard de 550, sem dependências.

### Checkpoints de conclusão (definem "feature pronta", endurecem as arestas)

- **F8a ✅ concluída em 2026-05-06**: `python main.py --contrato N --input-dir X --output-dir Y --non-interactive` roda sem `input()`, código de topo executável movido para `if __name__ == "__main__":`, `_solicitar_campo_humano` levanta `ParserCampoFaltante` em modo non-interactive, 17 raises estruturais convertidos para `ParserEstruturaQuebrada(ValueError)`. Adapter classifica via `isinstance` (preservada por exit codes 2/3 sincronizados entre `main.py` e `parser_adapter.py`). Detalhes em `docs/MAIN_PROD_CHANGES.md`.
- **F8b concluída** quando: `ParserCampoFaltante` vira registro em `nf_pending` com modal de preenchimento manual; endpoint `POST /api/uploads/pending/{id}/resolve` insere em `nf_entries` e retoma o batch; 11 colunas de `default_nf_template` em `nf_entries` viram NOT NULL (com migration de backfill).
- **F2 concluída** quando: uploads novos gravam `upload_batches.contrato_id` **e** linhas em `nf_entries` recebem `contrato_id` da sessão, sem fallback ao menu interativo do parser. Endpoint `POST /api/uploads` retorna 400 sem contrato na sessão.
- **F6 concluída** quando: totalizador consulta apenas `nf_entries` com `contrato_id IS NOT NULL` e status que conta como persistido (filtro exato definido na própria F6). Não soma linhas legadas com `contrato` texto livre.
- **F1 concluída** quando: usuário legado `user/password` é rejeitado em qualquer ambiente com `APP_ENV != development`; tokens de confirmação/reset são hash em banco, uso único, e SMTP ausente em produção falha startup.

### Ordem de execução

```
1. F8a ✅ parser non-interactive + exceções tipadas      (concluída 2026-05-06)
2. F5  ✅ limite 550                                     (concluída 2026-05-07)
3. F2  ✅ seleção de contrato + seed validado            (concluída 2026-05-11)
4. F3b ✅ consulta de NFs por contrato                   (concluída 2026-05-12)
5. F4  ✅ visualizar/baixar PDF                          (concluída 2026-05-12)
6. F3  ✅ browser de contratos + cache por contrato      (concluída 2026-05-13)
7. F6  — totalizadores                                   (consome F2)
7. F8b — nf_pending + modal + schema NOT NULL            (refina UX de F8a)
8. F1  — auth real                                       (desbloqueia F7)
9. F7  — e-mails transacionais                           (consome F1)
```

A ordem acima é a do ciclo. Trocar dentro de blocos independentes (ex.: F4 antes de F3) é permitido; **violar uma aresta da seção "Dependências obrigatórias" exige justificativa documentada e nova decisão registrada em `PENDING_DECISIONS.md`**.

A migração do parser (`main_v9.py` → parser v10 em `backend/app/main.py`) é uma feature transversal documentada em seção própria ao final. A cópia dos arquivos já foi feita; o que falta é a adaptação non-interactive — formalizada como F8.

### Modelo de execução por fases (humano-acompanhável)

O ciclo é **estritamente sequencial por feature**. Cada feature roda em 4 fases com **checkpoint humano obrigatório** entre elas. Não se inicia a fase seguinte sem aprovação explícita do dono na fase corrente.

```
[Fase A] Spec curta (1 página em planning/PROJECT_BUILDING.md)
         ├─ escopo, arestas duras, critérios negativos, ambiente-alvo
         └─ ⏸ CHECKPOINT: dono lê e aprova ("ok, segue") OU pede ajuste

[Fase B] Backend
         ├─ models/migration + endpoints + tests
         ├─ pytest passa
         └─ ⏸ CHECKPOINT: dono roda testes localmente, aprova OU pede ajuste

[Fase C] Frontend (se aplicável)
         ├─ componentes + integração com endpoints da Fase B
         ├─ npm run build sem erro
         └─ ⏸ CHECKPOINT: dono usa a feature no browser, aprova OU pede ajuste

[Fase D] Definition of Done + commit
         ├─ checklist de planning/DEFINITION_OF_DONE.md preenchida
         ├─ docs atualizados (CLAUDE.md, MAIN_PROD_CHANGES.md se main.py mudou)
         └─ ⏸ CHECKPOINT FINAL: dono revisa diff completo, aprova merge
                                ou pede revisão antes de iniciar próxima feature
```

**Regras do modelo de fases:**

1. **Uma feature por vez.** Não iniciar F5 enquanto F8 não passou pela Fase D. Não iniciar F2 enquanto F5 não passou pela Fase D.
2. **Diff máximo por fase: ~400 linhas.** Se uma fase passar disso, parar e dividir em sub-fases (B1/B2) com checkpoint entre elas.
3. **Pausa entre features.** Após o checkpoint final de uma feature, dono confirma explicitamente o início da próxima — não emendar automaticamente.
4. **Checkpoint não é formalidade.** Se o dono testa e algo não bate com a spec da Fase A, retorna-se à Fase B (ou A se a spec estava errada). Não se avança "consertando depois".
5. **Bug encontrado em fase anterior congela a atual.** Se na Fase C aparece bug na Fase B, volta-se para B antes de seguir.
6. **Spec da Fase A é vinculante.** Mudança de escopo durante B/C exige nova rodada de A com aprovação registrada.

A Definition of Done canônica vive em `planning/DEFINITION_OF_DONE.md` (a criar antes de iniciar F8).

---

## Mudanças Transversais de Schema

### Tabela `contratos` (nova)

Seed a partir de `base_contratos.json` (~140 entradas).

```sql
CREATE TABLE contratos (
    id          VARCHAR(36) PRIMARY KEY,
    numero      VARCHAR(32) UNIQUE NOT NULL,   -- ex.: "ECFS 101/2005"
    sigla       VARCHAR(255) NOT NULL,
    cnpj        VARCHAR(14) NOT NULL,
    tranche     VARCHAR(64),
    uf          VARCHAR(2),
    valor_contrato     NUMERIC(18,2) NOT NULL DEFAULT 0,
    valor_cde          NUMERIC(18,2) NOT NULL DEFAULT 0,
    participacao_cde   NUMERIC(5,4)  NOT NULL DEFAULT 0,
    tipo_contrato      VARCHAR(16)   NOT NULL,  -- "LPT" ou "MLA"
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

Variações observadas: `LPT` (maioria) e `MLA` (bloco ECM/2025). Vários contratos têm `valor_contrato = 0` e `valor_cde = 0` (ainda não monetizados); `ativo` permite filtrar sem deletar.

### Tabela `upload_batches` — campo `contrato_id` (novo)

`contrato_id VARCHAR(36) REFERENCES contratos(id) NULLABLE`. Nulo para batches antigos; obrigatório para novos após F2.

### Tabela `nf_entries` — campos novos

- `contrato_id VARCHAR(36) REFERENCES contratos(id) NULLABLE` complementa o `contrato` texto livre atual (mantido como legado).
- `upload_file_id VARCHAR(36) REFERENCES upload_files(id) NULLABLE` para rastrear de qual arquivo o lançamento foi extraído (necessário para F4).

A `business_key` **não muda** — uma mesma NF não pode existir duas vezes mesmo em contratos diferentes.

### Tabela `nf_pending` (nova, F8)

NFs que o parser identificou mas não conseguiu preencher 100% dos campos obrigatórios. Aguardam preenchimento manual via modal no frontend.

```sql
CREATE TABLE nf_pending (
    id                  VARCHAR(36) PRIMARY KEY,
    upload_file_id      VARCHAR(36) NOT NULL REFERENCES upload_files(id) ON DELETE CASCADE,
    upload_batch_id     VARCHAR(36) NOT NULL REFERENCES upload_batches(id) ON DELETE CASCADE,
    contrato_id         VARCHAR(36) NOT NULL REFERENCES contratos(id),
    prefilled_json      TEXT NOT NULL,        -- campos que o parser conseguiu extrair (descricao, ncm, quant, etc.)
    missing_fields_json TEXT NOT NULL,        -- lista de nomes de campos pendentes (ex.: ["cnpj", "fornecedor"])
    status              VARCHAR(16) NOT NULL DEFAULT 'aguardando',  -- aguardando | resolvido | abandonado
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX idx_nf_pending_status ON nf_pending(status);
CREATE INDEX idx_nf_pending_batch ON nf_pending(upload_batch_id);
```

Fluxo:
- Parser detecta NF com campo faltando → cria entrada com `status='aguardando'`.
- Frontend resolve via `POST /api/uploads/pending/{id}/resolve` → backend insere em `nf_entries` e marca `status='resolvido'`.
- Sessão abandonada por timeout → job marca `status='abandonado'`. NF não entra em `nf_entries`. Re-submissão dos PDFs deduplica via `business_key` quando o usuário voltar.

### Tabela `users` — campos para F1

```sql
ALTER TABLE users ADD COLUMN email VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN email_confirmed BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN confirmation_token VARCHAR(128);
ALTER TABLE users ADD COLUMN token_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN reset_token VARCHAR(128);
ALTER TABLE users ADD COLUMN reset_expires_at TIMESTAMPTZ;
```

### Migração

Hoje o projeto usa `create_all` no `lifespan` sem sistema de migrations. Para colunas novas em tabelas existentes, a estratégia mais simples é um script idempotente (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) executado no `lifespan` antes do `create_all`. **Decisão pendente**: introduzir Alembic neste momento? (ver Decisão #3).

---

## F5 — Limite máximo de 550 notas por batch ✅ concluída em 2026-05-07

**Objetivo**: impedir que um único envio submeta mais de 550 PDFs, protegendo o sistema de timeouts e uso excessivo de recursos.

### Subetapas
- [x] Em `POST /api/uploads`, antes de qualquer IO, contar `len(files)`. Se `> 550`, retornar `HTTP 422` com `{"detail": "Limite de 550 arquivos por lote excedido. Recebido: N"}`.
- [x] No frontend (`App.jsx`), ao selecionar arquivos, verificar `files.length > 550` e exibir alerta inline antes de habilitar o botão de envio.
- [x] Teste: `POST /api/uploads` com 551 arquivos-stub retorna 422.

### Critérios de Sucesso
- [x] 551 arquivos → 422 com a contagem na mensagem.
- [x] 550 arquivos → aceito normalmente (não rejeita no limite).
- [x] Frontend desabilita o botão ao selecionar > 550, sem submeter.

Smoke visual no Docker validado pelo dono. Detalhes do diff em `planning/PROJECT_BUILDING.md` (seção "F5 — Spec da Fase A").

**Histórico**: primeira tentativa em 2026-05-06 foi descartada por incidente de arquivos do parser sumirem do disco (rollback `git reset --hard 88fb0b0`). Re-aplicação em 2026-05-07 com mesma spec, mesmo código.

---

## F2 — Tela de seleção de contrato ✅ concluída em 2026-05-11

**Objetivo**: passo obrigatório entre login e área de upload onde o usuário escolhe o contrato em que vai trabalhar. O contrato fica na sessão e é associado ao batch.

### Subetapas
- [x] Criar tabela `contratos` (schema acima). — `models.py:Contrato` + Alembic `0002_f2_contratos.py`.
- [x] Script de seed `backend/app/seeds/seed_contratos.py` lê `base_contratos.json` e faz `INSERT ... ON CONFLICT (numero) DO UPDATE`. Executado no `lifespan` após `init_db()`.
- [x] `GET /api/contratos` (autenticado) retorna contratos ativos ordenados por `numero`. Campos: `id, numero, sigla, uf, tranche, tipo_contrato, valor_contrato, valor_cde, participacao_cde`. — `server.py:284`.
- [x] `POST /api/session/contrato` recebe `{"contrato_id": "..."}`, valida, persiste em `request.session["contrato_id"]`, retorna o contrato. — `server.py:319`. Inativo/inexistente → 404 (adversarial #21).
- [x] `GET /api/session/contrato` retorna o contrato selecionado ou 404. — `server.py:295`. Limpa sessão se contrato sumiu entre seleção e consulta.
- [x] `POST /api/uploads` lê `contrato_id` da sessão; se ausente, retorna `HTTP 400 {"detail": "Nenhum contrato selecionado."}`. — via `Depends(require_contrato)` em `dependencies.py`.
- [x] Associar `contrato_id` ao `UploadBatch` criado. — `server.py:382`.
- [x] Associar `contrato_id` à `NfEntry` criada. — `create_nf_entry(db, row, contrato_id=...)` em `server.py:137`/`server.py:462`. Teste `test_upload_with_contrato_persists_contrato_id_on_nf_entry`. Nota: rows pré-F2 ou inseridas sem contrato ativo na sessão ficam com `contrato_id = NULL` (coluna é nullable por isso).
- [x] Frontend: após login, redirecionar para tela de seleção de contrato (busca + lista). Confirmar antes de avançar. — `App.jsx:479` + `frontend/src/components/ContratoSelector.jsx`.
- [x] Exibir contrato ativo no topbar da área logada. — `App.jsx:495` (`.topbar-contrato`).

### Critérios de Sucesso
- ✅ `GET /api/contratos` retorna lista para autenticado, 401 para anônimo. — `test_contratos_endpoints.py`.
- ✅ `POST /api/session/contrato` com id válido persiste na sessão; inválido → 404.
- ✅ `POST /api/uploads` sem contrato na sessão → 400. — `test_upload_with_contrato.py`.
- ✅ `upload_batches.contrato_id` reflete o id correto após upload.
- ✅ `nf_entries.contrato_id` reflete o id correto após upload.
- ✅ Tela de seleção filtra (ver evolução abaixo).

### Evolução pós-spec (2026-05-11)
A spec original previa "Tela de seleção filtra por `numero`, `sigla` e `uf`" como lista única. Foi refatorada para **dois níveis (Estado → Contrato)** com base em feedback humano:
- Nível 1: lista de estados (UF distintos) com contagem por estado, ordem alfabética em pt-BR, filtro por nome do estado/sigla UF.
- Nível 2: lista de contratos do estado escolhido, formato `sigla · tranche · tipo_contrato` (linha primária) + `numero` em fonte monoespaçada na linha secundária. Filtro por sigla/tranche/tipo/número.
- Botão "Voltar para estados" no nível 2; breadcrumb mostra o estado atual.
- Endpoint `/api/contratos` não muda — agregação por UF é client-side.

Motivação: "as letrinhas confundem" (siglas técnicas como `ECFS 327/2013` não são bons pontos de busca humana). Mockup HTML aprovado em `planning/` antes da implementação.

---

## F3 — Página de consulta de contratos ✅ concluída em 2026-05-13

**Objetivo**: tela dedicada para busca e visualização dos **contratos** da base (planilha estática vinda do seed em F2), sem vínculo com a sessão ativa. Feature irmã de F3b: F3 lê a tabela `contratos`, F3b lê `nf_entries` filtrado por contrato. Spec visual completa em `planning/F3-consulta-contratos.html`.

### Subetapas
- [x] Estender `GET /api/contratos` com query params opcionais `?q=&numero=&sigla=&uf=&tranche=&tipo_contrato=&com_valor=&incluir_inativos=`. Defaults `None`/`False` preservam o comportamento atual (regressão validada — endpoint compartilhado com `ContratoSelector` F2 e dropdown da Notas F3b). `q` faz `ILIKE` em `numero OR sigla` (busca única). `numero`/`sigla` separados continuam ILIKE individuais.
- [x] Tela "Contratos" no frontend (3ª aba). `frontend/src/components/ContratosBrowser.jsx`. App.jsx evoluiu `currentView` para `{"upload","notas","contratos"}`. Topbar ganhou 3º link "Contratos".
- [x] Tabela com colunas: Número, Fornecedor (sigla), UF, Tranche, Tipo, Valor Contrato (BRL), Valor CDE (BRL), % CDE.
- [x] Barra de filtros: campo `q` (numero+sigla), select de UF (nome completo via `lib/ufNomes.js`), select de tipo, select de tranche, toggle "apenas com valor definido", toggle "incluir inativos". Opções dos selects derivam de uma resposta sem filtros no mount (evita dependência circular).
- [x] Tabela usa `table-layout: fixed` e ellipsis. Debounce 300ms + `AbortController` no fetch (reusa padrão do `NfsBrowser`).
- [x] **F3-c upgrade (2026-05-13)**: clique na linha dispara `POST /api/session/contrato` + leva para Upload. Linhas com `ativo=false` ficam visualmente desabilitadas (`text-muted` + cursor `not-allowed`). Tooltip explica o comportamento.
- [x] **Cache de sessão por contrato (2026-05-13)**: trocar de contrato preserva o snapshot dos slices `entries` e `upload.results` para retomada. Logout zera tudo. Badge "Último upload {relativo}" no header do card de Processamento.

### Critérios de Sucesso
- `?uf=SP` retorna apenas SP; `?tipo_contrato=MLA` retorna apenas MLA; `?com_valor=true` retorna apenas com valor > 0.
- Filtros combinados (`?uf=SP&tipo_contrato=LPT`) funcionam como `AND`.
- Tela renderiza sem erros com base vazia.
- Sem params, response idêntica ao comportamento atual (regressão — ContratoSelector e NfsBrowser não quebram).

### Decisões registradas (2026-05-12)
- **F3-a**: acesso por **link no topbar** (3º ao lado de Upload/Notas). Sem menu de tabs separado — esse foi removido em 2026-05-12 por poluição visual.
- **F3-b**: inativos ocultos por default; toggle "incluir inativos" disponível.
- **F3-c**: ~~clique na linha não faz nada~~ → **revisada em 2026-05-12**: clique numa linha **dispara `POST /api/session/contrato` e leva o usuário para a aba Upload com o contrato escolhido como ativo na sessão**. Equivalente a abrir o `ContratoSelector` + confirmar, sem precisar passar pelo logout. Linhas com `ativo=false` ficam visualmente desabilitadas (cor `text-muted` + cursor `not-allowed`) e não respondem ao clique. Tooltip informa o comportamento. Decisão tomada após uso real revelar que abrir a tabela de contratos sem poder selecionar é uma cobertura morta.
- **F3-d**: ordem default por `numero` string (lexicográfico). Mantém padrão atual do endpoint, consistente com ContratoSelector e dropdown da Notas. Headers clicáveis ficam para fase futura se aparecer demanda.
- **F3-e**: export CSV/XLSX **deferido**. Se necessário, reusa `frontend/src/lib/exportExcel.js` adicionando variante `exportContratos`.

---

## F3b — Consulta de NFs por contrato

**Objetivo**: tela dedicada para consulta das NFs persistidas no banco filtradas por contrato. Operador escolhe contrato em dropdown e filtra por colunas da `nf_entries` (número, data emissão, fornecedor, CNPJ, valor, tipo, descrição). Feature irmã de F3 (browser de contratos) — F3 lê a base estática `contratos`, F3b lê `nf_entries` dinâmico. Spec visual completa em `planning/F3b-consulta-nfs.html`.

### Subetapas
- [ ] Estender `GET /api/nf-entries` com query params opcionais: `?contrato_id=&q=&data_inicio=&data_fim=&valor_min=&valor_max=&tipo_nota=`. Todos defaults `None`; sem param preserva comportamento atual da tabela principal de upload. `q` faz `ILIKE %x%` em `numero_nf | fornecedor | cnpj | descricao` via `OR`. Demais filtros combinam por `AND`. Intervalos de data/valor inclusivos. Ordenação default por `data_emissao DESC`.
- [ ] Tela "Notas" no frontend, 3ª aba ao lado de Upload e Contratos. Link no topbar também.
- [ ] Dropdown de contrato no topo da tela, populado por `GET /api/contratos`. Formato do item: `sigla · tranche · tipo (numero)`.
- [ ] Barra de filtros: campo texto livre (busca em `q`), intervalo de data emissão, intervalo de valor total, select de `tipo_nota`. Debounce de 300ms + `AbortController` no fetch.
- [ ] Tabela com colunas: Número, Emissão, Fornecedor, CNPJ, Descrição, Valor total, Tipo. `table-layout: fixed` + ellipsis (regras de design).
- [ ] Footer da tabela exibe contagem de NFs filtradas + soma do `valor_total` (formato BRL via `Intl.NumberFormat('pt-BR')`).
- [ ] Empty state quando sem contrato selecionado: "Selecione um contrato para ver as NFs". Hint adicional quando contrato escolhido mas zero NFs: "NFs anteriores à F2 podem não estar associadas ao contrato".

### Critérios de Sucesso
- `?contrato_id=X` retorna apenas NFs com `nf_entries.contrato_id = X`.
- `?q=instalação` retorna NFs cuja `descricao` / `numero_nf` / `fornecedor` / `cnpj` contenham "instalação" (case-insensitive).
- `?data_inicio=2024-01-01&data_fim=2024-12-31` filtra inclusivamente.
- `?valor_min=1000&valor_max=5000` filtra inclusivamente.
- Combinação `?contrato_id=X&q=Y&data_inicio=Z` funciona como `AND`.
- Sem params, response idêntica ao comportamento atual da tabela de upload (regressão obrigatória).
- Tela renderiza sem erros quando contrato sem NFs (empty state com hint).
- Soma do footer bate exatamente com a soma das NFs visíveis.

### Decisões registradas (2026-05-11)
- **F3b-a**: trocar contrato no dropdown **NÃO** reseta os outros filtros — preserva o "estado mental" do operador (intervalo de data, busca textual). Botão "limpar filtros" disponível como reset explícito.
- **F3b-b**: ao entrar na aba "Notas", se houver contrato ativo na sessão (selecionado para upload), o dropdown **pré-seleciona** esse contrato. Operador pode trocar livremente.
- **F3b-c**: F3b é feature distinta de F3. F3 = browser de contratos (planilha estática); F3b = consulta de NFs filtrada por contrato (dinâmica, lê `nf_entries`).

---

## F4 — Visualizar e baixar PDF persistido ✅ concluída em 2026-05-12

**Objetivo**: em painéis que listam notas, abrir o PDF original no browser ou baixar, a partir do arquivo já em `backend/banco_de_nf/<batch_id>/`. Spec visual completa em `planning/F4-pdf-original.html`.

### Subetapas
- [x] Migration `0003_f4_pdf_paths`: adicionar `upload_files.stored_filename` (TEXT nullable) e `nf_entries.upload_file_id` (FK → `upload_files.id`, nullable). **Backfill agressivo** (Decisão F4-a): durante o upgrade, `os.listdir` em cada batch_dir e popular `stored_filename` para todos os arquivos pré-F4 que existem em disco. — Resultado: 339/339 `upload_files` com `stored_filename` populado.
- [x] `backend/app/storage.py` com função `get_pdf_path(upload_file, base_dir)`: retorna `Path` resolvido via `stored_filename`; fallback heurístico só para casos onde o backfill falhou.
- [x] `save_uploaded_pdf` (em `server.py`) passa a gravar `stored_filename` (UUID4 em disco, separado de `original_filename`) no `UploadFileRecord`. `create_nf_entry` recebe e grava `upload_file_id`. — Refactor: `UploadFileRecord` criado upfront (status `"processando"`) para que FK funcione no INSERT das `nf_entries`.
- [x] `GET /api/uploads/files/{upload_file_id}/pdf` (autenticado). Localiza o `upload_files` via JOIN com `upload_batches` + `users` filtrando `user.username == current_user` (impede vazamento entre usuários). `FileResponse` com `application/pdf`, `Content-Disposition: inline` (default) ou `attachment` se `?download=true`. Cabeçalho `X-Content-Type-Options: nosniff`.
- [x] Expor `upload_file_id` no payload de `GET /api/nf-entries` (`serialize_nf_entry` + `NfEntryResponse`).
- [x] Tabela de Notas (F3b) ganha coluna "PDF" com ícones 👁 (abrir em nova aba) e ⬇ (download). NFs sem `upload_file_id` (legacy ou pré-F4) → botões disabled com tooltip "PDF não disponível (anterior à F4)". **Tabela_persistida da Upload NÃO recebe os ícones** (Decisão F4-b).
- [x] Testes em `tests/test_pdf_endpoint.py`: sem auth → 401; id inexistente → 404; id válido → 200 com `application/pdf`; usuário A não enxerga PDF de usuário B (404, não 403, para não vazar existência); arquivo removido do disco → 404; `?download=true` retorna `attachment` com `original_filename`; fallback heurístico para legacy sem `stored_filename`.

### Critérios de Sucesso
- ✅ Browser renderiza PDF inline em nova aba.
- ✅ Com `?download=true`, força download com `original_filename` correto.
- ✅ Arquivo servido é byte-a-byte idêntico ao enviado.
- ✅ Migration backfill cobre todos os batches existentes em `banco_de_nf/`.

### Decisões registradas (2026-05-12)
- **F4-a**: backfill **agressivo na migration** (Opção A) — `0003_f4_pdf_paths` faz `os.listdir` em cada batch_dir e popula `stored_filename` para todos os arquivos pré-F4 já no disco. Resolver `get_pdf_path` fica simples (sem lógica de fallback no caminho quente), gasta IO uma vez na deploy.
- **F4-b**: ícones de PDF **somente na aba Notas**, não na tabela_persistida da Upload. Reforça a separação "Upload = enviar, Notas = consultar". Upload fica focada na função de envio.
- **F4-c**: F4 **não toca em F3** (browser de contratos, ainda não implementada). Quando F3 for feita, ela integra a navegação contrato → notas filtradas reusando `/api/nf-entries?contrato_id=…` (endpoint já estendido em F3b).
- **F4-d**: NFs pré-F4 (criadas antes da migration 0003) **NÃO recebem `upload_file_id`** e ficam com botões PDF desabilitados — **limitação aceita** em 2026-05-12. Razão: o schema antigo não armazenava a relação NF→arquivo, e o backfill via timestamp/contrato seria frágil em batches grandes (existe 1 batch com 126 PDFs no banco hoje, onde timestamps próximos inviabilizam o match). PDFs continuam **acessíveis em disco** via `upload_files.stored_filename` — só a navegação direta NF → PDF é que não funciona para legacy. Daqui pra frente, 100% dos uploads novos têm `upload_file_id`. Diagnóstico no momento da decisão: 150 NFs no banco, 2 com `upload_file_id`, 148 sem.

---

## F6 — Totalizadores no painel de upload

**Objetivo**: card no painel de upload mostrando, para o contrato ativo na sessão, o quanto já foi enviado vs. valor de contrato e CDE, com progresso visual.

### Subetapas
- [ ] `GET /api/contratos/{contrato_id}/totais` retorna:
  ```json
  {
    "contrato_id": "...",
    "numero": "ECFS 101/2005",
    "valor_contrato": 2143980.00,
    "valor_cde": 1715180.00,
    "participacao_cde": 0.8,
    "soma_nfs_enviadas": 980000.00,
    "pct_enviado_sobre_contrato": 0.4573,
    "pct_enviado_sobre_cde": 0.5713,
    "total_nfs_no_banco": 48
  }
  ```
  `soma_nfs_enviadas` = `SUM(nf_entries.valor_total)` filtrado por `contrato_id`. `total_nfs_no_banco` = `COUNT(DISTINCT nf_entries.numero_nf)` no mesmo filtro.
- [ ] Card no painel de upload (antes da seleção de arquivos): duas barras horizontais (vs. contrato; vs. CDE) + contagem de NFs distintas. Valores formatados como BRL (R$ X.XXX.XXX,XX).
- [ ] Recarrega ao montar e após cada `batch_done` no SSE.
- [ ] Quando `valor_contrato = 0`, exibir "Valor contratual não definido" e retornar `pct_*` como `null` (sem divisão por zero).

### Critérios de Sucesso
- 401 sem sessão; 404 para contrato inexistente.
- `valor_contrato = 0` → `pct_enviado_sobre_contrato = null` e UI exibe mensagem.
- Card atualiza após upload sem reload da página.
- `soma_nfs_enviadas` bate com soma manual via SQL direto no banco.

---

## F1 — Login real com confirmação por e-mail

**Objetivo**: substituir credenciais fixas por cadastro real com e-mail, hash de senha, confirmação por token e reset de senha.

### Subetapas
- [ ] Adicionar colunas de auth em `users` (ver schema transversal).
- [ ] `POST /api/auth/register` body `{email, password}`. Cria usuário com `email_confirmed=False`, gera `confirmation_token` (UUID seguro), `token_expires_at = now() + 24h`, envia e-mail com link `GET /api/auth/confirm?token=...`.
- [ ] `GET /api/auth/confirm?token=...` valida token + expiração, define `email_confirmed=True`, limpa o token.
- [ ] `POST /api/auth/login` exige `email_confirmed=True`. Caso contrário retorna 403 com mensagem orientando confirmação.
- [ ] `POST /api/auth/forgot-password` body `{email}` gera `reset_token`, `reset_expires_at = now() + 1h`, envia e-mail.
- [ ] `POST /api/auth/reset-password` body `{token, new_password}` valida e atualiza hash.
- [ ] Hash com `passlib[bcrypt]`. **Decisão pendente**: bcrypt ou argon2? (Decisão #2).
- [ ] Manter usuário `user`/`password` apenas se `DEBUG=true` (não em produção).
- [ ] Telas no frontend: registro, "verifique seu e-mail", login (ajustar mensagem de erro), "esqueci minha senha", "redefinir senha".

### Critérios de Sucesso
- Registro com e-mail duplicado → 409.
- Login sem confirmação de e-mail → 403.
- `confirm?token=EXPIRADO` → 400 com mensagem de expiração.
- Login com confirmado e senha correta → 200 + sessão.
- E-mail enviado para o endereço (verificável em sandbox SMTP — Decisão #1).
- Reset com token válido altera senha; login com a antiga → 401.

---

## F7 — E-mails transacionais

**Objetivo**: reutilizar a infra SMTP da F1 para enviar (a) confirmação de upload bem-sucedido para o usuário; (b) alerta de erro de parser para o admin quando algum arquivo falha com `erro_parsing`.

### Subetapas
- [ ] Isolar envio em `backend/app/email_service.py` com `send_email(to, subject, body_html)` usando `aiosmtplib` ou `smtplib` via `asyncio.to_thread`.
- [ ] Template de sucesso: nome do contrato, qtd. de notas inseridas, data/hora, link para consulta.
- [ ] Template de erro de parser: destinatário em `ADMIN_EMAIL` (env), corpo com `batch_id`, `original_filename` e `parser_error`.
- [ ] Disparar sucesso ao final do gerador SSE (evento `batch_done`) se ao menos um arquivo for `processado`.
- [ ] Disparar erro ao detectar `status = erro_parsing` em `upload_files`, ao final do processamento de cada arquivo.
- [ ] Envio nunca bloqueia o stream SSE — usar `asyncio.to_thread` ou `BackgroundTasks`.

### Critérios de Sucesso
- Upload com ≥ 1 nota inserida → usuário recebe e-mail com resumo correto.
- Upload com `erro_parsing` → admin recebe e-mail com nome do arquivo e o erro.
- Falha de SMTP não derruba o endpoint — erro logado, SSE continua.
- Em dev sem `SMTP_HOST` configurado, envio é silenciosamente ignorado (sem exception).

---

## Migração do Parser: `main_v9.py` → parser v10 (`backend/app/main.py`)

**Estado atual (2026-05-05)**: a cópia dos arquivos do parser v10 (`main.py`, `ocr_reader.py`, `cnpj_lookup.py`, `description_cleaner.py`, `contrato_config.py`) para `backend/app/` já foi feita. O FastAPI app foi movido para `backend/app/server.py` para liberar `main.py` ao parser. `parser_adapter.py` já aponta para o novo `main.py`. A versão anterior está em `main_v9.deprecated.py` apenas como referência histórica.

**Pendência (F8)**: o parser v10 ainda **não roda non-interactive** — chama `selecionar_contrato(...)` no nível de módulo (`main.py:85`) e `_solicitar_campo_humano` (`main.py:97`) em 14 pontos do fluxo. Subprocess sem TTY trava nesses `input()` até o timeout de 180s. F8 resolve isso (Decisão #8).

### Regras gerais de refactor — preservar versão de desenvolvimento

O `main.py` deste repositório é uma **cópia** do parser que evolui em outra pasta (`leitor_de_pdf/main.py`). O usuário desenvolve melhorias no parser fora deste projeto e periodicamente substitui o `main.py` aqui pela nova versão. Para que esse fluxo não quebre o tracking, qualquer adaptação para produção deve seguir estas regras:

1. **Não apagar funções, variáveis ou constantes existentes.** Ex.: `_solicitar_campo_humano` (linha 97), `arquivo_investigado` (linha 28), `MODO_LLM` (linha 31). Mesmo se ficarem inúteis em produção, permanecem no arquivo.
2. **Adicionar a versão de produção logo abaixo da função/bloco de desenvolvimento**, com comentário marcando a fase. Ex.: `# FASE PROD (web) — substitui _solicitar_campo_humano em modo non-interactive`.
3. **Comentar (sem deletar) chamadas que mudam de comportamento.** Cada chamada original fica como comentário acima da chamada de produção:
   ```python
   # FASE DEV (terminal):
   # df_service_description = _solicitar_campo_humano("descricao", contexto=nome_saida)
   # FASE PROD (web):
   df_service_description = _registrar_pendencia("descricao", contexto=nome_saida)
   ```
4. **Registrar toda mudança em `docs/MAIN_PROD_CHANGES.md`** — changelog canônico das adaptações de produção sobre o `main.py` de desenvolvimento. Quando uma nova versão do parser chegar, esse arquivo é o roteiro para reaplicar as adaptações rapidamente.
5. **Comportamento DEV vs PROD** pode ser controlado por flag `--non-interactive` ou env var, mas a coexistência das duas versões no mesmo arquivo é a regra dura — não substituir, não deletar.

Esta seção pode mudar quando novas versões do parser chegarem (ex.: integração com IA, novos campos extraídos). Sempre revisar antes de iniciar nova rodada de adaptação.



### O que o novo parser produz

`default_nf_template` por linha extraída:

```
descricao, ncm, quant, preco_unitario, numero_nf, tipo_nota,
data_emissao, cnpj, fornecedor, valor, contrato
```

O campo `contrato` vem de `selecionar_contrato()` (em `contrato_config.py`) e retorna:

```python
{
  "contrato": "ECFS 101/2005 - CPFL,SP - 2ª Tranche",
  "numero_contrato": "ECFS 101/2005",
  "valor_contrato": 2143980,
  "valor_cde": 1715180,
}
```

Com a F2, `contrato_id` vem da sessão — o `LegacyParserAdapter` precisa receber o número do contrato como parâmetro e injetá-lo nas linhas.

### Interface atual: somente CLI

`backend/app/main.py` executa código de topo (inclusive `CONTRATO = selecionar_contrato(...)` em `main.py:85`, que abre menu interativo no terminal). Não pode ser importado direto. Subprocess continua sendo a solução, mas requer passar o número do contrato como argumento ou env var para que `selecionar_contrato()` não entre em modo interativo. F8 introduz flags `--contrato NUMERO --input-dir PATH --output-dir PATH --non-interactive` para suprimir o modo terminal.

**Caminho proposto**: criar `leitor_de_pdf/run_parser.py` aceitando `--contrato NUMERO --input-dir PATH --output-dir PATH --non-interactive`. O `LegacyParserAdapter` é atualizado para invocar esse wrapper.

### Dependências externas

O novo parser importa `ocr_reader`, `cnpj_lookup`, `description_cleaner`, `contrato_config`. Esses módulos vivem em `leitor_de_pdf/` e não em `backend/`. Estratégia mais segura: manter o parser em seu diretório e invocá-lo via subprocess com Python do venv correto, ou containerizá-lo separadamente. **Decisão pendente** #7.

### Impacto na `business_key` e schema

Campos extraídos pelo novo parser são compatíveis com a `business_key` atual. Nenhuma mudança necessária. Única adição em `nf_entries` motivada pela migração: `contrato_id` (já documentado).

### Risco principal: interatividade

`main.py` chama `input()` quando campos obrigatórios não são extraídos (`cnpj`, `numero_nf`, `data_emissao`, `fornecedor`). Em subprocess sem TTY isso bloqueia. O timeout de 180s é a única proteção atual. O wrapper deve transformar `_solicitar_campo_humano()` em exceção em modo `--non-interactive` (Decisão #8).

---

## Decisões Pendentes

Lista que precisa ser respondida antes da implementação começar.

1. **Provedor SMTP e ambiente de dev** *(resolvida — 2026-05-05)*: SMTP via env vars (`SMTP_HOST`/`PORT`/`USER`/`PASSWORD`/`FROM`). Provedor inicial: Hostinger (`smtp.hostinger.com:587` STARTTLS), domínio Hostinger próprio. Volume estimado ≤10 e-mails/h — folgado vs. limites do plano. Pré-requisito de deploy: SPF + DKIM + DMARC configurados no DNS Hostinger antes do primeiro envio. Migração futura para servidor institucional = troca de env vars, sem alteração de código.
2. **Algoritmo de hash de senha** *(resolvida — 2026-05-05)*: **bcrypt** via `passlib[bcrypt]`, cost 10. `CryptContext` configurado com `schemes=["argon2", "bcrypt"]`, `default="bcrypt"`, `deprecated=["bcrypt"]` para permitir migração automática para argon2id quando a instituição definir o algoritmo institucional (basta trocar o default e adicionar `argon2-cffi` ao `requirements.txt` — logins bem-sucedidos re-hasheiam silenciosamente). Esqueleto em `backend/app/security.py` (`hash_password`, `verify_password`, `needs_rehash`). Política mínima: senha ≥ 10 caracteres, sem regras de complexidade obrigatórias (alinhado a OWASP 2024 / NIST SP 800-63B). Truncamento bcrypt em 72 bytes a documentar no endpoint `POST /api/auth/register`.
3. **Migrations** *(resolvida — 2026-05-05)*: **Alembic**, executado automaticamente via `alembic upgrade head` no `start.ps1` antes de subir o backend (não no `lifespan` — separa "alterar schema" de "subir app" e evita race condition em deploys com múltiplas réplicas no futuro). Configuração:
   - `alembic init` no diretório `backend/`, com `alembic/env.py` lendo `DATABASE_URL` do mesmo lugar que `backend/app/db.py` (sem duplicar configuração).
   - Primeira migration = **baseline** gerada via autogenerate contra banco vazio, capturando o schema atual (`users`, `upload_batches`, `upload_files`, `nf_entries`).
   - Migrations subsequentes uma por feature (F1: colunas de auth em `users`; F2: tabela `contratos` + `upload_batches.contrato_id` + `nf_entries.contrato_id`; F4: `nf_entries.upload_file_id`).
   - **Testes não usam migrations**: `conftest.py` continua chamando `init_db()` (`create_all`) — testa o estado final do schema, não o histórico. Prática padrão.
   - `start.ps1` ganha `alembic upgrade head` antes do `docker compose up`.
4. **Storage de PDFs** *(resolvida — 2026-05-05)*: **Filesystem local** em `backend/banco_de_nf/<batch_id>/<stored_filename>` (configurável via `UPLOAD_STORAGE_DIR`). Object storage (S3/MinIO) fica adiado até o servidor institucional definir suas políticas — investir agora em infra para um ambiente semi-produção (Hostinger) corre risco de virar trabalho jogado fora. Ajustes para preparar migração futura sem custo agora:
   - **F4**: acessar PDF via função abstrata `get_pdf_path(upload_file)` em `backend/app/storage.py` (a criar quando F4 entrar), em vez de espalhar `Path(UPLOAD_STORAGE_DIR) / ...` pelos endpoints. Migração futura troca uma função.
   - **Schema**: garantir que `upload_files` tem `stored_filename` (UUID ou nome real no disco) além de `original_filename`, para que o caminho seja reconstrutível mesmo movendo o diretório base. Confirmar/adicionar quando F4 entrar.
   - **Backup operacional (TODO)**: rsync semanal de `UPLOAD_STORAGE_DIR` para destino externo (B2/Drive/VPS secundário). Piso de proteção contra perda do servidor. Não automatizado agora — registrado como tarefa de ops.
5. **Username vs. e-mail no login** *(resolvida — 2026-05-05)*: **E-mail é o identificador único de login.** `username` descontinuado no fluxo novo. Implicações:
   - `users.email VARCHAR(255) UNIQUE NOT NULL` (já previsto no schema de F1).
   - `users.username` mantido por compat com o seed legado `user`/`password` (apenas em `DEBUG=true`); migration de F1 deve torná-lo `nullable=True` para não bloquear cadastros novos. Coluna pode ser removida em migration futura quando o legado for descomissionado.
   - `POST /api/auth/register` body `{email, password}` — sem `username`.
   - `POST /api/auth/login` body `{email, password}` — sem `username`.
   - Display no topbar: usar `email` (ou parte antes do `@`). Não há campo `display_name` separado nesta fase — pode ser adicionado depois se houver pedido específico.
   - Seed legado `user`/`password` permanece **somente** com `DEBUG=true` (já documentado no `CLAUDE.md`).
6. **Persistência do contrato selecionado** *(resolvida — 2026-05-05)*: **Opção A — somente sessão, sem persistência.** A cada login novo, sessão recomeça do zero e usuário passa pela tela de seleção de contrato. Razão: para a fase Hostinger (semi-produção, poucos usuários, alguns alternando entre contratos no mesmo dia), pré-selecionar último contrato é complicação desnecessária e pode induzir upload no contrato errado. Evolução futura (Opção B — pré-seleção com confirmação, Opção C — pular tela) fica **parqueada para decisão dos superiores institucionais** quando o sistema migrar para o servidor institucional. Registrada também pelo usuário em `planning/PENDING_DECISIONS.md` para essa rodada futura.
7. **Container do parser novo** *(resolvida — 2026-05-05)*: **Opção A1 aplicada de fato** — parser v10 vive em `backend/app/main.py` junto dos módulos irmãos (`ocr_reader.py`, `cnpj_lookup.py`, `description_cleaner.py`, `contrato_config.py`), na mesma imagem Docker do backend. Findings da varredura:
   - **Dependências Python**: 100% cobertas pelo `requirements.txt` atual (`pdfplumber`, `pandas`, `numpy`, `requests`, `tqdm`, `pytesseract`, `pdf2image`, `openpyxl`). Nada novo a instalar via pip para o parser rodar — só o `passlib[bcrypt]` adicionado pela Decisão #2.
   - **`python-dotenv`**: importado opcionalmente em `description_cleaner.py:8-12` (try/except). Não bloqueia se ausente. Em Docker as envs entram direto pelo `environment:` do compose, então não é necessário; em uvicorn local fora do Docker, ajudaria carregar `.env` automaticamente. Adiar até virar problema real.
   - **LLM**: `description_cleaner.py` chama OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) via REST. Lê `OPENROUTER_API_KEY` e `OPENROUTER_MODEL` (default `openai/gpt-oss-120b`) do ambiente. Sem key, retorna texto bruto graciosamente. Modelo é configurável por env var.
   - **Cache CNPJ offline**: `backend/app/cnpj.json` (cache de consultas) e `backend/app/block_cnpj.json` (lista de bloqueio). `cnpj_lookup.py` faz chamada externa quando o CNPJ não está em cache; cache é populado ao longo do uso.
   - **Estado atual do LLM cleaner**: **desativado em produção**. `backend/app/main.py:2000` tem a chamada `cleaner.batch_clean(...)` comentada por questão de performance (~4-5min para 135 itens conforme `parser_IA.md`). Refactor de performance do `description_cleaner` é trabalho do usuário, fora do escopo das 7 features.
   - **`contexto_programa.json`**: arquivo esperado pelo cleaner em `_CONTEXTO_PATH = "contexto_programa.json"` (relativo ao cwd). Ausente hoje; cleaner trata como warning + contexto vazio. Não bloqueia, mas ao reativar o LLM esse arquivo precisa ser preenchido.

   **Novas envs a documentar no `CLAUDE.md`** (quando o cleaner voltar): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`.
8. **Modo não-interativo do parser** *(resolvida — 2026-05-05)*: **Híbrido** — dois caminhos distintos baseados na natureza do erro.

   **Tipo 1 — campo não extraído** (14 chamadas de `_solicitar_campo_humano` em `main.py`: linhas 1024, 1030, 1191, 1206-1210, 1923, 1928, 1945, 1951, 1957, 1963, 1988):
   - Parser em modo non-interactive **não chama `input()`**. Em vez disso, escreve `pending_rows.json` no temp dir com `{row_index, prefilled_fields, missing_fields, original_filename}` e para de processar o batch (`SystemExit` com código específico ou retorno controlado).
   - Backend persiste em nova tabela `nf_pending` (`upload_file_id, prefilled_json, missing_fields_json, status: aguardando|resolvido|abandonado, created_at, resolved_at`).
   - SSE emite evento novo `file_pending_input` com payload da pendência.
   - Frontend abre modal: campos pré-preenchidos visíveis, campos faltando como inputs obrigatórios. **Bloqueia o batch inteiro** — arquivos seguintes não começam a processar.
   - **Granularidade dentro de uma única NF**: se qualquer produto/serviço da NF tem campo faltando, **a NF inteira vai para `nf_pending`** — outros produtos da mesma NF não entram em `nf_entries` parcialmente. Modal apresenta a NF inteira para preenchimento. Mantém invariante "linha em `nf_entries` = NF completa".
   - `POST /api/uploads/pending/{nf_pending_id}/resolve` recebe os campos preenchidos, faz merge com `prefilled_json`, computa `business_key`, insere em `nf_entries`, marca pendência como `resolvido`. Backend retoma o processamento do batch.
   - **Abandono = interpretação leve**: se a sessão cai/usuário fecha, backend marca `upload_batches.status = abandonado` após timeout (a definir em F8). Linhas já em `nf_entries` permanecem. Re-submissão dos PDFs deduplica automaticamente via `business_key`. **Sem rollback.**

   **Tipo 2 — estrutura interna do parser quebrou** (17 `raise ValueError` em `main.py`: linhas 687, 761, 903, 1008, 1046, 1164, 1168, 1235, 1309, 1317, 1319, 1343, 1369, 1381, 1558, 1599, 1901, mensagens tipo "Não conseguiu dividir a tabela em 3 partes"; linha 1599 é fallback de "campos não preenchidos" que pelo design é Tipo 2 — exige investigação manual com PDF anexado):
   - Arquivo cai em `erro_parsing` direto. **Sem modal** — não há campo único para preencher.
   - F7 envia e-mail a `ADMIN_EMAIL` com **PDF original anexado** (lido de `backend/banco_de_nf/<batch_id>/<filename>.pdf`) + `stderr`/`stdout` do parser + nome do arquivo.
   - Tratado como bug do parser — exige update do script para aquela estrutura específica de NF.
   - Batch **continua processando os demais arquivos** (não bloqueia, ao contrário do Tipo 1).

   **Schema implication (executar em F8):**
   - **Todas as 11 colunas** de `default_nf_template` em `nf_entries` viram `NOT NULL` (descricao, ncm, quant, preco_unitario, numero_nf, tipo_nota, data_emissao, cnpj, fornecedor, valor, contrato). Linha com qualquer campo `""` ou `None` é falha grave do parser e não pode entrar no banco.
   - Verificar `backend/app/models.py` antes de gerar a migration; pode exigir backfill de linhas históricas que tenham NULL antes do `ALTER COLUMN ... SET NOT NULL`.
   - Eliminar todos os `or ""` que envolvem chamadas a `_solicitar_campo_humano` no parser (linhas 1206-1210 e similares) — string vazia deve ser tratada como ausência e ir para a fila de pendência (Tipo 1).

   **Regra de refactor**: ver seção "Regras gerais de refactor — preservar versão de desenvolvimento" em "Migração do Parser" acima. Aplica-se a todo refactor de `main.py`, não só a `_solicitar_campo_humano`. Toda adaptação de F8 sobre `main.py` deve ser registrada em `docs/MAIN_PROD_CHANGES.md`.
9. **Sessões pré-F2 sem contrato** *(resolvida — 2026-05-05)*: **Opção A — backend retorna 400, frontend faz o redirect.** Razão: rota da UI é responsabilidade do frontend; backend prescrever `redirect` no payload acopla API à UI.
   - **`HTTP 400 {"detail": "Nenhum contrato selecionado."}`** quando endpoint que exige contrato é chamado sem `contrato_id` na sessão.
   - **Dependency centralizada** (`require_contrato`) em `backend/app/dependencies.py` (a criar em F2) ou `backend/app/security.py`. Lê `request.session.get("contrato_id")`; se ausente, levanta `HTTPException(400, "Nenhum contrato selecionado.")`. Endpoints como `POST /api/uploads`, `GET /api/contratos/{id}/totais` (F6) usam `Depends(require_contrato)` e recebem o `contrato_id` já validado.
   - **Frontend** chama `GET /api/session/contrato` no boot pós-login. Se 404, renderiza tela de seleção (rota React `/contratos`). O 400 do upload serve só como rede de segurança contra bug/estado inconsistente.
10. **Validação de magic bytes em PDFs** *(deferida — 2026-05-05, fora do escopo das 7 features)*: validação de `%PDF-` nos primeiros bytes não será implementada no backend deste ciclo. **Virá junto com a próxima versão do `main.py` de desenvolvimento** (a que trará o refactor do `description_cleaner` / `parser_IA`). A responsabilidade de detectar "arquivo não é PDF válido" passa para o próprio parser ou para o módulo OCR upstream — não para o backend FastAPI. Quando essa versão chegar, registrar a adaptação em `docs/MAIN_PROD_CHANGES.md` se houver mudança em `parser_adapter.py` ou no fluxo de status (`rejeitado` vs `erro_parsing`).
