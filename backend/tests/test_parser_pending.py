"""F8b — testes da Fase B1.

Cobre os helpers introduzidos no `main.py` que coletam o `prefilled` para o
modal de pendência. Os testes não dependem de PDF real — atacam diretamente
o módulo `main` em modo non-interactive simulado.

Para o teste end-to-end de subprocess + pending_rows.json em disco, ver
test_parser_pending_e2e.py (Fase B3).
"""
import importlib
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


@pytest.fixture
def main_module():
    """Re-importa o módulo main em estado limpo e ativa NON_INTERACTIVE_MODE.

    Garante isolamento entre testes — qualquer teste que mexe em globals do
    `main` (NON_INTERACTIVE_MODE, _PENDING_PREFILLED) volta ao default depois.
    """
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    if "main" in sys.modules:
        del sys.modules["main"]
    main = importlib.import_module("main")

    # Ativa o caminho PROD para os testes que exercitam o tracker.
    original_flag = main.NON_INTERACTIVE_MODE
    main.NON_INTERACTIVE_MODE = True
    main._reset_pending_prefilled()

    yield main

    main.NON_INTERACTIVE_MODE = original_flag
    main._reset_pending_prefilled()


def test_pending_track_armazena_valor_escalar(main_module):
    main_module._pending_track("cnpj", "12.345.678/0001-90")
    assert main_module._PENDING_PREFILLED == {"cnpj": "12.345.678/0001-90"}


def test_pending_track_desencapsula_dict_canonical_do_parser(main_module):
    """Parser passa structs no formato {'cnpj': '...'} — track precisa achatar."""
    main_module._pending_track("cnpj", {"cnpj": "12.345.678/0001-90"})
    main_module._pending_track("fornecedor", {"fornecedor": "Acme Energia"})
    assert main_module._PENDING_PREFILLED == {
        "cnpj": "12.345.678/0001-90",
        "fornecedor": "Acme Energia",
    }


def test_pending_track_ignora_none_e_string_vazia(main_module):
    """None ou '' = ausência, não pode poluir o prefilled."""
    main_module._pending_track("cnpj", None)
    main_module._pending_track("fornecedor", "")
    main_module._pending_track("data_emissao", {"data_emissao": None})
    assert main_module._PENDING_PREFILLED == {}


def test_pending_track_no_op_em_modo_dev(main_module):
    """Em modo interativo (DEV), track não deve gastar memória — comportamento
    original do parser preservado."""
    main_module.NON_INTERACTIVE_MODE = False
    main_module._pending_track("cnpj", "12.345.678/0001-90")
    assert main_module._PENDING_PREFILLED == {}


def test_reset_pending_zera_acumulador(main_module):
    main_module._pending_track("cnpj", "X")
    main_module._pending_track("fornecedor", "Y")
    main_module._reset_pending_prefilled()
    assert main_module._PENDING_PREFILLED == {}


def test_solicitar_campo_humano_snapshot_prefilled_na_excecao(main_module):
    """O core do B1: quando o parser falha pedindo input, a exceção carrega
    o snapshot do que já havia sido extraído. O adapter (B3) vai serializar
    isso em pending_rows.json para o frontend mostrar no modal."""
    main_module._pending_track("cnpj", "12.345.678/0001-90")
    main_module._pending_track("fornecedor", "Acme Energia")
    main_module._pending_track("data_emissao", "2026-04-12")

    with pytest.raises(main_module.ParserCampoFaltante) as exc_info:
        main_module._solicitar_campo_humano("numero_nf", contexto="NF-123.pdf")

    exc = exc_info.value
    assert exc.campo == "numero_nf"
    assert exc.contexto == "NF-123.pdf"
    assert exc.prefilled == {
        "cnpj": "12.345.678/0001-90",
        "fornecedor": "Acme Energia",
        "data_emissao": "2026-04-12",
    }


def test_prefilled_e_copia_independente_nao_referencia(main_module):
    """Snapshot precisa ser cópia — se o parser continuar adicionando campos
    depois da exceção, o prefilled da exceção original não pode mutar."""
    main_module._pending_track("cnpj", "X")
    try:
        main_module._solicitar_campo_humano("fornecedor", contexto="ctx")
    except main_module.ParserCampoFaltante as exc:
        snapshot_inicial = exc.prefilled
        main_module._pending_track("data_emissao", "2026-04-12")
        # Snapshot original não muda mesmo se _PENDING_PREFILLED é mutado depois.
        assert snapshot_inicial == {"cnpj": "X"}
        assert "data_emissao" not in snapshot_inicial


def test_prefilled_vazio_quando_falha_no_primeiro_campo(main_module):
    """PDF onde o cnpj (primeiro campo da chain) já falha — prefilled
    legitimamente vazio. Modal vai esconder o bloco prefilled."""
    with pytest.raises(main_module.ParserCampoFaltante) as exc_info:
        main_module._solicitar_campo_humano("cnpj", contexto="NF-456.pdf")
    assert exc_info.value.prefilled == {}


# ─── F8b fix 2026-05-14: campo canônico + missing expandido ─────────────

def test_canonical_field_extrai_chave_do_label_humano(main_module):
    """'ncm (produto 1 de 1)' → 'ncm'. Sem essa normalização, /resolve
    receberia chave que não bate com default_nf_template."""
    assert main_module._canonical_field("ncm (produto 1 de 1)") == "ncm"
    assert main_module._canonical_field("cnpj") == "cnpj"
    assert main_module._canonical_field("data_emissao") == "data_emissao"
    # Espaços extras tolerados.
    assert main_module._canonical_field("ncm  (produto)") == "ncm"


def test_canonical_field_preserva_chave_exotica_inteira(main_module):
    """'numero_de_produtos_nesta_nf' não tem espaço — passa cru. Caller
    filtra: se não está em default_nf_template, fica fora do missing."""
    assert main_module._canonical_field("numero_de_produtos_nesta_nf") == "numero_de_produtos_nesta_nf"
