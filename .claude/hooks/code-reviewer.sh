#!/usr/bin/env bash
# ============================================================================
# Hook: code-reviewer (Stop)
# ----------------------------------------------------------------------------
# Disparado quando o Claude Code termina de responder.
#
# Tarefa do agente:
#   - Ler docs/PLAN.md, localizar a seção "implementation plan"
#   - Revisar se o código implementado está aderente ao plano
#   - Criar testes para validar cada parte (quando possível)
#   - Gerar resumo em português com: executados, divergências, riscos,
#     sugestões — salvar em CODE-REVIEW.md
#
# Restrições:
#   - read-only sandbox (não altera arquivos do projeto)
#   - sem aprovação interativa (never)
# ============================================================================

set -u  # falha em variável não definida; NÃO usar -e pra Stop hook não travar Claude

# Vai para a raiz do projeto (Claude Code expõe esta variável)
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}" || exit 0

# Confere se o PLAN.md existe — se não, sai silenciosamente (exit 0)
# Stop hook que retorna erro pode entrar em loop com Claude tentando "consertar"
if [[ ! -f "docs/PLAN.md" ]]; then
  echo "[code-reviewer] docs/PLAN.md não encontrado, pulando revisão." >&2
  exit 0
fi

# Prompt enviado ao codex (heredoc evita pesadelo de aspas)
read -r -d '' PROMPT <<'EOF'
Leia docs/PLAN.md e procure pelo "implementation plan". Esta seção será seu guia
para a atividade de code-review. Revise se o código implementado está aderente
ao PLAN.md. Crie testes para analisar cada parte, quando possível, e execute os
testes disponíveis. Não altere arquivos do projeto.

Faça um resumo da sua análise em português, contendo:
  - O que foi executado
  - Divergências encontradas
  - Riscos
  - Sugestões

Salve esse resumo em CODE-REVIEW.md (na raiz do projeto).
EOF

# Executa o codex em modo não-interativo, leitura apenas
codex exec \
  --model gpt-5.5 \
  --ask-for-approval never \
  --sandbox read-only \
  "$PROMPT"

# Sempre sai 0: code-review é informativo, não deve bloquear o ciclo do Claude
exit 0