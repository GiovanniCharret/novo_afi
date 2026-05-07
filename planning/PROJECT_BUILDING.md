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

## Estado atual do repositório (snapshot 2026-05-05)

### O que já existe e funciona

- Backend FastAPI com upload + persistência + SSE (Partes 1–7 do MVP em `docs/PLAN.md`).
- Frontend SPA monolítica em `frontend/src/App.jsx` com login fictício, upload, tabela, status badges.
- Parser v10 (`backend/app/main.py`) copiado para o repo, junto com `ocr_reader.py`, `cnpj_lookup.py`, `description_cleaner.py`, `contrato_config.py`. Ainda **não roda non-interactive** — F8 vai resolver.
- FastAPI app movida para `backend/app/server.py` (era `main.py` antes da chegada do parser v10).
- `backend/app/security.py` criado com esqueleto de hash de senha (Decisão #2).
- `backend/app/main_v9.deprecated.py` mantido como referência histórica (sufixo torna não-importável).
- 9 das 10 Decisões Pendentes resolvidas; Decisão #10 deferida.

### O que está pendente para começar

- ~~**F5** (limite 550 PDFs/batch): concluída em 2026-05-07.~~
- **F2** (seleção de contrato + tabela `contratos` + seed): próxima na ordem.
- **F1** (auth real + Alembic setup): exige migration do schema, gateway para tudo que depende de auth séria.
- ~~**F8** (refactor non-interactive de `main.py`): desbloqueado em F8a (2026-05-06).~~
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

Após F8a e F5 entregues, a ordem do `planning/PLAN.md` aponta para **F2** (seleção de contrato + tabela `contratos` + seed). F8b (modal + `nf_pending`) está reordenada para entrar entre F6 e F1.




git push --set-upstream origin "banco_nf_com_contratos_filtro"

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