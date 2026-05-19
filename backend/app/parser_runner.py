"""parser_runner.py — camada de produção do parser de NFs (lógica F8a/F8b).

Entrypoint chamado pelo `LegacyParserAdapter` como subprocess. Roda os
arquivos do parser em `leitor_pdf/` (versão do projeto de desenvolvimento) e
os adapta para produção:

  * roda `leitor_pdf/main.py` via `runpy` no próprio processo (o subprocess
    já garante o isolamento — crash/timeout não derrubam o backend);
  * captura `ParserCampoFaltante` — o `_solicitar_campo_humano` do parser
    (main.py e ocr_reader.py) levanta essa exceção, com `campo` + `prefilled`
    (o que já foi extraído), quando um campo obrigatório falta. Vira o fluxo
    de preenchimento humano F8b. Como salvaguarda, `builtins.input` também é
    substituído (se algum `input()` escapar, vira ParserCampoFaltante em vez
    de travar lendo um stdin inexistente — o antigo `EOFError`);
  * fixa `contrato_config.selecionar_contrato` no contrato recebido via
    `--contrato`, sem abrir o menu interativo de terminal;
  * classifica o desfecho em exit codes que o `parser_adapter.py` entende:
        0 — sucesso (xlsx gerado em --output-dir)
        2 — campo faltante: grava pending_rows.json; o adapter abre o modal F8b
        3 — erro estrutural (ValueError propagado do pipeline)
        1 — falha genérica

Toda a lógica de produção que antes vivia (e poluía) o `main.py` mora aqui.
Trocar o parser por uma versão nova de desenvolvimento é só copiar os
arquivos para `leitor_pdf/`. Ver docs/PARSER_RUNNER.md.

Contrato com o projeto de desenvolvimento (se algo aqui quebrar, é porque
uma destas premissas mudou no parser de dev):
  * `_solicitar_campo_humano` levanta `ParserCampoFaltante(campo, prefilled)`
    quando não extrai um campo obrigatório (`ParserCampoFaltante` é definida
    em `ocr_reader.py`; `main.py` a importa de lá);
  * `contrato_config.selecionar_contrato(numero)` resolve sem prompt quando
    `numero` é uma chave válida de base_contratos.json;
  * `leitor_pdf/main.py` lê PDFs de `./nfs_analise` e grava o xlsx em
    `./output_dfs` (relativo ao cwd — o adapter roda com cwd no temp dir).
"""
import argparse
import builtins
import json
import re
import runpy
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent          # backend/app
LEITOR_PDF_DIR = APP_DIR / "leitor_pdf"
MAIN_SCRIPT = LEITOR_PDF_DIR / "main.py"

# `main.py` importa `ocr_reader` / `description_cleaner` como módulos planos —
# `leitor_pdf/` precisa estar no sys.path. `backend/app/` já entra no sys.path
# (é o diretório deste script), cobrindo `cnpj_lookup` e `contrato_config`.
if str(LEITOR_PDF_DIR) not in sys.path:
    sys.path.insert(0, str(LEITOR_PDF_DIR))


class ParserCampoFaltante(Exception):
    """Tipo 1 — campo obrigatório que o parser não conseguiu extrair. No
    terminal, `_solicitar_campo_humano` pediria o valor via `input()`; aqui
    isso vira o sinal que dispara o fluxo de preenchimento humano F8b."""

    def __init__(self, campo):
        self.campo = campo
        super().__init__(f"Campo obrigatório não extraído: '{campo}'")


def _campo_do_prompt(prompt):
    """Extrai o nome do campo do prompt de `_solicitar_campo_humano`
    (`Digite o valor para '<campo>' ...`). Normaliza rótulos compostos como
    `ncm (produto 1 de 1)` para a chave canônica `ncm`."""
    match = re.search(r"'([^']*)'", str(prompt))
    campo = match.group(1) if match else "campo_desconhecido"
    return campo.split(" ", 1)[0].strip() or "campo_desconhecido"


