# MAIN_PROD_CHANGES.md

> ⚠️ **OBSOLETO desde 2026-05-19 (reestruturação Opção A).** O `main.py` não é
> mais editado para produção: os arquivos do parser vivem intactos em
> `backend/app/leitor_pdf/` e toda a adaptação de produção foi extraída para
> `backend/app/parser_runner.py`. Ver **`docs/PARSER_RUNNER.md`** — é a
> referência atual. Este arquivo fica como registro histórico do modelo antigo.

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

### 2026-05-14 — F8b B1 fix — Bug do CONDUMAX (data invalida no /resolve)

Smoke visual de C1 revelou: PDF onde NCM falha primeiro (extração de produto roda ANTES de cnpj/data/numero) → modal abre só com NCM como missing, prefilled vazio, /resolve falha com `Data invalida:` (data_emissao=None em create_nf_entry). 3 bugs combinados:

- **Versão de origem**: B1 inicial (mesmo dia, 2026-05-14).
- **Tipo**: nova função, chamadas adicionadas, payload estruturado expandido.

#### Mudanças aplicadas

1. **Nova função `_canonical_field(campo)`** após `_reset_pending_prefilled`. Extrai chave canônica do `default_nf_template` a partir do label humano do parser. `'ncm (produto 1 de 1)' → 'ncm'`. Sem essa normalização, `filled = {"ncm (produto 1 de 1)": "85444900"}` no /resolve não bateria com `row.get("ncm")` em `create_nf_entry`.

2. **Block `except ParserCampoFaltante` expandido**: `missing` no `pending_rows.json` agora carrega o campo canônico + TODOS os campos de `default_nf_template` (exceto `contrato`, que vem da sessão) que NÃO estão em `prefilled`. Razão: parser pode falhar cedo (ex.: NCM) sem ter extraído cnpj/data/fornecedor/numero — todos NOT NULL. Antes o modal só pedia 1 campo e /resolve quebrava por NULL nos outros.

3. **5 chamadas best-effort de `_pending_track` ANTES da `new_concatenar`** (linha ~2026), aproveitando `df_product_service_desciption['primeiro_terco']` já refinado: `tipo_nota`, `cnpj` (+ `fornecedor` derivado via `consulta_nome_fornecedor`), `data_emissao`, `numero_nf`. Falhas individuais silenciadas — bloco principal (linha 2068+) tem try/except próprio que re-extrai/re-prompta. Garante que pendência por campo de produto (NCM/quant/preço) já tem metadados básicos no prefilled.

#### Impacto no DEV

Zero. `_pending_track` continua no-op em DEV (`NON_INTERACTIVE_MODE = False`). As 5 chamadas best-effort early são try/except-protegidas — nem em DEV nem em PROD podem quebrar o fluxo principal.

#### Testes

2 testes novos em `test_parser_pending.py`: `_canonical_field` extrai chave do label humano com parênteses; preserva chave exótica inteira (sem espaço). 10 testes B1 totais passando.

---

### 2026-05-14 — F8b B1 — Parser escreve `pending_rows.json` antes do exit 2

Camada de captura do prefilled que vai virar payload do modal de pendência no frontend (Fase B3 + C1). O parser DEV continua intocado — todo o trabalho é no bloco non-interactive.

- **Versão de origem**: `backend/app/main.py` pós-F8a (2026-05-07).
- **Tipo**: nova constante module-level, nova função, função alterada, chamadas adicionadas, bloco `except` expandido.

#### Mudanças aplicadas

1. **Novas constantes module-level** (logo após `NON_INTERACTIVE_MODE`):
   - `_PENDING_PREFILLED: dict = {}` — acumulador do que foi extraído com sucesso na NF em curso.
   - `_PENDING_CURRENT_FILE: str = ""` — nome do arquivo atual, capturado fora do scope local para sobreviver até o `except`.

2. **Novas funções** logo antes de `_solicitar_campo_humano`:
   - `_pending_track(campo, valor)` — registra extração bem-sucedida no acumulador. **No-op em modo DEV** (não gasta memória no terminal). Desencapsula o formato canônico do parser `{"cnpj": "..."}` para escalar. Filtra `None` e `""`.
   - `_reset_pending_prefilled()` — zera o acumulador no início de cada iteração do main loop.

3. **`_solicitar_campo_humano` alterada**: em modo non-interactive, agora passa `prefilled=dict(_PENDING_PREFILLED)` (cópia rasa) ao construir `ParserCampoFaltante`. DEV path inalterado.

