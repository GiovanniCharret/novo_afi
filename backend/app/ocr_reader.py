"""
Solução da IA usando pytesseract
"""

#C:\Users\GiovanniAzevedoCharr\AppData\Local\Programs\Tesseract-OCR
import re
import unicodedata
import pandas as pd
import pytesseract
from pdf2image import convert_from_path


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

# --- REGEX PRE-COMPILADAS (Melhoria de Performance) ---
RE_TWO_PRICES = re.compile(r'^\d+(?:[.,]\d+)*,\d{2}\d+(?:[.,]\d+)*,\d{2}$')
RE_DESC = re.compile(r"^(?=.*[a-zÃ -Ã¿])[a-z0-9Ã -Ã¿\s\-\.\(\)/,+]+$", flags=re.IGNORECASE)
RE_PRICE = re.compile(r'(?<![\d,])\b\d{1,3}(?:\.\d{3})*,\d{2}\b(?![0-9%])')
RE_NUM = re.compile(r'^[0-9.,]*[0-9]$')
RE_DATE = re.compile(r'\d{2}/\d{2}/\d{4}')
RE_CNPJ = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

# GLOBAIS --------------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\GiovanniAzevedoCharr\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
POPLLER_PATH = "poppler-25.12.0/Library/bin"
list_nf = []
cnpj_tomador = '03.467.321/0001-99'
CAMINHO_RAIZ = "./nfs_analise"
SAIDA_RAIZ = './output_dfs'
# Formato de dicionário por causa da função consolidate_data_to_dict que só recebe
# argumentos em dicionário
CONTRATO = {'contrato':'ECM/016-2025'}


def confirma_tipo_documento(texto):
    """
    Chamada só quando o pdfplumber falha, então preciso confirmar que 
    é um nf que meu script não resolve

    Ela confirma se o extraído pelo pytesseract, usando OCS
    é tem indícios suficientes de Nota Fiscal. Já que poderia ser outros 
    arquivos, tipo borderô de pagamento.

    """

    def normalizar(s):
        s = "" if s is None else str(s)
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s.upper()

    texto_normalizado = normalizar(texto)

    chaves_documento_nota_fiscal = [
        "NOTA FISCAL ELETRONICA",

        "NFS-E",
        "TOMADOR",
        "SERVICOS",
        "DESCRICAO",
        "DISCRIMINACAO",
        "PRODUTOS",
        "VALOR TOTAL",
        "DADOS ADICIONAIS",
        "OUTRAS INFORMACOES",
    ]

    qtd_chaves_encontradas = sum(
        1 for chave in chaves_documento_nota_fiscal if normalizar(chave) in texto_normalizado
    )

    is_nf = qtd_chaves_encontradas >= 4

    return is_nf

def normalizar_texto(s):
    s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def fatiar_texto_nf(texto):
    fronteira_inicio_lista = [
        "DISCRIMINACAO DOS SERVICOS",
        "DESCRIÇÃO DOS SERVIÇOS",
        "DESCRICAO DOS SERVICOS",
    ]

    fronteira_fim_lista = [
        "VALOR TOTAL",
    ]

    texto_normalizado = normalizar_texto(texto)

    idx_inicio = -1
    for item in fronteira_inicio_lista:
        pos = texto_normalizado.find(normalizar_texto(item))
        if pos != -1:
            idx_inicio = pos
            break

    idx_fim = -1
    for item in fronteira_fim_lista:
        pos = texto_normalizado.find(normalizar_texto(item))
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