def _input_nao_interativo(prompt=""):
    """Substitui `builtins.input` no modo non-interactive. Cobre as DUAS
    funções `_solicitar_campo_humano` (a do `main.py` e a do `ocr_reader.py`)
    de uma só vez, sem tocar em nenhuma delas — ambas chamam `input()`."""
    raise ParserCampoFaltante(_campo_do_prompt(prompt))


def _gravar_pending(output_dir, input_dir, campo, prefilled):
    """Grava `pending_rows.json` no `--output-dir` para o adapter ler.

    `prefilled` traz o que o parser já extraiu desta NF — vem da
    `ParserCampoFaltante` levantada pelo `_solicitar_campo_humano` do parser.
    O modal mostra esses campos preenchidos e pede só o que falta."""
    pdfs = sorted(Path(input_dir).glob("*.pdf"))
    nome_pdf = pdfs[0].name if pdfs else ""
    payload = {
        "original_filename": nome_pdf,
        "contexto": nome_pdf,
        "missing": [campo],
        "prefilled": prefilled or {},
    }
    try:
        (Path(output_dir) / "pending_rows.json").write_text(
            json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8"
        )
    except OSError as err:
        # Falha de IO não deve mascarar o desfecho — segue com exit 2.
        print(f"[parser_runner] Falha ao gravar pending_rows.json: {err}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Runner de produção do parser de NFs.")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Suprime input(); pedido de campo humano vira exit 2.")
    parser.add_argument("--contrato",
                        help="Número do contrato (chave de base_contratos.json).")
    parser.add_argument("--input-dir",
                        help="Diretório com o PDF de entrada.")
    parser.add_argument("--output-dir",
                        help="Diretório de saída (recebe o xlsx e o pending_rows.json).")
    args = parser.parse_args()

    # Validação manual (em vez de `required=True`): argparse sairia com
    # exit 2, que colidiria com o exit 2 = campo faltante. Argumento
    # ausente é falha genérica → exit 1.
    faltando = [
        nome for nome, valor in (
            ("--contrato", args.contrato),
            ("--input-dir", args.input_dir),
            ("--output-dir", args.output_dir),
        ) if not valor
    ]
    if faltando:
        print(f"[parser_runner] Argumentos obrigatórios ausentes: {', '.join(faltando)}",
              file=sys.stderr)
        return 1

    # Fixa o contrato: `selecionar_contrato` passa a ignorar o argumento (o
    # `main.py` de dev o chama com `None`) e devolve sempre o contrato
    # recebido por `--contrato`, sem abrir o menu interativo de terminal.
    import contrato_config
    _selecionar_original = contrato_config.selecionar_contrato
    contrato_config.selecionar_contrato = lambda numero=None: _selecionar_original(args.contrato)

    # Non-interactive: nenhum `input()` pode bloquear o subprocess.
    if args.non_interactive:
        builtins.input = _input_nao_interativo

    try:
        # `run_name="__main__"` para o caso de o `main.py` de dev vir, no
        # futuro, com um guard `if __name__ == "__main__":` — hoje ele roda
        # tudo em nível de módulo de qualquer forma.
        runpy.run_path(str(MAIN_SCRIPT), run_name="__main__")
    except Exception as exc:
        # Campo faltante (Tipo 1): o parser levanta uma exceção com `.campo`
        # e `.prefilled` (`ocr_reader.ParserCampoFaltante`, levantada pelas
        # `_solicitar_campo_humano` do main.py e do ocr_reader). Duck-typing
        # — não importamos a classe (o parser é executado via runpy). O
        # safety net `_input_nao_interativo` também cai aqui (sem prefilled).
        if hasattr(exc, "campo"):
            prefilled = getattr(exc, "prefilled", None) or {}
            _gravar_pending(args.output_dir, args.input_dir, exc.campo, prefilled)
            print(f"[parser_runner] Campo faltante: '{exc.campo}' "
                  f"({len(prefilled)} campo(s) já extraído(s))", file=sys.stderr)
            return 2
        if isinstance(exc, ValueError):
            # Erro estrutural — o pipeline levanta `ValueError` puro
            # (tabela quebrada etc.).
            print(f"[parser_runner] Erro estrutural no parser: {exc}", file=sys.stderr)
            return 3
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
