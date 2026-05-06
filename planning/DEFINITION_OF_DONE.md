# DEFINITION_OF_DONE.md — Critérios transversais de conclusão

Checklist única aplicada a **toda** feature do roadmap (F1–F8). É o conteúdo da **Fase D** definida em `PLAN.md` → "Modelo de execução por fases". Uma feature só está concluída quando todos os itens aplicáveis estão marcados.

> Hierarquia: este documento define **o que conta como pronto** em geral. Critérios de conclusão específicos por feature (ex.: "F8 concluída quando…" em `PLAN.md`) são **adicionais**, nunca substitutivos.

---

## 1. Critérios técnicos (sempre obrigatórios)

- [ ] **Backend tests** — `pytest` passa a partir de `backend/`. Testes novos cobrem o caminho feliz e os negativos do item 5 abaixo.
- [ ] **Schema** — se houve mudança em `models.py`:
  - [ ] migration Alembic criada (`alembic revision --autogenerate -m "..."` revisada manualmente)
  - [ ] smoke `alembic upgrade head` rodou contra banco vazio sem erro
  - [ ] se há dados legados que violariam novas constraints, migration tem etapa de backfill
- [ ] **Frontend build** — se houve mudança em `frontend/src/`:
  - [ ] `npm run build` termina sem erro nem warning não-trivial
  - [ ] `backend/app/static/assets/app.js` e `app.css` foram regerados
  - [ ] smoke manual no browser cobre o caminho feliz da feature
- [ ] **Parser** — se `backend/app/main.py` foi tocado:
  - [ ] entrada em `docs/MAIN_PROD_CHANGES.md` com **motivo**, **before/after** do comportamento, e **teste associado** (não basta comentar a chamada antiga)
  - [ ] regra de preservação respeitada: nada apagado, marcadores `# FASE DEV` / `# FASE PROD` aplicados
  - [ ] código de topo interativo guardado por `if __name__ == "__main__":` (após F8)

## 2. Documentação

- [ ] `CLAUDE.md` atualizado se a feature mudou: stack, comandos, arquitetura, env vars, ou regras de desenvolvimento.
- [ ] `planning/PROJECT_BUILDING.md` atualizado: feature movida de "em andamento" para "concluída" com data.
- [ ] `planning/PLAN.md` — se a feature tinha checkpoint próprio na seção "Checkpoints de conclusão", marcar atendido.
- [ ] Decisões tomadas durante a implementação (que não estavam no plano original) registradas em `planning/PENDING_DECISIONS.md` ou na seção "Decisões Pendentes" de `PLAN.md`.

## 3. Unidade mínima cruzando camadas

A feature **não** é cirúrgica em uma única camada quando seus critérios cruzam camadas. Para ser considerada concluída:

- [ ] Se há endpoint novo: existe consumidor no frontend **e** teste backend.
- [ ] Se há tela nova: existe endpoint correspondente **e** validação no backend (frontend não é fonte de verdade).
- [ ] Se há tabela nova: existe migration **e** teste que insere/lê **e** consumidor (endpoint ou seed) que justifica a existência.

## 4. Ambiente-alvo declarado

- [ ] Spec da Fase A declarou para qual ambiente a feature mira nesse ciclo: **local/dev**, **Hostinger semi-prod** ou **institucional futuro**.
- [ ] Decisões de segurança/configuração condizem com o alvo declarado (ex.: rate limit é aceitável "depois" se o alvo do ciclo é local; **não** é aceitável adiar se o alvo é Hostinger semi-prod).

## 5. Critérios negativos transversais (obrigatórios em endpoints/telas novas)

Cada endpoint ou tela introduzida pela feature precisa ter sido testada — automatizado quando possível, manual documentado quando não — contra:

- [ ] **Sem autenticação** — endpoint protegido retorna 401, tela protegida redireciona.
- [ ] **Sem contrato na sessão** — endpoint que exige contrato retorna 400 via `require_contrato`. Tela cliente lida com 400/404 redirecionando para `/contratos`.
- [ ] **ID inexistente** — `GET/PATCH /…/{id}` com id que não existe retorna 404, nunca 500.
- [ ] **ID de outro escopo** — usuário autenticado tentando acessar recurso de contrato que não selecionou retorna 404 (não 403 — não vazar existência).
- [ ] **Double-click / duas abas** — POSTs idempotentes ou com proteção contra duplicação. Estado da sessão não corrompe se o usuário abre duas abas.
- [ ] **Refresh no meio do fluxo** — recarregar a página durante upload SSE não cria batch órfão sem status definido.
- [ ] **Sessão expirada** — chamada com sessão expirada retorna 401, frontend redireciona para login sem perda de dados em digitação.

## 6. Logs e observabilidade

- [ ] Endpoints novos logam **erro** (stacktrace + contexto: user_id, batch_id, contrato_id) quando falham com 5xx.
- [ ] Operações sensíveis (login, registro, reset de senha, alteração de contrato) logam **sucesso** com user_id e timestamp para auditoria mínima.
- [ ] Logs **não** vazam senha, token, PDF binário ou e-mail completo em mensagens de erro retornadas ao cliente.

## 7. Aprovação humana (encerra a feature)

- [ ] Dono testou a feature ponta-a-ponta no ambiente declarado (Fase C) e aprovou.
- [ ] Dono revisou o diff final (Fase D) e aprovou.
- [ ] Próxima feature **só** é iniciada após esta aprovação final — sem emenda automática.

---

## Como usar este documento

1. **Ao iniciar a Fase D** de qualquer feature: copiar a checklist deste arquivo para o PR/commit de fechamento (ou para `planning/PROJECT_BUILDING.md` se não houver PR), marcando aplicáveis e justificando os "N/A".
2. **Item N/A precisa de motivo.** "N/A — feature não toca frontend" é aceitável; "N/A — sem tempo" não é.
3. **Critério não atendido = feature não concluída.** Voltar à fase apropriada (B/C) e completar antes de pedir checkpoint final.
4. **Este documento evolui.** Se durante uma feature surge um critério transversal novo (ex.: nova classe de bug recorrente), adicionar aqui em vez de cada feature redescobri-lo.
