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

### 2026-05-06 — F8a — Parser non-interactive + exceções tipadas

- **Versão de origem**: `leitor_de_pdf/main.py` v10 (cópia atual de `backend/app/main.py` antes desta entrada).
- **Tipo**: nova função, chamada substituída, bloco movido, import adicionado.
- **Razão**: subprocess do `parser_adapter.py` travava em `selecionar_contrato(None)` (linha 85 original) e nas 14 chamadas a `_solicitar_campo_humano` que usam `input()`. Sem este refactor, F2 (seleção de contrato) não tem como passar contrato ao parser, e qualquer NF com campo faltante trava o batch até o timeout de 180s.

#### Mudanças aplicadas

1. **Novas exceções tipadas** (após linha 25, FASE PROD).
   - `ParserCampoFaltante(Exception)` — sinaliza Tipo 1 (campo não extraído). Atributos: `campo`, `contexto`, `prefilled`.
   - `ParserEstruturaQuebrada(ValueError)` — sinaliza Tipo 2 (estrutura quebrada). **Herda de `ValueError`** para preservar os 5 blocos `except ValueError` já existentes em `main.py` (linhas 1194, 1242, 1887, 1922, 1927). O backend classifica via `isinstance`, não por número de linha (item 15 do `planning/ADVERSARIAL_REVIEW.md`).

2. **Flag `NON_INTERACTIVE_MODE`** (linha pós-MODO_LLM, FASE PROD). Default `False` preserva DEV. Ativada pelo bloco `if __name__ == "__main__":` quando `--non-interactive` está presente.

3. **`_solicitar_campo_humano`** (função em ~linha 118) — passou a checar `NON_INTERACTIVE_MODE` no topo:
   - **FASE PROD**: levanta `ParserCampoFaltante(campo, contexto)` em vez de `input()`.
   - **FASE DEV** (terminal): comportamento original preservado abaixo do branch PROD (`print` + `input`).
   - Esta única edição cobre as 14 call sites de `_solicitar_campo_humano` listadas em PLAN.md → Decisão #8.

4. **17× `raise ValueError(...)` → `raise ParserEstruturaQuebrada(...)`** nos sites estruturais (linhas atuais 712, 786, 928, 1033, 1071, 1189, 1193, 1260, 1334, 1342, 1344, 1368, 1394, 1406, 1583, 1624, 1926). Comportamento preservado pela herança de `ValueError`.
   - **Não tocados**: linha 822 (`_normalizar_texto recebeu tipo inválido` — programmer error) e linhas 1220/1224 (validação de input do usuário em `extrair_produtos_pagina_alternativa` — só dispara em DEV mode).

5. **Bloco de execução top-level movido** para `if __name__ == "__main__":` (linhas atuais 1755+):
   - **FASE DEV comentada**: linhas originais 88 (`Path("log.json").write_text`) e 106-110 (`CONTRATO = selecionar_contrato`, `_ocr_mod.CONTRATO`, `caminho_entrada`, `arquivos_pdf`) ficaram como comentários no topo, marcadas com `# FASE DEV (terminal) — chamadas movidas para if __name__ == "__main__":`.
   - **FASE PROD adicionada** ao final: argparse com `--contrato`, `--input-dir`, `--output-dir`, `--non-interactive`. `--contrato` é obrigatório **somente quando** `--non-interactive` (preserva uso DEV via menu). Setup recriado dentro do `__main__` block: `Path("log.json").write_text`, `CONTRATO = selecionar_contrato(_args.contrato)`, etc.
   - For loop principal (linha original 1747) re-indentado em +8 espaços para ficar dentro de `try:`.
   - **Exit codes** definidos: `1` para erro de uso (sem `--contrato` em modo non-interactive), `2` para `ParserCampoFaltante`, `3` para `ParserEstruturaQuebrada`.

#### Acoplamento com `parser_adapter.py` (mesma fase, F8a)

- Adapter passa subprocess com `--non-interactive --contrato N --input-dir X --output-dir Y` usando `sys.executable`.
- `parse_pdf_bytes` ganhou parâmetro `contrato_numero: str | None = None` (4º posicional). F2 vai usar.
- Constantes `EXIT_CODE_CAMPO_FALTANTE=2`, `EXIT_CODE_ESTRUTURA_QUEBRADA=3` no adapter espelham o `main.py`.
- Branches dedicados convertem exit 2 e exit 3 em `ParserOutcome(status="erro_parsing", reason="campo_faltante" | "estrutura_quebrada")`. Em F8b, exit 2 vai redirecionar para `nf_pending` em vez de `erro_parsing`.

#### Como reaplicar quando uma nova versão do parser DEV chegar

Ao trazer `leitor_de_pdf/main.py` v11 (ou superior) para este repositório:

