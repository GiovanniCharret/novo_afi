"""
Solução da IA usando pytesseract
"""

#C:\Users\GiovanniAzevedoCharr\AppData\Local\Programs\Tesseract-OCR
import re
import os
import unicodedata
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytesseract
import cv2
import numpy as np
from PIL import Image
from pdf2image import convert_from_path
from cnpj_lookup import consulta_nome_fornecedor

# DICIONÁRIO QUE RECEBERÁ OS DADOS DO PDF
default_nf_template = {
    # 'item': None, Será preenchido posteriormente por método reset_index
    #'codigo_produto': None,
    'descricao': None,
    'ncm': None, #Nomenclatura comum do mercosul
    'quant': None,
    'preco_unitario': None,
    'numero_nf': None,
    'tipo_nota': None,
    'data_emissao': None,
    'cnpj': None,
    'fornecedor': None,
    'valor': None,
    'contrato': None,
}

RE_DATE = re.compile(r'\d{2}/\d{2}/\d{4}')
# Regex tolerante a confusões OCR no campo data (D→0, O→0, l/I→1, S→5, B→8, n/N→8).
# Usado como fallback em extrair_data_emissao após o regex estrito falhar.
_RE_DATE_TOLERANTE = re.compile(r'[\dDOoIlSBnN]{2}/[\dDOoIlSBnN]{2}/[\dDOoIlSBnN]{4}')

# Pré-computações: chaves/labels normalizados via NFKD+upper são constantes; computar
# uma vez no escopo do módulo evita milhares de chamadas redundantes a
# unicodedata.normalize em batch grande.
def _norm_const(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).upper()

_CHAVES_NF_NORM = tuple(_norm_const(c) for c in (
    "NOTA FISCAL ELETRONICA", "NFS-E", "TOMADOR", "SERVICOS", "DESCRICAO",
    "DISCRIMINACAO", "PRODUTOS", "VALOR TOTAL", "DADOS ADICIONAIS",
))

_FRONTEIRA_INICIO_NORM = tuple(_norm_const(c) for c in (
    "DISCRIMINACAO DOS SERVICOS", "DESCRIÇÃO DOS SERVIÇOS",
    "DESCRICAO DOS SERVICOS", "Discriminação do(s)",
))

_FRONTEIRA_FIM_NORM = tuple(_norm_const(c) for c in (
    "OUTRAS INFORMACOES", "OUTRAS INFORMAÇOES", "OUTRASINFORMAÇÕES", "COFINS",
))

_NUM_NF_FALLBACK_NORM = tuple(_norm_const(c) for c in (
    "NUMERO DA NOTA", "NÚMERO DA NOTA", "SECRETARIA MUNICIPAL DA FAZENDA",
    "NOTA FISCAL ELETRONICA", "NFS-E", "Númeroda Nota", "NúmerodaNota",
))

_VALOR_LABELS = ("VALOR TOTAL DA NOTA", "VALOR DA NOTA", "VALOR TOTAL",
                 "VALOR DO(S) SERVICO(S)", "TOTAL DO(S) SERVICO(S)")
_VALOR_LABELS_NORM = tuple(_norm_const(c) for c in _VALOR_LABELS)

# GLOBAIS --------------------------
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Users\GiovanniAzevedoCharr\AppData\Local\Programs\Tesseract-OCR\tesseract.exe").strip()
POPLLER_PATH = os.getenv("POPLLER_PATH", "poppler-25.12.0/Library/bin").strip() or None
# Controlado por main.py via: import ocr_reader; ocr_reader.MODO_LLM_OCR = MODO_LLM
MODO_LLM_OCR = "precisao"

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

CAMINHO_RAIZ = "./nfs_analise"
SAIDA_RAIZ = './output_dfs'
# Formato de dicionário por causa da função consolidate_data_to_dict que só recebe
# argumentos em dicionário. Em execuções via main.py, é sobrescrito por
# `_ocr_mod.CONTRATO = CONTRATO` no topo de main.py. Em standalone runs, é
# preenchido lazy na 1ª chamada que precisar via _get_contrato().
CONTRATO = None


