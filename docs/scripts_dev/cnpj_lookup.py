import json
import requests
from pathlib import Path

_CACHE_PATH = Path(__file__).resolve().parent / "cnpj.json"
_CACHE = None  # carregado lazy na 1ª chamada; mantido em memória pelo resto do batch


def _carregar_cache_em_memoria():
    """Lê e normaliza o cnpj.json uma única vez. Em batch grande evita milhares
    de leituras de disco + parses de json para o mesmo arquivo."""
    if not _CACHE_PATH.exists():
        raise ValueError('O json de cnpjs sumiu')
    with open(_CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return data
    cache_normalizado = {}
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, dict):
                cnpj_item = "".join(filter(str.isdigit, str(value.get("cnpj", ""))))
                nome_item = str(value.get("nome", "")).strip()
                if cnpj_item and nome_item:
                    cache_normalizado[cnpj_item] = nome_item
    return cache_normalizado


def _salvar_cache(cache):
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def consulta_nome_fornecedor(cnpj):
    """
    Retorna o nome do fornecedor dado um CNPJ.
    Busca primeiro no cache local (cnpj.json); em caso de miss, consulta open.cnpja.com
    e salva o resultado no cache.

    :param cnpj: string com o CNPJ (pontuado ou só dígitos)
    :return: dict {'fornecedor': nome} ou string de erro
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = _carregar_cache_em_memoria()

    cnpj = "".join(filter(str.isdigit, cnpj))

    if cnpj in _CACHE:
        return {'fornecedor': _CACHE[cnpj]}

    url = f"https://open.cnpja.com/office/{cnpj}"
    try:
        # timeout obrigatório: sem ele, uma única chamada travada à API trava o
        # batch inteiro. 10s cobre o caso bom + dá margem para latência.
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            dados = response.json()
            nome_empresa = dados.get('company', {}).get('name', 'Nome não encontrado')
            _CACHE[cnpj] = nome_empresa
            _salvar_cache(_CACHE)
            return {'fornecedor': nome_empresa}
        elif response.status_code == 429:
            return "Erro: Limite de requisições atingido (max 5 por minuto)."
        else:
            return f"Erro na consulta: Status {response.status_code}"
    except Exception as e:
        return f"Ocorreu um erro: {e}"