4. **4 chamadas estratégicas de `_pending_track`** dentro do main loop (linhas ~2060-2080), logo após cada extração bem-sucedida de campo obrigatório: `cnpj`, `fornecedor`, `data_emissao`, `numero_nf`. Posicionamento depois das try/excepts garante captura tanto do valor extraído pelo parser quanto do digitado por humano em DEV.

5. **Reset + capture do current file** no topo de cada iteração do loop, antes de `extract_pdf_words`:
   ```python
   _reset_pending_prefilled()
   _PENDING_CURRENT_FILE = nome_saida
   ```

6. **Bloco `except ParserCampoFaltante` expandido** (~linhas 2126+). Antes do `sys.exit(2)`, escreve `pending_rows.json` no `--output-dir` com payload `{original_filename, contexto, missing: [campo], prefilled: {...}}`. Falha de IO no temp dir loga em stderr mas não mascara o exit 2 — adapter ainda classifica corretamente. **Não há nova exceção, novo exit code ou nova flag** — interface com adapter inalterada.

#### Por que não houve refactor mais profundo

A captura de `prefilled` está limitada aos 4 campos extraídos no main loop. Campos extraídos antes (descrição, valor, ncm, quant, preço unitário das linhas de produto) não entram no `prefilled` desta versão por exigirem `_pending_track` em pontos distribuídos pelas funções auxiliares (`new_concatenar_por_ponteiro_filtra_tabela_produtos`, `_campo_ou_humano`, etc.). Como o caso de uso real do modal é fornecedor/cnpj/data/numero (campos por NF, não por linha de produto), B1 fica focado nos quatro críticos. Expansão para campos de linha de produto fica como follow-up se aparecer demanda.

#### Impacto no DEV

Zero. `_pending_track` é no-op em modo interativo (`NON_INTERACTIVE_MODE = False`). Inputs no terminal seguem idênticos. `_reset_pending_prefilled` apenas zera um dict global — sem efeito colateral observável fora do modo PROD.

#### Testes

`backend/tests/test_parser_pending.py` (novo, 8 testes): tracker armazena escalar, desencapsula dict canônico, filtra None/'', é no-op em DEV, reset limpa, snapshot na exceção é cópia independente, prefilled vazio quando falha no primeiro campo. Não cobre o write em disco — isso vem na Fase B3 com teste e2e via subprocess.

---

### 2026-05-07 — F8a follow-up — Fix de NaN + fallback humano + trava de campos vazios

DEV trouxe três melhorias na função `new_concatenar_por_ponteiro_filtra_tabela_produtos` e em `consolidate_data_to_dict` para resolver o erro de `Decimal('NaN')` chegando ao PostgreSQL JSONB e endurecer invariantes do parser.

- **Versão de origem**: `leitor_de_pdf/main.py` v10+ (cópia em `bug_fix/main.py` em 2026-05-07).
- **Tipo**: nova função local, novo bloco lógico, chamadas substituídas, alias adicionado, comentários reformulados.

#### Mudanças aplicadas

1. **Nova função local `_campo_ou_humano(valor, campo_legivel, contexto_produto)`** dentro de `new_concatenar_por_ponteiro_filtra_tabela_produtos` (após `_norm`). Garante que campo de transação volta string não-vazia: se valor vem ausente/vazio, chama `_solicitar_campo_humano` em loop até receber algo. Em modo PROD non-interactive, a primeira chamada já levanta `ParserCampoFaltante` (F8a) e a exceção sobe — o `while True` não trava. Linhas atuais ~1103-1113.

2. **Heurística de corte da última janela de produtos** dentro do for loop de `new_concatenar`. Quando a última janela não tem teto natural (`fim = max_linha + 1`), pode absorver lixo pós-tabela (ex.: bloco ISSQN entre produtos e DADOS ADICIONAIS). Detecta gap vertical anormal (> 5× mediana dos gaps positivos da janela, piso de 25px) e corta. **Esta é a fix da causa raiz do `Decimal('NaN')` chegando ao DB**: o lixo absorvido gerava células de quantidade vazias/inválidas que viravam NaN. Linhas atuais ~1186-1202.

3. **Substituição de `raise ParserEstruturaQuebrada` por `_campo_ou_humano` para os 5 campos** (`descricao`, `ncm`, `quant`, `unit`, `price`) na seção de extração por janela. **Reclassificação semântica importante**: campos faltantes em produto **deixam de ser Tipo 2 (estrutura quebrada → email admin)** e passam a ser **Tipo 1 (campo faltante → revisão humana, futuramente nf_pending modal em F8b)**. Em PROD non-interactive, `_campo_ou_humano → _solicitar_campo_humano → raise ParserCampoFaltante` (exit code 2 no adapter).