def _get_contrato():
    global CONTRATO
    if CONTRATO is None:
        from contrato_config import selecionar_contrato
        CONTRATO = selecionar_contrato()
    return CONTRATO


# =============================================================================
# VALIDAÇÃO E CORREÇÃO OCR
# =============================================================================

# Substituições de caracteres típicos de OCR em contexto numérico (CNPJ)
_OCR_DIGIT_MAP = str.maketrans({
    'n': '8', 'N': '8',
    'l': '1', 'I': '1',
    'O': '0', 'o': '0',
    'S': '5',
    'B': '8',
    ',': '.',
})

# Substituições típicas em contexto de data (ex.: OCR `D5/05/2021` → `05/05/2021`).
# Não inclui `,` porque data não usa pontuação decimal.
_OCR_DIGIT_MAP_DATA = str.maketrans({
    'D': '0',
    'O': '0', 'o': '0',
    'l': '1', 'I': '1',
    'S': '5',
    'B': '8',
    'n': '8', 'N': '8',
})


def _corrigir_ocr_cnpj(texto):
    """Aplica substituições de confusões OCR típicas — usar só em candidatos a CNPJ."""
    return texto.translate(_OCR_DIGIT_MAP)


def _validar_cnpj(cnpj_str):
    """Valida CNPJ pelo algoritmo módulo 11. Aceita formato pontuado ou só dígitos."""
    digitos = re.sub(r"\D", "", cnpj_str or "")
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False

    def _digito(d, pesos):
        s = sum(int(c) * p for c, p in zip(d, pesos))
        r = s % 11
        return 0 if r < 2 else 11 - r

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return (int(digitos[12]) == _digito(digitos[:12], pesos1) and
            int(digitos[13]) == _digito(digitos[:13], pesos2))


# =============================================================================
# FUNÇÕES BASE
# =============================================================================

def confirma_tipo_documento(texto):
    """
    Chamada só quando o pdfplumber falha, então preciso confirmar que
    é um nf que meu script não resolve.

    Ela confirma se o extraído pelo pytesseract, usando OCR,
    tem indícios suficientes de Nota Fiscal. Já que poderia ser outros
    arquivos, tipo borderô de pagamento.
    """

    def normalizar(s):
        s = "" if s is None else str(s)
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s.upper()

    texto_normalizado = normalizar(texto)
    qtd_chaves_encontradas = sum(1 for chave in _CHAVES_NF_NORM if chave in texto_normalizado)
    return qtd_chaves_encontradas >= 4


def normalizar_texto(s):
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def fatiar_texto_nf(texto):
    texto_normalizado = normalizar_texto(texto)

    idx_inicio = -1
    for item_norm in _FRONTEIRA_INICIO_NORM:
        pos = texto_normalizado.find(item_norm)
        if pos != -1:
            idx_inicio = pos
            break

    idx_fim = -1
    for item_norm in _FRONTEIRA_FIM_NORM:
        pos = texto_normalizado.find(item_norm)
        if pos != -1:
            idx_fim = pos
            break

    if idx_inicio != -1 and (idx_fim == -1 or idx_fim <= idx_inicio):
        trecho = texto[idx_inicio:]
        return {
            "inicio": texto[:idx_inicio],
            "meio": trecho,
            "fim": trecho,
        }

    return {
        "inicio": texto[:idx_inicio] if idx_inicio != -1 else texto,
        "meio": texto[idx_inicio:idx_fim] if idx_inicio != -1 and idx_fim != -1 and idx_fim > idx_inicio else "",
        "fim": texto[idx_fim:] if idx_fim != -1 else "",
    }


# =============================================================================
# EXTRATORES DE CAMPO
# =============================================================================

