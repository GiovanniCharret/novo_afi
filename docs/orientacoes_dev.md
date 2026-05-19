# Orientações para o projeto de desenvolvimento do parser

**Para quem mantém `leitor_de_pdf/` (`main.py`, `ocr_reader.py`).**

O parser roda em dois lugares: no terminal (desenvolvimento) e dentro do
backend `recebimento_notas` (produção). Para funcionar nos dois sem o backend
precisar editar o parser a cada versão, o parser expõe **um único contrato**.
Este documento descreve esse contrato e o código exato a manter.

> Contexto: até 2026-05-19 o backend editava o `main.py` à mão a cada pull
> (marcadores `FASE DEV`/`FASE PROD`). Isso acabou. Agora o backend roda os
> arquivos do parser intactos via `parser_runner.py` (ver `docs/PARSER_RUNNER.md`)
> — desde que o contrato abaixo seja respeitado.

## O contrato — `ParserCampoFaltante`

Quando o parser não consegue extrair um campo obrigatório, ele **levanta uma
exceção** `ParserCampoFaltante` carregando o nome do campo e o que já foi
extraído. Não chama mais `input()`.

- O backend captura essa exceção → abre um modal de preenchimento manual
  mostrando os campos já extraídos preenchidos e pedindo só o que falta.
- No terminal, se você quiser o prompt interativo de volta, envolva a chamada
  do parser num `try/except ParserCampoFaltante` e faça o `input()` lá.

### O que NÃO colocar no parser

Não adicione lógica de produção ao `main.py`/`ocr_reader.py`: nada de
`argparse`, exit codes, `pending_rows.json`, flags `NON_INTERACTIVE`. Isso é
responsabilidade do `parser_runner.py`, no lado do backend. O parser só
precisa do `ParserCampoFaltante`.

## Código a manter — `ocr_reader.py`

Define a classe e a função de fallback. `_solicitar_campo_humano` reúne o
`prefilled` a partir do dict `nf` que `_montar_nf_multiplos_passes` está
montando (lido do frame chamador).

```python
class ParserCampoFaltante(Exception):
    """Campo obrigatório que o parser não conseguiu extrair automaticamente.

    Carrega `prefilled` — o que o parser JÁ capturou desta NF — para que o
    preenchimento humano (modal do backend, ou um loop de terminal) mostre só
    o que falta de fato, sem o operador redigitar o que já foi extraído.
    """

    def __init__(self, campo, prefilled=None):
        self.campo = campo
        self.prefilled = dict(prefilled or {})
        super().__init__(f"Campo obrigatório não extraído: '{campo}'")


def _solicitar_campo_humano(campo, contexto=""):
    """Sinaliza um campo obrigatório não extraído pelo OCR.

    Levanta `ParserCampoFaltante` carregando o que o pass de OCR já montou —
    o dict `nf` que `_montar_nf_multiplos_passes` preenche no frame chamador.
    """
    import sys
    prefilled = {}
    frame = sys._getframe(1)
    while frame is not None:
        nf = frame.f_locals.get("nf")
        if isinstance(nf, dict):
            prefilled = {k: v for k, v in nf.items() if v not in (None, "")}
            break
        frame = frame.f_back
    raise ParserCampoFaltante(campo, prefilled)
```

## Código a manter — `main.py`

Importa a classe de `ocr_reader` (módulo único — evita import circular) e
levanta a mesma exceção. O `prefilled` é coletado varrendo os frames da pilha
atrás das variáveis do pipeline.

```python
# no bloco de imports, junto dos outros de ocr_reader:
from ocr_reader import extrair_dados_nf_servico_do_pdf, product_or_service, ParserCampoFaltante


# Mapeia variáveis do pipeline (dicts canônicos) -> chave do campo na NF.
_PREFILL_METADADOS = {
    "cnpj_fornecedor": "cnpj",
    "nome_fornecedor": "fornecedor",
    "data_nota_fiscal": "data_emissao",
    "numero_nota_fiscal": "numero_nf",
    "tipo_nota_fical": "tipo_nota",
}
_PREFILL_TRANSACAO = ("descricao", "ncm", "quant", "preco_unitario", "valor")


def _coletar_prefilled():
    """Varre os frames da pilha e reúne o que o pipeline já extraiu desta NF
    (metadados + 1ª transação) para o `prefilled` da `ParserCampoFaltante`.
    Tolerante: variável ainda não atribuída simplesmente não entra no dict.
    """
    import sys
    prefilled = {}
    frame = sys._getframe(2)  # pula _coletar_prefilled + _solicitar_campo_humano
    while frame is not None:
        escopo = {**frame.f_globals, **frame.f_locals}
        for var, chave in _PREFILL_METADADOS.items():
            if chave not in prefilled:
                val = escopo.get(var)
                if isinstance(val, dict) and val.get(chave) not in (None, ""):
                    prefilled[chave] = val[chave]
        trans = escopo.get("list_product_service_transation")
        if isinstance(trans, list) and trans and isinstance(trans[0], dict):
            for k in _PREFILL_TRANSACAO:
                if k not in prefilled and trans[0].get(k) not in (None, ""):
                    prefilled[k] = trans[0][k]
        frame = frame.f_back
    return prefilled


def _solicitar_campo_humano(campo, contexto):
    """Sinaliza um campo obrigatório não extraído pelo pipeline.

    Levanta `ParserCampoFaltante` (definida em `ocr_reader.py`) carregando em
    `prefilled` o que o parser já capturou desta NF.
    """
    raise ParserCampoFaltante(campo, _coletar_prefilled())
```

### ⚠️ Manutenção do `_PREFILL_METADADOS`

`_coletar_prefilled` encontra os campos extraídos pelos **nomes das variáveis**
do pipeline. Se um refactor renomear `cnpj_fornecedor`, `data_nota_fiscal`,
`numero_nota_fiscal`, `nome_fornecedor`, `tipo_nota_fical` ou
`list_product_service_transation`, **atualize `_PREFILL_METADADOS` /
`_PREFILL_TRANSACAO` no mesmo commit**. Se esquecer, o campo simplesmente não
entra no `prefilled` (degrada — o modal pede ele de novo —, não quebra).

## Demais premissas que o `parser_runner` assume

Continuam valendo (não são novidade, mas se mudarem, avise quem mantém o
backend para ajustar o `parser_runner.py`):

- `contrato_config.selecionar_contrato(numero)` resolve **sem prompt** quando
  `numero` é uma chave válida de `base_contratos.json`.
- O pipeline lê PDFs de `./nfs_analise` e grava o xlsx em `./output_dfs`
  (caminhos relativos ao cwd).
- Arquivos de dados lidos via `Path(__file__).parent` (hoje: `block_cnpj.json`)
  ficam ao lado do `main.py`. Ao adicionar um novo, avise o backend (ele
  precisa copiá-lo para `leitor_pdf/`).

## Checklist ao publicar uma versão nova do parser

- [ ] `ocr_reader.py` tem a classe `ParserCampoFaltante` e o
      `_solicitar_campo_humano` que a levanta.
- [ ] `main.py` importa `ParserCampoFaltante` de `ocr_reader` e o
      `_solicitar_campo_humano` a levanta via `_coletar_prefilled`.
- [ ] `_PREFILL_METADADOS` reflete os nomes atuais das variáveis do pipeline.
- [ ] Nenhuma lógica de produção (argparse / exit codes / flags) foi adicionada.
- [ ] Novo arquivo de dados lido por `__file__`? Avise o backend.
