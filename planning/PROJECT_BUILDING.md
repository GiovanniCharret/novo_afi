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

- **F5** (limite 550 PDFs/batch): cirúrgico, sem dependências. Boa primeira entrega.
- **F2** (seleção de contrato + tabela `contratos` + seed): segundo passo natural.
- **F1** (auth real + Alembic setup): exige migration do schema, gateway para tudo que depende de auth séria.
- **F8** (refactor non-interactive de `main.py` + `nf_pending`): pré-requisito lógico para F2 enviar contrato ao parser.

### Arquivos da raiz que **não são** entrypoints

- `base_contratos.json` — fonte de verdade dos contratos. Lido pelo seed em F2.
- `index.html` na raiz (separado de `frontend/index.html`) — vestígio de teste antigo, **não usado** pelo build.
- `.env` — variáveis de ambiente locais. Não comitado.
- `docker-compose.yml` — orquestração local. Entrypoint é o backend container.

### Próxima tarefa concreta proposta

Ainda não decidida pelo dono. Candidatos em ordem recomendada (de `planning/PLAN.md`): F5 → F2 → F3 → F4 → F6 → F1 → F7. F8 pode entrar antes de F2 (necessário para o subprocess do parser não travar em `input()`).