def extrair_descricao(partes_nf):
    texto_meio = partes_nf.get("meio", "").strip()
    if not texto_meio:
        raise ValueError("OCR: não foi possível extrair descrição (trecho 'meio' vazio).")

    padrao = (
        r"(?:DISCRIMINACAO DOS SERVICOS|DISCRIMINAÇÃO DOS SERVIÇOS|"
        r"DESCRICAO DOS SERVICOS|DESCRIÇÃO DOS SERVIÇOS)"
        r"(.*?)"
        r"Discriminação do(s) Serviço"
        r"(?:VALORES DA NOTA|VALOR TOTAL|DADOS DA OBRA|OBSERVACOES DA NOTA|$)"
    )
    match = re.search(padrao, texto_meio, flags=re.IGNORECASE | re.DOTALL)
    if match:
        descricao = " ".join(match.group(1).split()).strip()
    else:
        descricao = " ".join(texto_meio.split()).strip()

    if not descricao:
        raise ValueError("OCR: não foi possível extrair descrição.")
    return descricao



def extrair_numero_nf(texto_inicio):
    """
    Extrai número da NF:
    1) Corta texto antes da data de emissão
    2) Busca número próximo do primeiro marcador encontrado em texto_fallback
    3) Stitch de grupos de dígitos separados por espaço (OCR split)
    4) Retorna o candidato mais longo (maior chance de ser o número completo)
    """
    texto_inicio_normalizado = normalizar_texto(texto_inicio)

    match_data = RE_DATE.search(texto_inicio_normalizado)
    cabecalho = texto_inicio_normalizado[:match_data.start()] if match_data else texto_inicio_normalizado

    for mask_norm in _NUM_NF_FALLBACK_NORM:
        idx = cabecalho.find(mask_norm)
        if idx == -1:
            continue

        janela_inicio = max(0, idx - 120)
        janela_fim    = min(len(cabecalho), idx + 180)
        janela        = cabecalho[janela_inicio:janela_fim]

        # Stitch: une grupos de dígitos separados por espaço (OCR split, ex: "201 900000002447")
        janela_stitched = re.sub(r'(\d+)\s+(\d+)', lambda m: m.group(1) + m.group(2), janela)
        candidatos = re.findall(r"(?<!\d)\d{4,10}(?!\d)", janela_stitched)
        if candidatos:
            return max(candidatos, key=len)

    raise ValueError("OCR: não foi possível extrair número da NF.")


def extrair_data_emissao(texto_inicio):
    # 1) Caminho rápido: regex estrito (dd/mm/yyyy, só dígitos).
    match = RE_DATE.search(texto_inicio)
    if match:
        return match.group(0)
    # 2) Fallback OCR: regex tolerante a letras confundíveis com dígito,
    # aplica `_OCR_DIGIT_MAP_DATA` no candidato e valida via datetime.strptime.
    for candidato in _RE_DATE_TOLERANTE.findall(texto_inicio):
        corrigido = candidato.translate(_OCR_DIGIT_MAP_DATA)
        try:
            datetime.strptime(corrigido, "%d/%m/%Y")
            return corrigido
        except ValueError:
            continue
    return None


def extrair_cnpj(texto_inicio):
    """
    Estratégias em ordem crescente de tolerância:
    1) Regex estrita para CNPJ pontuado
    2) CNPJ próximo do label CPF/CNPJ (somente dígitos e pontuação esperada)
    3) Label + tolerância a chars não-dígito + correção OCR
    """

    def _formatar_cnpj(digitos):
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"

    # 1) Regex estrita
    match_pontuado = re.search(r"\d{2}\.\d{3}\.\d{3}\s*/\s*\d{4}\s*-\s*\d{2}", texto_inicio)
    if match_pontuado:
        digitos = re.sub(r"\D", "", match_pontuado.group(0))
        if len(digitos) == 14:
            return _formatar_cnpj(digitos)

    # 2) CNPJ próximo dos marcadores CPF/CNPJ (variações comuns de OCR)
    match_label = re.search(
        r"(?:CPF\s*/?\s*CNPJ|CPFICNPJ|CPFCNPJ|CPFICNPU|CPFICNPI)\s*[:\-]?\s*([0-9\.\-/\s]{14,25})",
        texto_inicio,
        flags=re.IGNORECASE,
    )
    if match_label:
        digitos = re.sub(r"\D", "", match_label.group(1))
        if len(digitos) == 14:
            return _formatar_cnpj(digitos)

    # 3) Mesma label, com tolerância a chars não-dígito + correção OCR
    match_tolerante = re.search(
        r"(?:CPF\s*/?\s*CNPJ|CPFICNPJ|CPFCNPJ|CPFICNPU|CPFICNPI)\s*[:\-]?\s*"
        r"([0-9a-zA-Z\.\,\-/\s]{12,25})",
        texto_inicio,
        flags=re.IGNORECASE,
    )
    if match_tolerante:
        candidato = match_tolerante.group(1).strip()
        corrigido = _corrigir_ocr_cnpj(candidato)
        digitos = re.sub(r"\D", "", corrigido)
        if len(digitos) == 14:
            return _formatar_cnpj(digitos)

    raise ValueError("OCR: não foi possível extrair CNPJ.")


