# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Guidelines governam processo, não reduzem critérios aprovados

**Estas guidelines descrevem como trabalhar, não definem o que conta como pronto.**

Em caso de tensão entre uma guideline aqui e um critério explícito de `planning/PLAN.md` ou `planning/DEFINITION_OF_DONE.md`, **o plano vence**. Especificamente:

- "No features beyond what was asked" (seção 2) **não** autoriza pular critérios negativos do DoD (auth, contrato ausente, id inexistente, etc.) sob argumento de "não foi pedido explicitamente". Critérios transversais são parte implícita de toda feature.
- "Surgical changes" (seção 3) **não** autoriza entregar feature em uma camada quando o critério da feature cruza camadas (ver DoD §3 — Unidade mínima cruzando camadas).
- "If uncertain, ask" (seção 1) **não** autoriza interromper task clara do plano por dúvida sobre detalhe resolvível lendo o repositório.

A hierarquia é: **`PLAN.md` (escopo e critérios) > `DEFINITION_OF_DONE.md` (limiar de pronto) > este documento (processo)**. Uma guideline nunca é justificativa para entregar abaixo do DoD.

## 6. Forma de perguntar

**Perguntar é caro para o dono. Pergunta sem contexto custa duas rodadas em vez de uma.**

Antes de interromper o trabalho com uma pergunta, distinguir:

- **Dúvida resolvível** — a resposta está no repositório (código, `CLAUDE.md`, `PLAN.md`, `docs/`, git log). **Resolver lendo, não perguntando.**
- **Dúvida bloqueante** — decisão irreversível, ambiguidade de escopo do plano, ou trade-off institucional. **Perguntar.**

Quando a dúvida é bloqueante, a pergunta deve trazer:

1. **Contexto** — o que está sendo implementado e onde a dúvida apareceu (arquivo:linha quando aplicável).
2. **Opções** — pelo menos duas alternativas concretas, com consequências de cada uma.
3. **Recomendação** — qual opção parece melhor e por quê.

Exemplo ruim: "Como devo tratar erros aqui?"

Exemplo bom: "Em `parser_adapter.py:142`, quando o subprocess do parser estoura timeout (180s), tenho duas opções: (a) registrar o arquivo como `erro_parsing` e continuar o batch, ou (b) abortar o batch inteiro. Recomendo (a) porque o usuário já viu o evento `file_parsing` no SSE e cancelar o batch agora invalida arquivos já processados. Confirma?"

Pergunta sem contexto + opções + recomendação volta como pedido de mais informação. Não economiza turno; gasta dois.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes — but never block clear plan tasks under cover of caution.
