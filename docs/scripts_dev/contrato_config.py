"""Carrega `base_contratos.json` e oferece seleção (programática ou interativa).

`selecionar_contrato(numero)` é o único ponto de entrada. Retorna um dict
compatível com `consolidate_data_to_dict` em `main.py`:
    {
      'contrato': '<numero> - <sigla>,<uf> - <tranche>',  # estampado no Excel
      'numero_contrato': '<numero>',                        # uso interno (filename, etc)
      'valor_contrato': int,
      'valor_cde': int,
    }
Se `numero` for None ou não estiver na base, abre menu numerado no terminal.
"""
import json
from pathlib import Path

_BASE_PATH = Path(__file__).resolve().parent / "base_contratos.json"
_BASE = None


def _carregar_base():
    global _BASE
    if _BASE is None:
        with open(_BASE_PATH, encoding="utf-8") as f:
            _BASE = json.load(f)
    return _BASE


def _formatar_contrato_str(numero, info):
    return f"{numero} - {info['sigla']},{info['uf']} - {info['tranche']}"


def _construir_dict(numero, info):
    return {
        "contrato": _formatar_contrato_str(numero, info),
        "numero_contrato": numero,
        "valor_contrato": info["valor_contrato"],
        "valor_cde": info["valor_cde"],
    }


def _menu_interativo(base):
    chaves = list(base.keys())
    print("\n=== Seleção de contrato (base_contratos.json) ===")
    for i, k in enumerate(chaves, start=1):
        info = base[k]
        print(f"  [{i:>3}] {k}  —  {info['sigla']} {info['tranche']}")
    while True:
        escolha = input(
            f"\nDigite o número [1..{len(chaves)}] ou cole a chave exata: "
        ).strip()
        if escolha.isdigit():
            idx = int(escolha)
            if 1 <= idx <= len(chaves):
                return chaves[idx - 1]
            print(f"  Fora do intervalo (1..{len(chaves)}). Tente de novo.")
            continue
        if escolha in base:
            return escolha
        print("  Chave não encontrada na base. Tente de novo.")


def selecionar_contrato(numero=None):
    base = _carregar_base()
    if numero is None or numero not in base:
        if numero is not None:
            print(f"[contrato_config] '{numero}' não está em base_contratos.json — escolha manualmente.")
        numero = _menu_interativo(base)
    return _construir_dict(numero, base[numero])
