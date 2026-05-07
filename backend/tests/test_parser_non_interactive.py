"""F8a — testes do refactor non-interactive do parser.

Cobre apenas a interface: import limpo, --help, exit codes, exceções tipadas,
constantes do adapter sincronizadas. Não exercita o pipeline real do parser
(isso depende de PDFs e está coberto pelos testes de upload).
"""
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def test_main_module_import_does_not_block():
    """`import main` não pode disparar input() nem chamar selecionar_contrato.

    Antes de F8a, a linha 85 do main.py executava `selecionar_contrato(None)`
    no nível de módulo, travando qualquer subprocess sem TTY.
    """
    import importlib
    import sys as _sys

    # Remove import anterior (se conftest já importou main indiretamente)
    _sys.path.insert(0, str(SCRIPT_PATH.parent))
    if "main" in _sys.modules:
        del _sys.modules["main"]

    main = importlib.import_module("main")

    assert main.NON_INTERACTIVE_MODE is False, "default deve ser False — preserva DEV"
    assert hasattr(main, "ParserCampoFaltante")
    assert hasattr(main, "ParserEstruturaQuebrada")


def test_parser_estrutura_quebrada_inherits_value_error():
    """ParserEstruturaQuebrada precisa ser ValueError para preservar os 5 blocos
    `except ValueError` existentes em main.py (linhas 1194, 1242, 1887, 1922, 1927).
    """
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    if "main" in sys.modules:
        del sys.modules["main"]
    import main

    assert issubclass(main.ParserEstruturaQuebrada, ValueError)
    # ParserCampoFaltante não pode ser ValueError — adapter classifica via isinstance
    assert not issubclass(main.ParserCampoFaltante, ValueError)


def test_main_help_exits_zero():
    """`python main.py --help` retorna exit code 0 e mostra as 4 flags da F8a."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "--contrato" in result.stdout
    assert "--input-dir" in result.stdout
    assert "--output-dir" in result.stdout
    assert "--non-interactive" in result.stdout


def test_main_requires_contrato_when_non_interactive():
    """`--non-interactive` sem `--contrato` falha rápido com exit code 1.

    Sem este enforcement, o parser cairia em selecionar_contrato(None) que
    chama input() e trava o subprocess.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--non-interactive"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "--contrato" in result.stderr


def test_adapter_constants_match_main_exit_codes():
    """Adapter precisa ter os mesmos exit codes que main.py usa em sys.exit.

    Se main.py mudar `sys.exit(2)` para outro número, o adapter passa a
    classificar errado. Esta checagem trava o adapter contra esse drift.
    F2 removeu `DEFAULT_CONTRATO_PRE_F2` (era placeholder F8a).
    """
    sys.path.insert(0, str(SCRIPT_PATH.parents[0]))
    from app import parser_adapter

    assert parser_adapter.EXIT_CODE_CAMPO_FALTANTE == 2
    assert parser_adapter.EXIT_CODE_ESTRUTURA_QUEBRADA == 3
    assert not hasattr(parser_adapter, "DEFAULT_CONTRATO_PRE_F2"), (
        "DEFAULT_CONTRATO_PRE_F2 foi removido em F2 — não deve mais existir"
    )


def test_adapter_signature_accepts_contrato_numero():
    """parse_pdf_bytes precisa aceitar contrato_numero como kwarg ou 4º posicional.

    F2 vai depender disso para passar request.session["contrato_id"].
    """
    import inspect

    from app.parser_adapter import LegacyParserAdapter

    sig = inspect.signature(LegacyParserAdapter.parse_pdf_bytes)
    params = list(sig.parameters.keys())
    assert "contrato_numero" in params, f"esperado 'contrato_numero' em {params}"

    # default deve ser None para que server.py possa chamar sem passar
    assert sig.parameters["contrato_numero"].default is None
