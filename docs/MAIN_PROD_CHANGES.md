# MAIN_PROD_CHANGES.md

Changelog canônico das adaptações de produção sobre o `backend/app/main.py`.

## Por que este arquivo existe

`backend/app/main.py` é uma cópia do parser que evolui em outra pasta de desenvolvimento (`leitor_de_pdf/main.py`). Periodicamente, uma nova versão do parser é trazida para este repositório. Para que isso não destrua as adaptações de produção (modo non-interactive, integração com `parser_adapter.py`, etc.), toda mudança feita sobre o `main.py` aqui é registrada nesta lista. Quando uma nova versão do parser chegar, este arquivo é o roteiro para reaplicar tudo rapidamente.

## Regras de refactor

Ver `planning/PLAN.md` → "Migração do Parser" → "Regras gerais de refactor — preservar versão de desenvolvimento". Resumo:

1. Não apagar funções, variáveis ou constantes existentes.
2. Adicionar a versão de produção logo abaixo do bloco de desenvolvimento, com marcador `# FASE PROD`.
3. Comentar chamadas DEV em vez de deletar, com marcador `# FASE DEV`.
4. Registrar toda mudança aqui (linha + descrição + razão).
5. Coexistência DEV/PROD no mesmo arquivo é regra dura.

## Como registrar uma mudança

Cada entrada deve ter:

- **Data** — quando a adaptação foi aplicada.
- **Versão de origem** — qual versão do parser DEV foi a base (commit/data/identificador da pasta `leitor_de_pdf/`).
- **Linha(s) afetada(s)** — referência ao `main.py` deste repositório.
- **Tipo** — `nova função`, `chamada substituída`, `import adicionado`, `constante modificada`, `bloco comentado`, etc.
- **Descrição** — o que foi feito.
- **Razão** — por que foi necessário em produção.

Formato sugerido por entrada:

```markdown
### YYYY-MM-DD — [F<n> | manutenção] — [resumo curto]

- **Versão de origem**: `leitor_de_pdf/main.py` <commit ou data>
- **Linha(s)**: <intervalos no main.py atual>
- **Tipo**: <categoria>
- **Descrição**: <o que mudou>
- **Razão**: <por quê>
```

## Changelog

<!-- Adicionar entradas mais recentes no topo. -->

_(Vazio — primeira entrada será criada quando F8 começar.)_