1. Copiar o arquivo cru sobre `backend/app/main.py`.
2. Reaplicar a mudança **1** (definir `ParserCampoFaltante` e `ParserEstruturaQuebrada` após os imports).
3. Reaplicar **2** (linha `NON_INTERACTIVE_MODE = False`).
4. Reaplicar **3** (modificação do topo de `_solicitar_campo_humano`).
5. Reaplicar **4** (varrer `raise ValueError` e converter os de natureza estrutural — Tipo 2). **Atenção**: linhas mudam a cada versão; use grep por mensagem, não por número de linha. Lista de mensagens canônicas estão neste documento e em `planning/PLAN.md` Decisão #8.
6. Reaplicar **5** (mover top-level executável para `if __name__ == "__main__":` com argparse + try/except). O helper Python que fez isso na primeira aplicação está documentado no histórico desta conversa de F8a; pode ser regravado como script em `backend/scripts/refactor_main_phase_prod.py` se a operação se tornar recorrente.
7. Rodar `backend/tests/test_parser_non_interactive.py` para validar — todos os 6 testes devem passar.
8. Validar com smoke: `python backend/app/main.py --help` (exit 0) e `python backend/app/main.py --non-interactive` (exit 1).

#### Fix de infraestrutura (B4 — destravando smoke visual de F8a)

Durante a Fase C (smoke visual) de F8a, descobriu-se que `backend/app/ocr_reader.py:13` faz `import cv2` no nível de módulo, mas `opencv-python` nunca esteve em `backend/requirements.txt` nem no `Dockerfile`. O `import` está em `ocr_reader.py` linha 13 e **executa antes** de `selecionar_contrato(None)` (que travava em `input()` pré-F8a).

Pré-F8a o ImportError já acontecia, mas era mascarado: o subprocess travava nos 180s do `input()` interativo, o adapter caía em `erro_parsing` genérico, e o stderr não era proeminente. F8a destravou o timeout e tornou a classificação de exit codes precisa, então o ImportError de `cv2` aparece visível com traceback no frontend.

**Aplicado**: adicionado `opencv-python-headless==4.10.0.84` em `backend/requirements.txt`. Versão headless é a correta para container (sem libs de display X11). API equivalente para os usos em `ocr_reader.py:408-417` (`cv2.threshold`, `cv2.morphologyEx`, `cv2.add`, `cv2.subtract`, `cv2.bitwise_not`).

**Quando uma nova versão do parser DEV chegar**: verificar se `ocr_reader.py` ainda usa `cv2` (ou se mudou para outra lib de visão). Se sim, manter `opencv-python-headless` em `requirements.txt`. Se a nova versão usar mais funções de `cv2`, validar que `headless` ainda cobre.

#### Fix de infraestrutura adicional (B5 — bind mount de `base_contratos.json`)

Após o fix do `cv2` (B4), o smoke falhou em outro `FileNotFoundError`: `contrato_config.py:16` faz `_BASE_PATH = Path(__file__).resolve().parent / "base_contratos.json"`, esperando o JSON ao lado do módulo (em `backend/app/`). O arquivo real está em `recebimento_notas/base_contratos.json` (raiz do projeto, conforme `CLAUDE.md`).

Pré-F8a o erro também acontecia em import-time (linha original 85 chamava `selecionar_contrato(None)` que aciona `_carregar_base()`). Permanecia mascarado pelo timeout do `input()`. F8a destravou isso e tornou o erro determinístico no stderr.

**Aplicado**: bind mount adicional em `docker-compose.yml` sob o serviço `backend`:

```yaml
volumes:
  - ./backend:/app/backend
  - ./base_contratos.json:/app/backend/app/base_contratos.json:ro
```

**Não tocou** `contrato_config.py` (módulo do parser DEV, regra de preservação). Fonte de verdade continua na raiz (`CLAUDE.md` documenta). F2 e o parser leem do mesmo arquivo via caminhos diferentes.

**Quando uma nova versão do parser DEV chegar**: se `contrato_config.py` mudar para outra estratégia de localização do JSON (ex.: env var, caminho relativo ao cwd), reavaliar se este bind mount ainda é necessário. Se sim, manter; se a nova versão honrar env var, trocar pelo padrão `BASE_CONTRATOS_PATH=/app/base_contratos.json` em `docker-compose.yml`.

**Limitação conhecida**: rodar `uvicorn` direto fora do compose continua falhando. Aceitável porque o ambiente-alvo de F8a é local/dev via Docker (declarado na spec da Fase A). Quem desenvolver puramente em venv terá que copiar o JSON manualmente para `backend/app/` ou usar o compose.

#### Testes adicionados

`backend/tests/test_parser_non_interactive.py` (novo, 6 testes):

- `test_main_module_import_does_not_block` — garante que `import main` não dispara menu interativo.
- `test_parser_estrutura_quebrada_inherits_value_error` — preserva captura por `except ValueError` legado.
- `test_main_help_exits_zero` — `--help` funciona e cita as 4 flags.
- `test_main_requires_contrato_when_non_interactive` — enforcement da combinação.
- `test_adapter_constants_match_main_exit_codes` — trava o adapter contra drift de exit codes.
- `test_adapter_signature_accepts_contrato_numero` — F2 pode wirear contrato_id da sessão.
