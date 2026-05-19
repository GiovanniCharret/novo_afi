"""Testes do parser_runner.py — camada de produção do parser (Opção A,
reestruturação de 2026-05-19).

O `parser_runner.py` adapta o `leitor_pdf/main.py` (idêntico ao que vem do
projeto de desenvolvimento do parser) para rodar non-interactive, sem editá-lo.
Ver docs/PARSER_RUNNER.md.

Estes testes cobrem a INTERFACE do runner — import limpo, exit codes, --help
e o mecanismo de campo faltante (`builtins.input` → `ParserCampoFaltante`).
Não exercitam o pipeline real do parser (depende de PDF + stack OCR; isso é
coberto pelos testes de upload, que usam um FakeAdapter, e pelo smoke manual).
"""
import subprocess
import sys
from pathlib import Path

import pytest

# parser_runner é um script em backend/app/ — import plano exige app/ no path.
_APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

import parser_runner  # noqa: E402

RUNNER_PATH = Path(parser_runner.__file__).resolve()


def test_import_nao_roda_pipeline():
    """Importar `parser_runner` não dispara o parser nem `input()` — `main()`
    só roda sob `if __name__ == "__main__"`."""
    assert hasattr(parser_runner, "main")
    assert hasattr(parser_runner, "ParserCampoFaltante")


def test_campo_faltante_nao_e_value_error():
    """`ParserCampoFaltante` NÃO pode herdar de `ValueError`: o runner
    classifica campo faltante (exit 2) separado de erro estrutural (exit 3,
    `ValueError` propagado do pipeline). Se virasse `ValueError`, o `except`
    estrutural o capturaria primeiro e o modal F8b nunca abriria."""
    assert not issubclass(parser_runner.ParserCampoFaltante, ValueError)
    assert issubclass(parser_runner.ParserCampoFaltante, Exception)


def test_campo_do_prompt_extrai_e_normaliza():
    """`_campo_do_prompt` tira o campo do prompt de `_solicitar_campo_humano`
    e normaliza rótulo composto (`ncm (produto 1 de 1)` → `ncm`)."""
    f = parser_runner._campo_do_prompt
    assert f("  Digite o valor para 'cnpj' (ou Enter para deixar em branco): ") == "cnpj"
    assert f("  Digite o valor para 'ncm (produto 1 de 1)' (ou Enter): ") == "ncm"
    assert f("prompt sem aspas") == "campo_desconhecido"


def test_input_nao_interativo_levanta_campo_faltante():
    """O `input()` substituído levanta `ParserCampoFaltante` com o campo do
    prompt. Cobre as DUAS `_solicitar_campo_humano` (main.py e ocr_reader.py)
    — ambas chamam `input()`."""
    with pytest.raises(parser_runner.ParserCampoFaltante) as exc:
        parser_runner._input_nao_interativo("  Digite o valor para 'valor' (ou Enter): ")
    assert exc.value.campo == "valor"


def test_runner_help_exits_zero():
    """`python parser_runner.py --help` → exit 0, mostra as 4 flags que o
    `parser_adapter.py` passa."""
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    for flag in ("--non-interactive", "--contrato", "--input-dir", "--output-dir"):
        assert flag in result.stdout


def test_runner_falha_sem_contrato_com_exit_1():
    """Argumento obrigatório ausente → exit 1 (não exit 2). Exit 2 é
    reservado para campo faltante — argparse `required=True` sairia com 2 e
    o adapter classificaria errado."""
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--non-interactive",
         "--input-dir", ".", "--output-dir", "."],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "contrato" in result.stderr.lower()


def test_adapter_aponta_para_o_runner():
    """O `LegacyParserAdapter` deve invocar `parser_runner.py` como subprocess
    (não mais `main.py` direto) e manter os exit codes 2/3."""
    from app import parser_adapter

    assert parser_adapter.SCRIPT_PATH.name == "parser_runner.py"
    assert parser_adapter.EXIT_CODE_CAMPO_FALTANTE == 2
    assert parser_adapter.EXIT_CODE_ESTRUTURA_QUEBRADA == 3