def extrair_descricao(partes_nf):
    texto_meio = partes_nf.get("meio", "").strip()
    if not texto_meio:
        raise ValueError("OCR: não foi possível extrair descrição (trecho 'meio' vazio).")

    padrao = (
        r"(?:DISCRIMINACAO DOS SERVICOS|DISCRIMINAÇÃO DOS SERVIÇOS|"
        r"DESCRICAO DOS SERVICOS|DESCRIÇÃO DOS SERVIÇOS)"
        r"(.*?)"
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


def extrair_tipo_nota(texto_inicio):
    tipos_nota_lista = [
        "NFS-E",
        "NOTA FISCAL ELETRONICA DE SERVICOS",
        "NOTA FISCAL ELETRÔNICA DE SERVIÇOS",
    ]

    texto_inicio_normalizado = normalizar_texto(texto_inicio)
    for tipo in tipos_nota_lista:
        if normalizar_texto(tipo) in texto_inicio_normalizado:
            return 'serviço'
    return 'não identificado'


def extrair_numero_nf(texto_inicio):
    """
    Extrai número da NF pelo fallback:
    1) corta texto antes da data de emissão
    2) busca número próximo do primeiro texto encontrado em texto_fallback
    """
    texto_inicio_normalizado = normalizar_texto(texto_inicio)

    # 1 - Corta o texto na data. 
    match_data = RE_DATE.search(texto_inicio_normalizado)
    if match_data:
        # 2 - Fatia a parte anterior
        cabecalho = texto_inicio_normalizado[:match_data.start()]
    else:
        cabecalho = texto_inicio_normalizado

    texto_fallback = [
        'NUMERO DA NOTA',
        'NÚMERO DA NOTA',
        'SECRETARIA MUNICIPAL DA FAZENDA',
        'NOTA FISCAL ELETRONICA',
        'NFS-E',
    ]

    for mask_str in texto_fallback:
        idx = cabecalho.find(normalizar_texto(mask_str))
        if idx == -1:
            continue

        janela_inicio = max(0, idx - 120)
        janela_fim = min(len(cabecalho), idx + 180)
        janela = cabecalho[janela_inicio:janela_fim]

        candidatos = re.findall(r"\b\d{2,9}\b", janela)
        if candidatos:
            return candidatos[0]

    raise ValueError("OCR: não foi possível extrair número da NF.")


def extrair_data_emissao(texto_inicio):
    match = RE_DATE.search(texto_inicio)
    return match.group(0) if match else None


def extrair_cnpj(texto_inicio):
    """
    """

    def _formatar_cnpj(digitos):

        digitos = f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


        return digitos

    # 1) procura qualquer coisa que seja ou pareça CNPJ
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

    raise ValueError("OCR: não foi possível extrair CNPJ.")


def extrair_valor(texto_fim):
    texto_fim = (texto_fim or "").strip()
    if not texto_fim:
        raise ValueError("OCR: não foi possível extrair valor (trecho 'fim' vazio).")

    labels = ["VALOR LIQUIDO", "VALOR TOTAL", "VALOR DA NOTA"]
    texto_norm = normalizar_texto(texto_fim)

    for label in labels:
        idx = texto_norm.find(label)
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

    secao = texto_fim
    match_secao = re.search(r"(VALORES DA NOTA|VALOR TOTAL|VALOR DA NOTA)(.*)", texto_fim, flags=re.IGNORECASE | re.DOTALL)
    if match_secao:
        secao = match_secao.group(2)

    valores = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", secao)
    if valores:
        return valores[0]

    raise ValueError("OCR: não foi possível extrair valor.")


def montar_nf_template_servico(partes_nf):
    '''
    Preencher a linha de dados da NF em formato tabular (lista de dict)
    '''

    nf = default_nf_template.copy()
    #nf["codigo_produto"] = None
    nf["descricao"] = extrair_descricao(partes_nf)
    nf["ncm"] = None
    nf["quant"] = None
    nf["preco_unitario"] = None
    nf["numero_nf"] = extrair_numero_nf(partes_nf.get("inicio", ""))
    nf["tipo_nota"] = extrair_tipo_nota(partes_nf.get("inicio", ""))
    nf["data_emissao"] = extrair_data_emissao(partes_nf.get("inicio", ""))
    nf["cnpj"] = extrair_cnpj(partes_nf['inicio'])
    nf["fornecedor"] = None
    nf["valor"] = extrair_valor(partes_nf.get("fim", ""))
    nf["contrato"] = CONTRATO["contrato"]
    # pandas.DataFrame(dict_de_escalares) exige index; retornamos lista de linhas
    # para permitir pd.DataFrame(nf_extraida) no código chamador.
    return [nf] 


def extrair_texto_ocr_primeira_pagina(pdf_path, dpi=300, poppler_path=POPLLER_PATH, lang="por"):
    images = convert_from_path(
        pdf_path,
        dpi=dpi,
        poppler_path=poppler_path,
        first_page=1, 
        last_page=1,
        grayscale=True
    )
    return pytesseract.image_to_string(images[0], lang=lang, config="--oem 3 --psm 6")


def extrair_dados_nf_servico_do_texto(texto):
    partes_nf = fatiar_texto_nf(texto)
    nf_extraida = montar_nf_template_servico(partes_nf)
    return {
        "partes_nf": partes_nf,
        "nf_extraida": nf_extraida,
    }


def extrair_dados_nf_servico_do_pdf(pdf_path=CAMINHO_RAIZ, dpi=400, poppler_path=POPLLER_PATH, lang="eng", salvar_texto_em=None):
    texto = extrair_texto_ocr_primeira_pagina(
        pdf_path=pdf_path,
        dpi=dpi,
        poppler_path=poppler_path,
        lang=lang,
    )

    resultado = {} # Declaração obrigatória

    is_pdf = confirma_tipo_documento(texto)
    resultado["is_nf"] = is_pdf

    if salvar_texto_em:
        open(salvar_texto_em, "w", encoding="utf-8").write(texto)

    if is_pdf:

        resultado = extrair_dados_nf_servico_do_texto(texto)
        
        resultado["texto"] = texto

    return resultado


if __name__ == "__main__":

    resultado = extrair_dados_nf_servico_do_pdf(
        #pdf_path=PDF_PATH,
        dpi=600,
        poppler_path=POPLLER_PATH,
        lang="eng",
        salvar_texto_em="exemplo.txt",
    )

    print(resultado["partes_nf"])
    print(resultado["nf_extraida"])