def extrair_valor(texto_fim, texto_meio):
    if not texto_fim:
        raise ValueError("OCR: não foi possível extrair valor (trecho 'fim' vazio).")

    texto_norm = normalizar_texto(texto_fim)

    for label_norm in _VALOR_LABELS_NORM:
        idx = texto_norm.find(label_norm)
        if idx == -1:
            continue
        trecho = texto_fim[idx: idx + 320]
        linhas = [ln.strip() for ln in trecho.splitlines() if ln.strip()]
        if len(linhas) >= 2:
            valores_linha = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", linhas[1])
            if valores_linha:
                return valores_linha[-1]
        valores_label = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", trecho)
        if valores_label:
            return valores_label[0]

    # Fallback: procura os labels no trecho do meio da nota
    texto_meio = (texto_meio or "").strip()
    if texto_meio:
        texto_meio_norm = normalizar_texto(texto_meio)
        for label_norm in _VALOR_LABELS_NORM:
            idx = texto_meio_norm.find(label_norm)
            if idx == -1:
                continue
            trecho = texto_meio[idx: idx + 320]
            linhas = [ln.strip() for ln in trecho.splitlines() if ln.strip()]
            if len(linhas) >= 2:
                valores_linha = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", linhas[1])
                if valores_linha:
                    return valores_linha[-1]
            valores_label = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", trecho)
            if valores_label:
                return valores_label[0]

    raise ValueError("OCR: não foi possível extrair valor.")


# =============================================================================
# MONTAGEM DO TEMPLATE + FALLBACK HUMANO
# =============================================================================

def _solicitar_campo_humano(campo, contexto=""):
    """Pausa o batch e pede ao operador que digite o valor do campo não extraído.

    Ponto de extensão: inserir instâncias automáticas adicionais (ex.: LLM multimodal)
    ANTES do input humano — quando nenhuma resolver, o humano digita.
    """
    print(f"\n[REVISÃO HUMANA] Arquivo: {contexto}")
    print(f"  Campo '{campo}' não pôde ser extraído automaticamente.")
    # ── ponto de extensão ─────────────────────────────────────────────────────
    # Ex.:  valor = _extrair_via_llm(campo, contexto)
    #       if valor: return valor
    # ─────────────────────────────────────────────────────────────────────────
    valor = input(f"  Digite o valor para '{campo}' (ou Enter para deixar em branco): ").strip()
    return valor or None


# =============================================================================
# PRÉ-PROCESSAMENTO DE IMAGEM
# =============================================================================

def _remover_linhas_tabela(img_gray_np, kernel_size=40):
    """
    Remove linhas horizontais e verticais da imagem para melhorar o OCR.

    Recebe um array numpy grayscale (já convertido pelo caller) — em batch
    grande, evita refazer `np.array(pil.convert("L"))` por pass quando a mesma
    imagem é processada com kernels diferentes.

    kernel_size controla a agressividade:
      20 → remoção leve (linhas finas, menos colateral em caracteres)
      40 → remoção agressiva (padrão original — pode corromper dígitos próximos a bordas)
    """
    _, binaria = cv2.threshold(img_gray_np, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_size))
    linhas_h = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel_h)
    linhas_v = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel_v)
    linhas   = cv2.add(linhas_h, linhas_v)

    sem_linhas = cv2.subtract(binaria, linhas)
    resultado  = cv2.bitwise_not(sem_linhas)
    return Image.fromarray(resultado)