4. **Alias `'qtd'` adicionado** em `aliases['quant']`. Linha atual ~1119.

5. **Trava de campos string vazia em `consolidate_data_to_dict`** (3b). Bloco novo após o check de `campos_vazios` (3a). Detecta strings vazias remanescentes (que indicam defeito de código upstream, não input malformado) e levanta `RuntimeError` — **não ValueError, não ParserEstruturaQuebrada** — propositalmente fora do `except ValueError` do main loop. O batch para, forçando correção do código. Linhas atuais ~1664-1685.

6. **Comentários reformulados** em `consolidate_data_to_dict`: separação clara entre 3a (campos None — revisão humana legítima) e 3b (strings vazias — bug code upstream).

#### Impacto na classificação de erros (interação com F8a)

Antes desta entrada:
- `ncm` ou `descricao` faltante → `ParserEstruturaQuebrada` → exit 3 → adapter classifica como `reason="estrutura_quebrada"` → e-mail admin (em F7)

Depois desta entrada:
- `ncm`, `descricao`, `quant`, `unit`, `price` faltante → `ParserCampoFaltante` → exit 2 → adapter classifica como `reason="campo_faltante"` → revisão humana (em F8b vira `nf_pending` + modal)

Reclassificação correta — campo faltante É Tipo 1 por design, F8a tinha colocado errado em Tipo 2 (a função `new_concatenar` é território de "campo do produto", não de "estrutura do PDF").

#### Mudança não aplicada

A variável de debug `arquivo_investigado` em DEV mudou de `'29105'` para `'1592'`. Não trouxe — é preferência de debug do usuário em DEV; em PROD não tem efeito (string nunca casa com nome de arquivo real).

#### Validação

- `python -m py_compile backend/app/main.py` → OK
- `pytest backend/tests/test_parser_non_interactive.py` → 6/6 passam
- Smoke visual no Docker pendente (a executar pelo dono após esta entrada)

---

### 2026-05-06 — F8a follow-up — Alinhamento `num_nf` com DEV + tesseract-ocr-por

Detectado durante smoke pós-rollback: a função `num_nf` em `backend/app/main.py` tinha lógica diferente da versão DEV atual (`leitor_de_pdf/main.py`). A divergência veio de uma modificação anterior em backend/app/main.py que nunca foi registrada aqui — agora estamos alinhando com a DEV atual e documentando.

- **Versão de origem**: `leitor_de_pdf/main.py` (cópia em `bug_fix/main.py` durante esta sessão de fix).
- **Linha(s)**: `backend/app/main.py:1581-1583` (atual, pós-update).
- **Tipo**: chamada substituída (alinhamento DEV).
- **Descrição**: `num_nf` retorna `{'numero_nf': " - ".join(numeros_unicos)}` em todos os casos. Versão anterior (não-registrada) retornava string única quando `len == 1` e lista quando `> 1`, gerando heterogeneidade no tipo de retorno. DEV consolidou em string sempre.
- **Razão**: heterogeneidade do tipo (string vs lista) causa erros downstream quando o consumidor espera string. DEV reverteu para string única; PROD precisa acompanhar.

#### Fix de infraestrutura — `tesseract-ocr-por` no Dockerfile

Smoke pós-rollback expôs erro de OCR: `TesseractError: Failed loading language 'por'`. `Dockerfile` instalava só `tesseract-ocr` (engine), não o pacote de idioma. PDFs imagem (que caem no caminho de fallback OCR de `extrair_dados_nf_servico_do_pdf`) falhavam no container, mas funcionavam no host Windows porque a instalação local de tesseract tinha o pacote `por` baixado em algum momento.

Mesmo padrão das B4/B5 do F8a inicial (cv2, base_contratos.json): F8a destravou o pipeline e expôs deps de runtime que estavam latentes.

**Aplicado**: adicionado `tesseract-ocr-por` ao `apt-get install` no `backend/Dockerfile`. Idiomas adicionais não são necessários — `ocr_reader.py` usa `lang="por"` em todos os call sites.

**Quando uma nova versão do parser DEV chegar**: verificar se `ocr_reader.py` ainda usa só `por` ou adicionou outros idiomas (`eng`, `osd`). Se sim, adicionar os pacotes correspondentes (`tesseract-ocr-eng`, `tesseract-ocr-osd`). `osd` é frequentemente útil para detecção de orientação de página.

---

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
