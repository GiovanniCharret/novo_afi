# Parser — `leitor_pdf/` + `parser_runner.py`

**Reestruturação de 2026-05-19 (Opção A).** Substitui o modelo anterior, em
que as adaptações de produção F8a/F8b eram editadas dentro do `main.py` e
rastreadas em `docs/MAIN_PROD_CHANGES.md` (agora obsoleto).

## Problema que resolve

O parser de NFs é desenvolvido **fora deste repositório** (projeto `leitor_de_pdf`)
e versões novas são puxadas periodicamente. Antes, cada pull exigia re-aplicar à
mão as adaptações de produção (modo non-interactive, exit codes, `pending_rows.json`,
`argparse`) dentro do `main.py`. Isso era frágil — um pull podia trazer um
`main.py` sem as adaptações e quebrar todo o backend.

## Solução

Os arquivos do parser ficam numa pasta isolada; toda a **adaptação de produção**
vive num arquivo separado que o repositório controla.

```
backend/app/
├── leitor_pdf/                ← arquivos do parser (projeto de desenvolvimento)
│   ├── main.py
│   ├── ocr_reader.py
│   ├── description_cleaner.py
│   └── block_cnpj.json          (dado lido por main.py via __file__)
├── cnpj_lookup.py             ← módulos irmãos do parser que PERMANECEM
├── contrato_config.py            em backend/app/ (decisão 2026-05-19)
├── parser_runner.py           ← camada de produção (F8a/F8b vivem aqui)
└── parser_adapter.py          ← invoca parser_runner.py como subprocess
```

`cnpj_lookup.py` e `contrato_config.py` ficaram em `backend/app/` de propósito
(preserva os caminhos de `cnpj.json` e `base_contratos.json`). Eles e os
arquivos de `leitor_pdf/` entram no `sys.path` do `parser_runner`.

`parser_runner.py` **não contém lógica de produção dentro dos arquivos do
parser** — ele os roda por fora. A única coisa que o parser precisa expor é o
contrato abaixo.

## O contrato do parser — `ParserCampoFaltante`

O parser sinaliza "não consegui extrair o campo X" de forma estruturada, e
isso é parte do **design do parser** (adotado no projeto de desenvolvimento —
não é poluição de produção):

- `ocr_reader.py` define `class ParserCampoFaltante(Exception)` com `.campo`
  (o campo faltante) e `.prefilled` (dict do que o parser JÁ extraiu desta NF).
  `main.py` importa essa classe (`from ocr_reader import ParserCampoFaltante`).
- As duas funções `_solicitar_campo_humano` (uma no `main.py`, outra no
  `ocr_reader.py`) **levantam `ParserCampoFaltante`** em vez de chamar
  `input()`. Cada uma reúne o `prefilled` do que o pipeline já montou
  (`main.py` varre os frames da pilha; `ocr_reader.py` lê o dict `nf` do
  pass de OCR).

Resultado: o `parser_runner` captura essa exceção e o modal F8b mostra os
campos já extraídos preenchidos, pedindo só o que falta.

> **Ao puxar uma versão nova do parser** (`leitor_de_pdf/`), garanta que o
> `_solicitar_campo_humano` (no `main.py` e no `ocr_reader.py`) continua
> levantando `ParserCampoFaltante(campo, prefilled)`. É o único ponto do
> parser que o `parser_runner` depende. (No terminal de dev, quem quiser o
> prompt interativo de volta envolve a chamada num `try/except`.)

## Como o `parser_runner.py` funciona

Entrypoint chamado pelo `LegacyParserAdapter` como subprocess:

1. Roda `leitor_pdf/main.py` via `runpy.run_path` no próprio processo (o
   subprocess já isola — crash/timeout não derrubam o backend).
2. Captura `ParserCampoFaltante` (duck-typing por `.campo`/`.prefilled` — a
   classe vem do parser, executado via runpy). Como salvaguarda, também
   substitui `builtins.input`: se algum `input()` escapar, vira
   `ParserCampoFaltante` em vez de travar lendo stdin inexistente.
3. Fixa `contrato_config.selecionar_contrato` no contrato de `--contrato`,
   sem abrir o menu interativo.
4. Classifica o desfecho em exit codes que o `parser_adapter.py` já entende:
   `0` sucesso · `2` campo faltante (grava `pending_rows.json` com `campo` +
   `prefilled` → modal F8b) · `3` erro estrutural (`ValueError` do pipeline) ·
   `1` falha genérica.

Premissas adicionais do contrato (se quebrarem num pull, ajustar o runner):
`contrato_config.selecionar_contrato(numero)` resolve sem prompt para uma
chave válida de `base_contratos.json`; `main.py` lê PDFs de `./nfs_analise`
e grava o xlsx em `./output_dfs` (relativo ao cwd — o adapter roda o
subprocess com cwd no temp dir).

## Como atualizar o parser (pull de uma versão nova de dev)

Copie os arquivos novos para `backend/app/leitor_pdf/`. O `parser_runner.py`
não muda. Confira só:

- `_solicitar_campo_humano` (main.py e ocr_reader.py) ainda levanta
  `ParserCampoFaltante(campo, prefilled)` — ver "O contrato do parser";
- se `main.py` passar a ler um novo arquivo de dados via
  `Path(__file__).parent`, copie-o para `leitor_pdf/` também (hoje: só
  `block_cnpj.json`).

## Testes

`backend/tests/test_parser_runner.py` cobre a interface do runner (import
limpo, exit codes, `--help`, salvaguarda `builtins.input`). O pipeline real
depende de PDF + stack OCR — coberto pelo smoke manual e, indiretamente,
pelos testes de upload (que usam `FakeAdapter`).