def extrair_texto_ocr_primeira_pagina(pdf_path, poppler_path=POPLLER_PATH, lang="por", kernel_size=None):
    """
    kernel_size=None → sem remoção de linhas (imagem original)
    kernel_size=20   → remoção leve
    kernel_size=40   → remoção agressiva (comportamento anterior)
    """
    images = convert_from_path(
        pdf_path,
        size=(3508, None),
        poppler_path=poppler_path,
        first_page=1,
        last_page=1,
        grayscale=True,
    )
    if kernel_size:
        img_gray = np.array(images[0].convert("L"))
        img = _remover_linhas_tabela(img_gray, kernel_size=kernel_size)
    else:
        img = images[0]
    return pytesseract.image_to_string(img, lang=lang, config="--oem 3 --psm 6")


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def product_or_service(texto_ou_df):
    """
    Classifica a NF como produto ou serviço com base em keywords.
    Aceita string de texto puro (path OCR) ou DataFrame com coluna "text" (path pdfplumber).
    Retorna: "product" ou "service"
    """
    if isinstance(texto_ou_df, pd.DataFrame):
        corpus = " ".join(texto_ou_df["text"].fillna("").astype(str).tolist())
    else:
        corpus = str(texto_ou_df or "")

    product_keywords = [
        "CÓDIGO PRODUTO", "ncm", "NCM", "cfop", "CFOP",
        "icms", "UNITÁRIO", "ipi", "quant", "QTD", "valor unitario",
    ]
    product_score = sum(1 for k in product_keywords if k in corpus)

    return "product" if product_score > 1 else "service"


def _pontuar_texto(partes):
    """Pontua quantos campos críticos são extraíveis/válidos a partir das partes
    já fatiadas. Recebe o dict retornado por `fatiar_texto_nf` para evitar
    fatiamento e normalização redundantes (em batch grande, eram 2× por pass).
    """
    inicio = partes.get("inicio", "")
    score  = 0

    try:
        cnpj = extrair_cnpj(inicio)
        score += 2 if _validar_cnpj(cnpj) else 1
    except ValueError:
        pass

    if extrair_data_emissao(inicio):
        score += 1

    try:
        extrair_valor(partes.get("fim", ""), partes.get("meio", ""))
        score += 1
    except ValueError:
        pass

    try:
        num = extrair_numero_nf(inicio)
        if num:
            score += 1
    except ValueError:
        pass

    return score


def _montar_nf_multiplos_passes(passes_ordenados, contexto=""):
    """
    Monta o dict da NF percorrendo os passes em ordem de score decrescente.

    Para cada campo, tenta o pass de melhor score primeiro. Se falhar (ValueError
    ou None), tenta o segundo, depois o terceiro. Só chama _solicitar_campo_humano
    se todos os passes falharem para aquele campo.

    passes_ordenados: lista de dicts já ordenada por score desc, cada item contém
        {"nome": str, "score": int, "texto": str, "partes": {"inicio", "meio", "fim"}}
    contexto: nome do arquivo PDF, exibido nas mensagens de revisão humana.
    """
    # Parte do template padrão com campos fixos que não dependem de extração
    nf = default_nf_template.copy()
    nf["ncm"]   = 'não se aplica'  # NFS-e de serviço nunca tem NCM
    nf["quant"] = '1'               # Serviço não tem quantidade unitária

    # --- descricao ---------------------------------------------------------------
    # Para descrição, ignora a ordem de score e tenta sempre sem_remocao primeiro:
    # a erosão morfológica do OpenCV preserva bordas numéricas mas corrompe blocos
    # de texto livres — quanto mais caracteres, mais dano acumulado. sem_remocao
    # maximiza a fidelidade do texto. Só cai nos demais passes se sem_remocao falhar.
    passes_descricao = sorted(passes_ordenados, key=lambda p: 0 if p["nome"] == "sem_remocao" else 1)
    for p in passes_descricao:
        try:
            nf["descricao"] = extrair_descricao(p["partes"])
            break
        except ValueError:
            pass

    # --- valor -------------------------------------------------------------------
    # extrair_valor recebe o trecho final da nota (onde fica "VALOR TOTAL") e o
    # trecho do meio como fallback interno. Ambos vêm de partes["fim"] e partes["meio"].
    # preco_unitario e valor recebem o mesmo número — em NFS-e de serviço o preço
    # unitário é o próprio valor total da nota.
    for p in passes_ordenados:
        try:
            preco = extrair_valor(p["partes"].get("fim", ""), p["partes"].get("meio", ""))
            nf["preco_unitario"] = preco
            nf["valor"]          = preco
            break
        except ValueError:
            pass

    # --- numero_nf ---------------------------------------------------------------
    # Guarda verificação extra (if num) porque extrair_numero_nf pode retornar
    # string vazia em casos de candidatos zerados, mesmo sem levantar exceção.
    for p in passes_ordenados:
        try:
            num = extrair_numero_nf(p["partes"].get("inicio", ""))
            if num:
                nf["numero_nf"] = num
                break
        except ValueError:
            pass

    # --- tipo_nota ---------------------------------------------------------------
    # Não é campo crítico e não tem fallback humano. Usa o texto completo do melhor
    # pass para maximizar a detecção de keywords de produto (NCM, CFOP, ICMS aparecem
    # no corpo da nota, não só no cabeçalho). Traduz para português para manter
    # consistência com os valores históricos do path OCR.
    tipo = product_or_service(passes_ordenados[0]["texto"])
    nf["tipo_nota"] = 'serviço' if tipo == "service" else 'produto'

    # --- data_emissao ------------------------------------------------------------
    # extrair_data_emissao retorna None (não levanta exceção) quando não encontra
    # a data, por isso o controle é feito por "if data" em vez de try/except.
    for p in passes_ordenados:
        data = extrair_data_emissao(p["partes"].get("inicio", ""))
        if data:
            nf["data_emissao"] = data
            break

    # --- cnpj --------------------------------------------------------------------
    # CNPJ é o campo mais sensível a corrupção de OCR (bordas de tabela destroem
    # dígitos). Por isso a busca percorre todos os passes antes de desistir.
    # extrair_cnpj tenta 3 estratégias internas (regex estrita → label → tolerante+correção).
    for p in passes_ordenados:
        try:
            cnpj = extrair_cnpj(p["partes"].get("inicio", ""))
            if cnpj:
                nf["cnpj"] = cnpj
                break
        except ValueError:
            pass

    # --- fornecedor --------------------------------------------------------------
    # Derivado do CNPJ: consulta cache local (cnpj.json) e, em caso de miss,
    # chama a API open.cnpja.com. Se o CNPJ não foi encontrado em nenhum pass,
    # fornecedor fica None e será tratado no fallback humano via campo "cnpj".
    if nf["cnpj"]:
        try:
            nf["fornecedor"] = consulta_nome_fornecedor(nf["cnpj"])["fornecedor"]
        except Exception:
            nf["fornecedor"] = None

    # --- contrato ----------------------------------------------------------------
    # Valor injetado por main.py ou carregado lazy via base_contratos.json.
    nf["contrato"] = _get_contrato()["contrato"]

    # --- fallback humano ---------------------------------------------------------
    # Só chega aqui se todos os passes (sem_remocao, kernel_20, kernel_40) falharam
    # para o campo. O operador digita o valor no terminal; se pressionar Enter em
    # branco, o campo fica None na planilha final.
    # Ordem dos campos: CNPJ primeiro porque, se preenchido, desbloqueia a busca
    # do fornecedor logo abaixo.
    campos_criticos = ["cnpj", "data_emissao", "valor", "numero_nf", "descricao"]
    for campo in campos_criticos:
        if nf.get(campo) is None:
            nf[campo] = _solicitar_campo_humano(campo, contexto=contexto)
            # Caso especial: CNPJ digitado pelo operador → tenta buscar o fornecedor
            # agora, já que a etapa automática acima foi pulada por falta de CNPJ.
            if campo == "cnpj" and nf["cnpj"] and not nf.get("fornecedor"):
                try:
                    nf["fornecedor"] = consulta_nome_fornecedor(nf["cnpj"])["fornecedor"]
                except Exception:
                    pass

    # preco_unitario e valor devem ser sempre iguais em NFS-e. Se a extração falhou
    # mas o fallback humano preencheu valor, espelha aqui sem pedir ao operador de novo.
    if not nf.get("preco_unitario") and nf.get("valor"):
        nf["preco_unitario"] = nf["valor"]

    return nf


def extrair_com_cascade(pdf_path, poppler_path=POPLLER_PATH, lang="por", salvar_texto_em=None):
    """
    Converte o PDF uma vez e roda 3 passes de pré-processamento OCR:
      Pass 1 — sem remoção de linhas (mais fiel ao texto original)
      Pass 2 — remoção leve  (kernel 20px)
      Pass 3 — remoção agressiva (kernel 40px — comportamento anterior)

    O score ordena a prioridade de busca por campo — não elimina passes.
    Para cada campo, percorre os passes do melhor ao pior score até encontrar
    um valor válido. O fallback humano só é acionado se todos os passes falharem.
    """
    images = convert_from_path(
        pdf_path,
        size=(3508, None),
        poppler_path=poppler_path,
        first_page=1,
        last_page=1,
        grayscale=True,
    )
    imagem_original = images[0]
    # Pré-conversão única: kernel_60 e kernel_40 ambos consumiriam uma cópia
    # numpy grayscale; converter no loop refazia o trabalho a cada pass.
    img_gray_np = np.array(imagem_original.convert("L"))

    passes_config = [
        ("sem_remocao", None),
        ("kernel_60",   60),
        ("kernel_40",   40),
    ]

    stem = Path(pdf_path).stem

    passes_validos = []
    for nome, kernel_size in passes_config:
        if kernel_size:
            img = _remover_linhas_tabela(img_gray_np, kernel_size=kernel_size)
        else:
            img = imagem_original
        texto = pytesseract.image_to_string(img, lang=lang, config="--oem 3 --psm 6")

        # Exporta o texto de cada pass para inspeção ==================================================
        #txt_path = Path(SAIDA_RAIZ) / f"{stem}_ocr_{nome}.txt"
        #txt_path.write_text(texto, encoding="utf-8")

        if not confirma_tipo_documento(texto):
            continue

        partes = fatiar_texto_nf(texto)
        score  = _pontuar_texto(partes)
        passes_validos.append({"nome": nome, "score": score, "texto": texto, "partes": partes})

    if not passes_validos:
        return {"is_nf": False}

    # Ordena por score decrescente; sort estável mantém pass 1 na frente em empates
    passes_validos.sort(key=lambda x: x["score"], reverse=True)

    contexto = os.path.basename(str(pdf_path))
    nf = _montar_nf_multiplos_passes(passes_validos, contexto=contexto)

    melhor = passes_validos[0]
    if salvar_texto_em:
        open(salvar_texto_em, "w", encoding="utf-8").write(melhor["texto"])

    return {
        "is_nf":         True,
        "pass_utilizado": melhor["nome"],
        "nf_extraida":   [nf],
        "partes_nf":     melhor["partes"],
        "texto":         melhor["texto"],
    }


def extrair_dados_nf_servico_do_pdf(pdf_path=CAMINHO_RAIZ, poppler_path=POPLLER_PATH, lang="por", salvar_texto_em=None):
    return extrair_com_cascade(
        pdf_path=pdf_path,
        poppler_path=poppler_path,
        lang=lang,
        salvar_texto_em=salvar_texto_em,
    )
