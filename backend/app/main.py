"""
v10

O que tem na 10?
1. Ajust do top_drift = 15.0 atual vira variável do loop for top_drift in [15.0, 7.5], para nfs que 
os detalhes de produto são muito pequenos.
2. normatize_produt_classes recebeu um update para normalizar texto

x. Seleção de contrato


"""
import pdfplumber
import pandas as pd
import re
from numpy import arange, sqrt
import requests
import numpy as np  # Necessário para o cálculo de distÃ¢ncia
from pathlib import Path
from tqdm import tqdm # Opcional: pip install tqdm (barra de progresso)
import unicodedata
import json
from ocr_reader import extrair_dados_nf_servico_do_pdf, product_or_service
from cnpj_lookup import consulta_nome_fornecedor
from description_cleaner import cleaner

# DEPURADOR
arquivo_investigado = '29105'

# LLM — modo de limpeza da coluna descricao: "precisao" | "recall"
MODO_LLM = "precisao"

# Propaga o modo para o path OCR (ocr_reader.py lê sua própria global MODO_LLM_OCR)
import ocr_reader as _ocr_mod
_ocr_mod.MODO_LLM_OCR = MODO_LLM

# DICIONÁRIO QUE RECEBERÁ OS DADOS DO PDF
default_nf_template = {
    # 'item': None, Será preenchido posteriormente por método reset_index
    # 'codigo_produto': None, # Removido na V7.3
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

# LOG DE EXECUTION AND VALIDATION
log_model = {
    'id': 0,
    'nome_arquivo': None,
    'status': None, #aberto - problema - rejeitado - processado
    'movivo': None, #caracteres não alfanuméricos - formato imagem - não é nota fiscal(OCR) - não é nota fiscal(confirma_tipo_documento)
    'next': None, #NA - chamando OCR - Assegurando dados de NF - convertento em xlsx

    'erro': None #NA - Valueerror

}

# Zerando o log
Path("log.json").write_text("", encoding="utf-8")


# --- REGEX PARA CARACTERES INVALIDOS
RE_INVALID_CHAR = re.compile(
    #r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ\s\.,;:/()\-_%:+º°*@\$#\|=]" ANTERIOR - DEIXEI GRAVADA
    r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ\s\.,;:/()\-_%:+º°*@\$#\|='\"“”‘’]" # ADIÇÃO PARA NÃO BLOQUEAR NF COM STR '“ILUSTRATIVO”,', '“AUTO-RETIDO”'
)

# GLOBAIS --------------------------
list_nf = []
CAMINHO_RAIZ = "./nfs_analise"
SAIDA_RAIZ = './output_dfs'
# Formato de dicionário por causa da função consolidate_data_to_dict que só recebe
# argumentos em dicionário. Selecionado a partir de base_contratos.json.
# Use None para escolher interativamente.
from contrato_config import selecionar_contrato
CONTRATO_NUMERO = None
CONTRATO = selecionar_contrato(CONTRATO_NUMERO)
_ocr_mod.CONTRATO = CONTRATO
caminho_entrada = Path(CAMINHO_RAIZ)
#rglob("*.pdf") busca recursivamente em todas as subpastas
arquivos_pdf = list(caminho_entrada.rglob("*.pdf"))

# DataFrame acumulador das linhas de todas as NFs processadas
tabela_anexo1_modelo = pd.DataFrame(columns=default_nf_template.keys())
# Cacete!
df_anexo1_consolidado = tabela_anexo1_modelo


def _solicitar_campo_humano(campo, contexto):
    print(f"\n[REVISÃO HUMANA] Arquivo: {contexto}")
    print(f"  Campo '{campo}' não pôde ser extraído automaticamente.")
    valor = input(f"  Digite o valor para '{campo}' (ou Enter para deixar em branco): ").strip()
    return valor or None


def extract_pdf_words(pdf_path, page_index=0):
    """
    Extrai todos os textos, que ficam listatos em text
    O valor que procura está na coluna text
    Use o depurador abaixo para ver a coluna e o df

    `page_index` (0-based) seleciona a página. Default 0 preserva o comportamento
    histórico (single-page). Para DANFE multi-folha, o caller passa page_index=1
    (ou superior) para ler a página onde os produtos estão impressos.
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_index]
        words = page.extract_words(keep_blank_chars=False, x_tolerance=2, y_tolerance=2)
        df_words = pd.DataFrame(words)

        return df_words


def eh_danfe_multifolha(pdf_path):
    """
    Detecta per-NF se o DANFE é multi-folha (produtos podem estar em pág. 2+).

    Sinal estrutural: o DANFE-NF-e (modelo 55) imprime `Folha N/M` no header de
    identificação do documento. Se M > 1, é multi-folha por declaração do próprio
    documento. Combina com `len(pdf.pages) > 1` (fato do PDF) para evitar falso
    positivo em PDF de página única que mencione "Folha" em outro contexto.

    Retorna True se ambos sinais coincidem, False caso contrário.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) <= 1:
            return False
        texto_pag1 = pdf.pages[0].extract_text() or ""
    match = re.search(r'Folha\s+(\d+)\s*/\s*(\d+)', texto_pag1, re.IGNORECASE)
    if match:
        return int(match.group(2)) > 1
    return False


def confirma_tipo_documento(texto):
    """
    Chamada só quando o pdfplumber falha, então preciso confirmar que 
    é um nf que meu script não resolve

    Ela confirma se o extraído pelo pytesseract, usando OCS
    é tem indícios suficientes de Nota Fiscal. Já que poderia ser outros 
    arquivos, tipo borderô de pagamento.

    """

    if isinstance(texto, pd.DataFrame):
        if "text" not in texto.columns:
            return False
        texto = " ".join(texto["text"].fillna("").astype(str).tolist())

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


def list_regex_filter(text):
    """
    Identifica a natureza de uma string extraída de uma NF.

    Testar na ordem certa é vital para o sucesso do filtro

    1. Merged Price - Quando dois valores aparecem fundidos e precisam ser separados 
    2. CNPJ
    2. data da emissÃ£o
    3. valor
    4. num (quantidade, porcentagem ou nÃºmero de nota)
    6. descrição do material/serviÃ§o
    7. O restante vai como undefined

    
    :return natureza da string. Ex. Essa Ã© uma string de descriÃ§Ã£o de material.
    Essa Ã© uma string de data
    """
    #Lista de Regex
    two_merged_price_pattern = re.compile(r'^\d+(?:[.,]\d+)*,\d{2}\d+(?:[.,]\d+)*,\d{2}$')
    material_description = re.compile(r"^(?=.*[a-zà-ÿ])[a-z0-9à-ÿº\s\-\.\(\)/,+]+$", flags=re.IGNORECASE)
    price = re.compile(r'(?<![\d,])\b\d{1,3}(?:\.\d{3})*,\d{2}\b(?![0-9%])')
    number = re.compile(r'^(?:R\$\s*)?(?=.*[1-9])[0-9.,]*[0-9]$') #r'^\d+(?:[.,]\d+)*$') #'^[1-9.,]*[1-9]$') #'^\d+(?:[.,]\d+)*$' #r'^\d+(?:\.\d+)*$')
    create_date = re.compile(r'\d{2}/\d{2}/\d{4}')
    cnpj = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
    

    # E relação entre index e objeto re
    class_list = [
        
        ('two_merged_price', two_merged_price_pattern),
        ("CNPJ", cnpj),
        ("data", create_date),
        #("price", price), #Price e num são parecidos. Por isso, essa regex precisa vir na frente
        ("num_or_price", number), # com join_lonely_charecte, linea 265
        ("descpt", material_description)

    ]           
 
    for label, pattern in class_list:

        if pattern.search(text):
            return label

    return "unindentfied"


def fix_merged_prices(df):
    """
    Identifica 'two_merged_price', separa os textos e divide as coordenadas
    geomÃ©tricas (x0, x1 e center_x) para que funÃ§Ãµes espaciais 
    identifiquem que sÃ£o colunas diferentes.
    """
    # 1. Identificamos os í­ndices problemáticos
    target_indices = df[df['string_class'] == 'two_merged_price'].index.tolist()

    # 2. Iteramos de trás PARA FRENTE para manter a integridade do fatiamento
    for idx in reversed(target_indices):
        row_original = df.loc[idx]
        text_val = str(row_original['text']).strip()
        parts = text_val.split(',')
        
        if len(parts) >= 3:
            # 3. Separação dos textos (Ex: 126.381,15 e 176.030,89)
            text1 = f"{parts[0]},{parts[1][:2]}"
            text2 = f"{parts[1][2:].strip()},{parts[2]}"
            
            # --- FIX GEOMÃ‰TRICO ---
            # Calculamos o ponto mÃ©dio exato da largura original
            mid_x = (row_original['x0'] + row_original['x1']) / 2

            # 4. Criamos as duas linhas com coordenadas distintas
            # Linha A (Lado Esquerdo da cÃ©lula)
            row_a = row_original.copy()
            row_a['text'] = text1
            row_a['string_class'] = 'num_or_price'
            row_a['x1'] = mid_x  # Termina no meio
            row_a['center_x'] = (row_a['x0'] + mid_x) / 2 # Recalcula o centro
            
            # Linha B (Lado Direito da cédula)
            row_b = row_original.copy()
            row_b['text'] = text2
            row_b['string_class'] = 'num_or_price'
            row_b['x0'] = mid_x  # Começa do meio
            row_b['center_x'] = (mid_x + row_b['x1']) / 2 # Recalcula o centro
            
            # 5. ReconstruÃ§Ã£o do DataFrame
            df_topo = df.loc[:idx].iloc[:-1] 
            df_base = df.loc[idx:].iloc[1:]
            
            df_new_rows = pd.DataFrame([row_a, row_b])
            df_new_rows.index = [idx, idx + 0.1] 

            df = pd.concat([df_topo, df_new_rows, df_base])

    return df


def join_lonely_character(df):
    """
    GLOBAIS QUE QUEBRA SE MEXER num_or_price, unindentfied, string_class, text
    
    Concatena caracteres solitários à linha anterior apenas se:
    1. Os dois números não foram mum_or_price (caracteres numéricos são preservados).
    2. A classificação for 'unindentfied'.
    """

    indices_to_drop = []
    
    # Iteramos a partir da segunda linha (Í­ndice 1)
    for i in range(1, len(df)):
        current_text = str(df.iloc[i]['text']).strip()
        current_class = df.iloc[i]['string_class']
        least_class = df.iloc[i-1]['string_class']
        
        # CRITÉRIOS DE FUSÃO:
        # Comprimento menor ou igual a 2 E não é número e classificação só unindentfied
        if len(current_text) <= 2 and not current_text.isdigit() and current_class == "unindentfied" and least_class !='num_or_price':
            idx_prev = df.index[i-1]
            idx_curr = df.index[i]
            
            # Concatena o texto na linha anterior
            df.at[idx_prev, 'text'] = str(df.at[idx_prev, 'text']) + current_text
            
            # Marca a linha atual para ser removida
            indices_to_drop.append(idx_curr)
            
    # Remove as linhas fundidas
    df = df.drop(indices_to_drop).reset_index(drop=True)
    
    return df


def concatenate_string_class(df):
    """
    A df manda os dados quebrados. A coluna "string class" adicionou 
    informações da string via regex

    Agora é preciso juntar essas informações usando dados exportados da pdfplumber
    e da função list_regex_filter.

    O objerivo é juntar linhas assim --

    COMISSIONAMENTO
    DE
    SISTEMA
    INDIVIDUAL
    DE
    GERAÇÃO
    DE
    ENERGIA

    Em -- 

    COMISSIONAMENTO DE SISTEMA INDIVIDUAL DE GERAÇÃO DE ENERGIA ELÉTRICA
    
    """
 
    # 1. Definimos as classes que podem ser "coladas" umas nas outras
    is_valid_class = df['string_class'].isin(['descpt', 'unindentfied'])
    
    # Criamos uma máscara para a linha anterior (shift)
    # fill_value=False garante que a primeira linha da NF nunca tente mesclar com o nada
    valid_base = is_valid_class.shift(fill_value=False)

    # VerificaÃ§Ã£o de proximidade espacial
    same_line = (df['top'] - df['top'].shift()).abs() < 4.0
    not_too_far = (df['x0'] - df['x1'].shift()).between(0.01, 6.0, inclusive='neither')
    texto_atual = df['text'].fillna("").astype(str).str.strip().str.lower()
    """
    Haverá linhas assim que não podem juntas. É tipo uma condição semântica

    Valor
    Valor
    total

    """
    texto_anterior = texto_atual.shift(fill_value="")
    similar_text = texto_atual.combine(
        texto_anterior,
        lambda atual, anterior: bool(atual and anterior and (atual in anterior or anterior in atual))
    )
    
    # 2. Lógica do Grupo corrigida:
    # São mesclamos se a linha atual FOR válida E a linha anterior TAMBÉM FOR válida
    should_merge = is_valid_class & valid_base & same_line & not_too_far & ~similar_text
    
    # O grupo só muda (incrementa) quando Não deve mesclar
    new_group_start = ~should_merge
    df['group_id'] = new_group_start.cumsum()
    
    # 3. Agrupamento
    # Opção B (bug_fix/BUG_NCM_MISSING.md) — quando um token 'unindentfied' curto
    # (ex.: '-') aparece imediatamente antes de um 'descpt' (ex.: 'POSTE DE CONCRETO...'),
    # a fusão espacial juntava os textos mas o agg='first' preservava 'unindentfied'.
    # Resultado: o nome do produto não era reconhecido como descrição em
    # concatenar_por_ponteiro_filtra_tabela_produtos. Agora, se qualquer elemento
    # do grupo for 'descpt', a classe final do grupo é 'descpt'.
    def _resolve_class(serie):
        valores = serie.tolist()
        if 'descpt' in valores:
            return 'descpt'
        return valores[0]

    df_grouped = df.groupby('group_id').agg({
        'text': lambda x: ' '.join(map(str, x)),
        'string_class': _resolve_class,
        'x0': 'min',
        'x1': 'max',
        'top': 'first',
        'doctop': 'first',
        'bottom': 'max'
    }).reset_index(drop=True)
    
    return df_grouped
    

def refine_table_classification(df):
    """
    Reclassifica todas classes 'num_or_price' com a string 'descpt' mais próxima
    geometricamente (eixo X e Y), sem depender de nomes pré-definidos.
    """
    # 1. Calcular center_x e adicionar a nova coluna ao DF
    df['center_x'] = (df['x0'] + df['x1']) / 2
    
    # Anchors me ajuda no debug
    df['Anchors'] = "N/A"

    # 3. Laço exclusivo para linhas com 'num_or_price'
    # Buscamos os índices para garantir que não alteramos a ordem física do DF
    targets_idx = df[df['string_class'] == 'num_or_price'].index

    for idx in targets_idx:
        row = df.loc[idx]
        current_top = row['top']
        current_center = row['center_x']

        # 2. Filtrar o DF por "descpt" e por "top" <= atual
        # Isso garante que o número busque apenas cabeçalhos que estão acima dele
        potential_headers = df[(df['string_class'] == 'descpt') & (df['top'] <= current_top)].copy()

        if not potential_headers.empty:
            # 3. Cálculo da Proximidade Geométrica (Distância Euclidiana)
            # Buscamos o menor valor de: raiz( (delta_top)^2 + (delta_center_x)^2 )
            
            # Distância vertical (sempre <= 0 pois filtramos top <= current_top)
            potential_headers['d_top'] = potential_headers['top'] - current_top
            
            # Distância horizontal
            potential_headers['d_x'] = potential_headers['center_x'] - current_center
            
            # Distância Geométrica Total
            potential_headers['dist_total'] = (potential_headers['d_top']**2 + potential_headers['d_x']**2)**0.5

            # Encontramos o índice do texto mais próximo
            best_match_idx = potential_headers['dist_total'].idxmin()
            header_text = potential_headers.loc[best_match_idx, 'text']

            # 4. Retornar esse "text" na "string_class" do ponteiro no laço
            df.at[idx, 'string_class'] = header_text
            
            # Adicionamos o log na coluna Anchors para o seu debug
            df.at[idx, 'Anchors'] = f"Alinhado a: {header_text} (Dist: {potential_headers.loc[best_match_idx, 'dist_total']:.2f}px)"

    return df


def refine_product_table_classification(df):
    """
    Classifica tokens 'num_or_price' dentro da tabela de produtos de uma NF-e.

    POR QUE ESTA FUNÇÃO EXISTE (e não usamos refine_table_classification aqui):
    ───────────────────────────────────────────────────────────────────────────
    refine_table_classification() encontra, para cada token 'num_or_price', o
    token 'descpt' mais próximo geometricamente (distância euclidiana em X e Y),
    considerando TODOS os tokens descpt que estão ACIMA do número avaliado.

    Isso funciona muito bem para o primeiro terço da nota (metadados, cabeçalhos,
    totais), onde todo token descpt é contexto legítimo de rótulo.

    Na tabela de produtos, porém, as linhas de DADOS também contêm tokens descpt.
    Exemplo real: o campo "unidade de medida" de cada produto aparece como "UN"
    classificado como descpt. Esse "UN" fica NA MESMA LINHA HORIZONTAL do número
    de quantidade — distância vertical zero. Já o cabeçalho correto "QUANT" fica
    ~45px acima. Pelo cálculo euclidiano, o "UN" da mesma linha vence e o número
    recebe a string_class errada.

    SOLUÇÃO DESTA FUNÇÃO:
    ─────────────────────
    Usar apenas os tokens da LINHA DE CABEÇALHO como âncoras, e calcular somente
    a distância HORIZONTAL (|delta center_x|). Como todos os candidatos estão na
    mesma linha, a distância vertical seria idêntica para todos — usar só a
    horizontal é equivalente à euclidiana e mais legível.

    COMO IDENTIFICAMOS A LINHA DE CABEÇALHO:
    ─────────────────────────────────────────
    fracionando_nf_produto() garante que o slice começa exatamente no cabeçalho
    da tabela. Portanto, os tokens com os menores valores de 'top' no slice são
    os cabeçalhos de coluna. Usamos uma tolerância de HEADER_TOL pixels para
    incluir cabeçalhos que ocupam duas linhas físicas (ex.: "VALOR" em top=432
    e "UNITÁRIO" em top=435 — ambos pertencem ao mesmo cabeçalho de coluna).
    """
    df = df.copy()

    # A média da âncora
    df['center_x'] = (df['x0'] + df['x1']) / 2
    df['Anchors'] = "N/A"

    # ── 1. Identificar a linha de cabeçalho ─────────────────────────────────────
    # O menor 'top' do slice é a primeira linha — os cabeçalhos de coluna.
    # HEADER_TOL cobre cabeçalhos em duas alturas físicas distintas (ex.: 432 e 435).
    HEADER_TOL = 5.0  # px
    top_values = pd.to_numeric(df['top'], errors='coerce')
    min_top = top_values.min()
    mask_cabecalho = (top_values <= min_top + HEADER_TOL) & (df['string_class'] == 'descpt')
    cabecalhos = df[mask_cabecalho].copy()

    if cabecalhos.empty:
        # Sem cabeçalho reconhecível — devolve df sem alterar (não quebra o pipeline)
        return df

    # ── 2. Classificar cada num_or_price pela coluna horizontalmente mais próxima ─
    # Todos os cabeçalhos estão na mesma linha, então delta_top é igual para todos.
    # Comparar só |delta center_x| é suficiente e evita ruído vertical.
    targets_idx = df[df['string_class'] == 'num_or_price'].index

    for idx in targets_idx:
        current_center = df.at[idx, 'center_x']

        # Distância horizontal absoluta de cada cabeçalho ao token atual
        dist_x = (cabecalhos['center_x'] - current_center).abs()

        best_idx = dist_x.idxmin()
        header_text = cabecalhos.at[best_idx, 'text']
        melhor_dist = dist_x.min()

        df.at[idx, 'string_class'] = header_text
        # Coluna Anchors mantém o mesmo formato de refine_table_classification para debug
        df.at[idx, 'Anchors'] = f"Alinhado a: {header_text} (Dist X: {melhor_dist:.2f}px)"

    return df


def fracionando_nf_produto(df):
    """
    Fraciona NFs de produto em primeiro terço, tabela de produtos e último terço.

    Caso especial DANFE multi-folha: quando o cabeçalho da tabela é encontrado mas
    não há evidência de produto entre ele e DADOS ADICIONAIS (pág. 1 de DANFE
    multi-folha, onde os produtos ficam em pág. 2+), retorna `tabela_produtos`
    vazia em vez de raise. O caller decide se aciona retry em página alternativa.
    """
    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.upper()

    chave_corta_primeiro_terco = [
        'DADOS',
        'SERVIÇOS',
        'PRODUTO',
        'DESCRIÇÃO',
        'DISCRIMINAÇÃO',
        'PRODUTOS',
        'PRODUTO',
        'PRESTADOS'
    ]
    chave_corta_ultimo_terco = ['DADOS ADICIONAIS', 'INFORMAÇÕES ADICIONAIS', 'OUTRAS INFORMAÇÕES']

    idx_inicio_adicionais = None
    for chave in chave_corta_ultimo_terco:
        mask = df['text'].str.contains(chave, case=False, na=False)
        indices = df[mask].index
        if not indices.empty:
            idx_inicio_adicionais = indices[0]
            break

    def _candidato_muito_alto(idx):
        top_limite = pd.to_numeric(df['top'], errors='coerce').quantile(0.20)
        top_atual = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
        return pd.notna(top_limite) and pd.notna(top_atual) and top_atual < top_limite

    def _tem_cabecalho_estrutural(idx):
        if 'top' not in df.columns:
            texto_faixa = " ".join(df.loc[[idx], 'text'].fillna("").astype(str).tolist())
        else:
            top_ref = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
            faixa = df[(pd.to_numeric(df['top'], errors='coerce') - top_ref).abs() <= 8].copy()
            texto_faixa = " ".join(faixa['text'].fillna("").astype(str).tolist())

        texto_faixa = _normalizar_texto(texto_faixa)
        tem_item = any(chave in texto_faixa for chave in ['PRODUTO', 'PRODUTOS', 'SERVICO', 'SERVICOS'])
        tem_descricao = any(chave in texto_faixa for chave in ['DESCRICAO', 'DISCRIMINACAO'])
        tem_coluna_tabela = any(chave in texto_faixa for chave in ['NCM', 'CFOP', 'QUANT', 'QTD', 'UNIT', 'VALOR', 'TOTAL'])
        return tem_item and tem_descricao and tem_coluna_tabela

    def _tem_evidencia_produto_abaixo(idx):
        # Janela: do candidato até DADOS ADICIONAIS (se conhecido) ou até o fim do df.
        # Antes era hard-coded em top+45 — pequeno demais para descrições multi-linha
        # com linhas auxiliares (ex.: GENERAL 1364: Pedido/Prod.Cliente/Resolucao/FCI).
        if 'top' not in df.columns:
            if idx_inicio_adicionais is not None:
                trecho = df.loc[idx:idx_inicio_adicionais].copy()
            else:
                trecho = df.loc[idx:].copy()
        else:
            top_ref = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
            top_num = pd.to_numeric(df['top'], errors='coerce')
            mask = top_num >= top_ref
            if idx_inicio_adicionais is not None:
                top_ceiling = pd.to_numeric(df.loc[idx_inicio_adicionais, 'top'], errors='coerce')
                if pd.notna(top_ceiling):
                    mask = mask & (top_num < top_ceiling)
            trecho = df[mask].copy()

        textos = trecho['text'].fillna("").astype(str).str.strip()
        tem_ncm = textos.str.replace(r'\D', '', regex=True).str.len().eq(8).any()
        tem_valor = textos.str.contains(r'\d{1,3}(?:\.\d{3})*,\d{2}', regex=True, na=False).any()
        tem_descricao = trecho['string_class'].astype(str).isin(['descpt', 'unindentfied']).any()
        return tem_ncm and tem_valor and tem_descricao

    def _eh_inicio_tabela_valido(idx):
        if _candidato_muito_alto(idx):
            return False
        if not _tem_cabecalho_estrutural(idx):
            return False
        return _tem_evidencia_produto_abaixo(idx)

    dic_frac_nf = {
        "primeiro_terco": pd.DataFrame(columns=df.columns),
        "tabela_produtos": pd.DataFrame(columns=df.columns),
        "ultimo_terco": pd.DataFrame(columns=df.columns)
    }

    idx_inicio_tabela = None
    idx_header_only = None  # primeiro candidato com header válido, mesmo sem evidência de produto
    encontrou_inicio_valido = False

    for chave1 in chave_corta_primeiro_terco:
        for chave2 in chave_corta_primeiro_terco:
            if chave1 != chave2:
                mask = (
                    df['text'].str.contains(chave1, case=False, na=False) &
                    df['text'].str.contains(chave2, case=False, na=False)
                )
                indices = df[mask].index
                if not indices.empty:
                    for idx_candidato in indices:
                        if _candidato_muito_alto(idx_candidato):
                            continue
                        if not _tem_cabecalho_estrutural(idx_candidato):
                            continue
                        if idx_header_only is None:
                            idx_header_only = idx_candidato
                        if _tem_evidencia_produto_abaixo(idx_candidato):
                            idx_inicio_tabela = idx_candidato
                            encontrou_inicio_valido = True
                            break
            if encontrou_inicio_valido:
                break
        if encontrou_inicio_valido:
            break

    if idx_inicio_tabela is not None and idx_inicio_adicionais is None and 'top' in df.columns:
        trecho = df.loc[idx_inicio_tabela:].copy()
        top_num = pd.to_numeric(trecho['top'], errors='coerce')
        gaps = top_num.diff().abs()
        media_local = gaps.rolling(window=6, min_periods=3).mean().shift(1)

        for n in range(3, 10):
            salto_anormal = (gaps > (media_local * n)) & (gaps > 12)
            candidatos = list(trecho.index[salto_anormal.fillna(False)])
            # Rejeita candidato que ainda tenha NCM (token de 8 dígitos puros)
            # depois — significa que o "salto" é entre dois produtos, não entre
            # tabela e DADOS ADICIONAIS. Caso ITB N F 51627: 4 produtos com
            # idênticos NCMs e gap inter-produto grande (descrições com várias
            # linhas auxiliares de números de série) confundiam o heurístico.
            for cand in candidatos:
                textos_depois = df.loc[cand:, 'text'].fillna("").astype(str)
                tem_ncm_depois = textos_depois.str.fullmatch(r'\d{8}').any()
                if not tem_ncm_depois:
                    idx_inicio_adicionais = cand
                    break
            if idx_inicio_adicionais is not None:
                break

    # Caso especial: header da tabela existe, DADOS ADICIONAIS existe, mas a tabela
    # entre eles está vazia. Estruturalmente é DANFE multi-folha pág. 1 (produtos
    # ficam em pág. 2+). Retorna tabela vazia para o caller decidir o retry.
    if idx_inicio_tabela is None and idx_header_only is not None and idx_inicio_adicionais is not None:
        dic_frac_nf['primeiro_terco'] = df.loc[:idx_header_only].iloc[:-1].copy()
        dic_frac_nf['tabela_produtos'] = pd.DataFrame(columns=df.columns)
        dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()
        return dic_frac_nf

    if idx_inicio_tabela is None:
        raise ValueError('Não conseguiu dividir a tabela em 3 partes. O que aconteceu?')

    dic_frac_nf['primeiro_terco'] = df.loc[:idx_inicio_tabela].iloc[:-1].copy()

    if idx_inicio_adicionais is None:
        dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:].copy()
        return dic_frac_nf

    dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:idx_inicio_adicionais].iloc[:-1].copy()
    dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()
    return dic_frac_nf



def fracionando_nf_servico(df):
    """
    Fraciona NFs de serviço em primeiro terço, tabela descritiva e último terço.
    """
    dic_frac_nf = {
        "primeiro_terco": pd.DataFrame(columns=df.columns),
        "tabela_produtos": pd.DataFrame(columns=df.columns),
        "ultimo_terco": pd.DataFrame(columns=df.columns)
    }

    chave_fallbak_parte_superior = [
        'Descrição',
        'Discriminação',
        'Detalhada',
        'Serviços',
        'Prestados'
    ]

    # Essa chave estava dando erro para notas fiscais de serviço que colocam chave "valor total" antes da descrição
    # o outro bloco de chaves parece mais razoável.
    # chave_fallbak_parte_inferior = [
    #     'VALOR TOTAL',
    #     'VALOR LÍQUIDO',
    #     'VALOR LIQUIDO',
    #     'PREÇO DOS SERVIÇOS',
    #     'PRECO DOS SERVICOS',
    #     'VL. LÍQUIDO',
    #     'VL. LIQUIDO',
    # ]

    chave_fallbak_parte_inferior = [
        'Deduções',
        'Base Cálculo',
        'Outras retenções'
     ]


    idx_inicio_tabela = None
    idx_inicio_adicionais = None

    for chave in chave_fallbak_parte_inferior:
        mask_inferior = (
            df['string_class'].astype(str).str.contains(chave, case=False, na=False) |
            df['text'].astype(str).str.contains(chave, case=False, na=False)
        )
        indices_inferior = df[mask_inferior].index
        if not indices_inferior.empty:
            idx_inicio_adicionais = indices_inferior[0]
            break

    df_superior = df.loc[:idx_inicio_adicionais - 1] if idx_inicio_adicionais is not None else df.copy()

    for chave in chave_fallbak_parte_superior:
        mask_superior = df_superior['text'].str.contains(chave, case=False, na=False)
        indices_superior = df_superior[mask_superior].index
        if not indices_superior.empty:
            idx_inicio_tabela = indices_superior[0]
            break

    if idx_inicio_tabela is None:
        raise ValueError('Não conseguiu dividir a tabela de serviço em 3 partes. O que aconteceu?')

    dic_frac_nf['primeiro_terco'] = df.loc[:idx_inicio_tabela].iloc[:-1].copy()

    # Se não conseguiu dividir a segunda e terceira partes
    if idx_inicio_adicionais is None:
        dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:].copy()
        return dic_frac_nf
    
 
    """
    Para evitar esse tipo de textão abaixo, um aparador que corta tudo que é imposto da string
    Antes
    SERVIÇO DE INSTALAÇÃO DE SISTEMA FOTOVOLTAICO INFORMAÇÕES ADICIONAIS REF. INSTALAÇÃO SIGFIS REALIZADO NO MUNICIPIO DE TOCANTINOPOLIS -TO CONTRATO: 2023.0156.01 LOTE DE CONSOLIDAÇÃO: 261992 COD. FATURAMENTO: 230156011907877490010000261992 Atividade: 4221902-Construção de estações e redes de distribuição de energia elétrica 7.02 Execução, por administração, empreitada ou subempreitada, de obras de construção civil, hidráulica ou elétrica e de outras obras semelhantes, inclusive sondagem, perfuração de poços, escavação, drenagem e irrigação, terraplanagem, pavimentação, concr Retenções PIS COFINS INSS IR CSLL FederaisR$ 2.594,21 R$ 11.973,25 R$ 13.968,80 R$ 5.986,63 R$ 3.991,08 Demonstrativo Cálculo do Imposto Valor dos ServiçosR$ 399.108,48 Valor dos ServiçosR$ 399.108,48 (-) Desconto IncondicionadoR$ 0,00 (-) Desconto IncondicionadoR$ 0,00 (-) Retenções FederaisR$ 38.513,97 (=) Valor da NotaR$ 399.108,48 (-) ISSQN Retido pelo TomadorR$ 19.955,42 (-) DeduçõesR$ 0,00
    Depois
    
    """

    dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:idx_inicio_adicionais].iloc[:-1].copy()
    dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()

    return dic_frac_nf


def normatize_produt_classes(df):
    """
     Cada NF escreve os títulos dos dados da tabela de produtos de formas diferentes
     normatizar, evita quebrar e torna menos verborragica funções abaixo

     return df com 'string_class' normatizada
    """

    def _normalizar_texto(texto):
        if texto is None or (not isinstance(texto, str) and pd.isna(texto)):
            return ""
        if not isinstance(texto, str):
            raise ValueError(f"_normalizar_texto recebeu tipo inválido: {type(texto).__name__}")
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.lower().strip()

    # Só uma constante que pode virar um laço no futuro
    default_text = ["Descrição do produto", "NCM/SH", "QUANT", "UNIT", "price"]

    # 1. Consolida descpt para criar a descrição do produto
    misunderstood_NCM_text = ['ncm', 'NCM/ SH', 'NCM', 'SH']
    misunderstood_quant_text = ['QTD.', 'QUANT.', 'Qtde.'] # UN de unidades. Não de valor unitário.
    misunderstood_unitario_text = ['VALOR UNITÁRIO', 'unitário', 'UNITÁRIO', 'VALOR UNIT', 'UNITARIO', 'VLR. UNIT.']
    misunderstood_price_text = ['TOTAL', 'VLR. TOTAL', 'Valor total']

    classe_normalizada = df['string_class'].apply(_normalizar_texto)

    ncm_norm = {_normalizar_texto(r) for r in misunderstood_NCM_text}
    quant_norm = {_normalizar_texto(r) for r in misunderstood_quant_text}
    unit_norm = {_normalizar_texto(r) for r in misunderstood_unitario_text}
    price_norm = {_normalizar_texto(r) for r in misunderstood_price_text}

    df.loc[classe_normalizada.isin(ncm_norm), 'string_class'] = 'NCM/SH'
    df.loc[classe_normalizada.isin(quant_norm), 'string_class'] = 'QUANT'
    df.loc[classe_normalizada.isin(unit_norm), 'string_class'] = 'UNIT'
    df.loc[classe_normalizada.isin(price_norm), 'string_class'] = 'price'


    return df


def semantic_filter(df):
    """
    Aplica filtros semânticos em classes já normatizadas.
    Regra atual:
    - NCM/SH deve conter exatamente 8 dígitos.
    - Se não contiver, rebaixa para 'unindentfied'.
    """
    mask_ncm = df['string_class'] == 'NCM/SH'

    ncm_digitos = (
        df.loc[mask_ncm, 'text']
        .astype(str)
        .str.replace(r'\D', '', regex=True)
    )
    mask_invalido = ncm_digitos.str.len() != 8
    idx_invalidos = ncm_digitos[mask_invalido].index
    df.loc[idx_invalidos, 'string_class'] = 'unindentfied'

     # LOG
    log = {
        'id': seq + 1,
        'nome_arquivo': nome_saida,
        'status': 'problema', #aberto - problema - rejeitado - processado
        'movivo': 'semantic filter NCM aplicado', 
        'next': 'NA', #NA - chamando OCR
        'erro': None #NA - Valueerror
    }
    with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")


    
    return df


# Âncoras de linha alternativas quando NCM/SH está ausente (ex.: pdfplumber colou NCM à descrição).
# Adicionar novas variantes aqui conforme novos formatos de NF forem encontrados.
FALLBACK_ANCORAS_LINHA = [
    'CÓDIGO PRODUTO',
    'CFOP',
]


def concatenar_por_ponteiro_filtra_tabela_produtos(df, contexto):
    """
    Concatena linhas de texto baseando-se no intervalo entre NCM.
    1 - Tem que ter NCM na tabela. 
    
    Conta todos os NCM, serão os produtos
    Células que sofreram concatenação são reclassificadas como 'Descrição do produto'.
    """
    # TOLERÂNCIA DE PIXELS
    x_tol=30.0
    
    # Lista a quantidade de produtos na tabela, via contagem de NCM.
    # Quando o NCM vem colado à descrição pelo pdfplumber, nenhuma linha é classificada
    # como NCM/SH aqui. A função continua normalmente — o campo ficará None no bloco do
    # produto — e a supervisão humana em get_real_transations cobrirá o campo ausente.
    indices_ncm = df[df['string_class'] == 'NCM/SH'].index.tolist()


    def encontrar_ponteiro_coluna_descricao(df):
        # Chaves de corte baseadas na estrutura padrao de Notas Fiscais
        chave_ponteiro_coluna = [
            'DESCRIÇÃO DO PRODUTO',
            'DESCRICAO DO PRODUTO',
            'DISCRIMINAÇÃO DO PRODUTO',
            'DISCRIMINACAO DO PRODUTO',
            'DETALHE DO PRODUTO'
        ]
        serie_texto = df['text'].astype(str).str.upper()

        for mask_str in chave_ponteiro_coluna:
            mask_header = serie_texto.str.contains(mask_str.upper(), na=False)
            if mask_header.any():
                return float(df.loc[mask_header, 'center_x'].iloc[0])

        raise ValueError('Fiquei sem Âncora horizontal de ponteiro. Atualize as chaves')

    def encontrar_ponteiros_linha_ncm(df):
        # Caso normal: usa NCM/SH como âncora vertical de produto
        indices = df[df['string_class'] == 'NCM/SH'].index.tolist()
        if indices:
            return indices
        # Fallback: tenta cada âncora alternativa na ordem da lista FALLBACK_ANCORAS_LINHA
        for ancora in FALLBACK_ANCORAS_LINHA:
            indices = df[df['string_class'].str.upper() == ancora.upper()].index.tolist()
            if indices:
                return indices
        return []
    
    
    df_original = df.copy()
    center_x_descricao = encontrar_ponteiro_coluna_descricao(df)
    indices_ncm = encontrar_ponteiros_linha_ncm(df)
    first_ncm_top = float(df.at[indices_ncm[0], 'top']) if indices_ncm else None

    for top_drift in [15.0, 7.5]:
        df = df_original.copy()

        for i, idx_ncm in enumerate(indices_ncm):
            ncm_top = float(df.at[idx_ncm, 'top'])

            if i < len(indices_ncm) - 1:
                next_ncm_top = float(df.at[indices_ncm[i + 1], 'top'])
                mask_bloco = (df['top'] >= (ncm_top - top_drift)) & (df['top'] < next_ncm_top)
            else:
                mask_bloco = df['top'] >= (ncm_top - top_drift)

            df_bloco = df[mask_bloco].copy()

            if center_x_descricao is None:
                mask_descpt = df_bloco['string_class'] == 'descpt'
            else:
                mask_descpt = (
                    (df_bloco['string_class'] == 'descpt') &
                    ((df_bloco['top'] - ncm_top) <= top_drift) &
                    ((df_bloco['center_x'] - center_x_descricao) <= x_tol)
                )

            indices_descpt = df_bloco[mask_descpt].index.tolist()

            # Opção D (bug_fix/BUG_NCM_MISSING.md) — layouts em que a descrição
            # principal compartilha o mesmo 'top' da linha de NCM/QUANT/UNIT/price
            # (ex.: NF 23404 INDUSTRIA). Tokens à esquerda do NCM nessa linha não
            # são capturados acima quando sua string_class é 'unindentfied' ou o
            # nome literal do header da coluna ('DESCRIÇÃO DO PRODUTO/ SERVIÇO').
            # Inclui-os explicitamente, exigindo same-line + à esquerda do NCM.
            classes_reservadas = {'NCM/SH', 'QUANT', 'UNIT', 'price', 'Descrição do produto'}
            ncm_x0 = float(df.at[idx_ncm, 'x0'])
            mask_same_line = (
                (df_bloco['top'] == ncm_top) &
                (df_bloco['x1'] <= ncm_x0) &
                (~df_bloco['string_class'].isin(classes_reservadas))
            )
            indices_same_line = df_bloco[mask_same_line].index.tolist()
            indices_descpt = sorted(set(indices_descpt) | set(indices_same_line))

            if not indices_descpt:
                continue

            texto_concatenado = " ".join(
                df.loc[indices_descpt, 'text'].astype(str).str.strip().tolist()
            ).strip()
            primeiro_descpt = indices_descpt[0]
            df.at[primeiro_descpt, 'text'] = texto_concatenado
            df.at[primeiro_descpt, 'string_class'] = 'Descrição do produto'

        if first_ncm_top is not None:
            desc_tops = df.loc[df['string_class'] == 'Descrição do produto', 'top']
            if not desc_tops.empty and (desc_tops < first_ncm_top - 1.0).any():
                continue
        break
    
    classes_necessarias = ["Descrição do produto", 'NCM/SH', "QUANT", "UNIT", "price"]

    # Opção 3 (docs/BUG_NCM_MISSING.md) — quando concatenate_string_class funde
    # headers adjacentes (ex.: 'NCM/SH O/CST'), refine_product_table_classification
    # propaga o texto fundido como string_class. Aqui, antes de filtrar pelas
    # classes_necessarias, normaliza qualquer string_class que CONTENHA uma chave
    # canônica para a própria chave canônica.
    #
    # IMPORTANTE: 'Descrição do produto' fica DE FORA da lista. Essa classe é
    # responsabilidade do loop upstream (que opera sobre tokens descpt textuais).
    # Se incluída aqui, codigos numéricos rotulados pelo refine com o header
    # da coluna descrição (ex.: 'DESCRIÇÃO DO PRODUTO/ SERVIÇO') seriam
    # canonizados em 'Descrição do produto', inflando n_desc e levando a
    # supervisão humana indevida + erro em get_real_transations.
    chaves_canonicas = ['NCM/SH', 'QUANT', 'UNIT', 'price']
    string_class_atual = df['string_class'].astype(str)
    for chave in chaves_canonicas:
        mask_chave = (
            string_class_atual.str.contains(re.escape(chave), case=False, na=False)
            & (df['string_class'] != chave)
        )
        df.loc[mask_chave, 'string_class'] = chave
        string_class_atual = df['string_class'].astype(str)

    classes_existentes = set(df["string_class"].dropna().astype(str).tolist())

    for classe in classes_necessarias:
        if classe not in classes_existentes and classe != 'NCM/SH':
            raise ValueError(
                f"concatenar_por_ponteiro: classe esperada não encontrada '{classe}'"
            )

    df = df[df['string_class'].isin(classes_necessarias)].reset_index(drop=True)

    supervisao_humana_acionada = False
    if 'NCM/SH' not in classes_existentes:
        supervisao_humana_acionada = True
        n_desc  = (df['string_class'] == 'Descrição do produto').sum()
        n_quant = (df['string_class'] == 'QUANT').sum()
        n_price = (df['string_class'] == 'price').sum()

        if n_desc == n_quant == n_price and n_desc > 0:
            n_produtos = int(n_desc)
        else:
            n_produtos = int(_solicitar_campo_humano('numero_de_produtos_nesta_nf', contexto) or 0)

        indices_desc = df[df['string_class'] == 'Descrição do produto'].index.tolist()
        partes = []
        prev = 0
        for i in range(n_produtos):
            ncm_val = _solicitar_campo_humano(f'ncm (produto {i + 1} de {n_produtos})', contexto)
            pos = indices_desc[i] if i < len(indices_desc) else len(df) - 1
            partes.append(df.iloc[prev:pos + 1])
            partes.append(pd.DataFrame([{'string_class': 'NCM/SH', 'text': ncm_val}]))
            prev = pos + 1
        partes.append(df.iloc[prev:])
        df = pd.concat(partes, ignore_index=True)

    # Opção 7 (bug_fix/BUG_NCM_MISSING.md) — antes de devolver, validar que cada
    # 'Descrição do produto' tem exatamente um 'NCM/SH' correspondente. Só vale
    # para o fluxo automático: se a supervisão humana foi acionada, o operador
    # já fez o trabalho e não cabe à validação derrubar o resultado dele.
    if not supervisao_humana_acionada:
        n_desc_final = (df['string_class'] == 'Descrição do produto').sum()
        n_ncm_final = (df['string_class'] == 'NCM/SH').sum()
        if n_desc_final != n_ncm_final:
            raise ValueError(
                f"concatenar_por_ponteiro: divergência entre nº de descrições ({n_desc_final}) "
                f"e nº de NCM/SH ({n_ncm_final}) ao final do processamento. "
                f"Contexto: {contexto}"
            )

    return df


def new_concatenar_por_ponteiro_filtra_tabela_produtos(df, contexto):
    """
    Versão estrutural do concatenar (vide docs/NEW_concatenar_por_ponteiro_filtra_tabela_produtos.md).

    Invariantes:
    - 1 produto = 1 NCM/SH (8 dígitos) na faixa horizontal da coluna NCM.
    - Janela vertical do produto i = [linha após NCM_{i-1}, linha antes NCM_{i+1}].
    - Cada campo extraído pela faixa de center_x do cabeçalho correspondente.
    """
    LINE_TOL = 2.0
    HEADER_TOL = 5.0

    def _norm(s):
        s = "" if pd.isna(s) else str(s)
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return s.lower().strip()

    df = df.copy().reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=['string_class', 'text'])

    # 1. Header da tabela
    top_min = pd.to_numeric(df['top'], errors='coerce').min()
    df_header = df[
        (pd.to_numeric(df['top'], errors='coerce') <= top_min + HEADER_TOL)
        & (df['string_class'] == 'descpt')
    ].copy()

    # 2. Faixas brutas por alias de cabeçalho.
    # Aliases ordenados do mais específico para o mais curto (substring contains).
    aliases = {
        'descricao': ['descricao do produto', 'discriminacao do produto', 'detalhe do produto'],
        'ncm':       ['ncm/sh', 'ncm sh', 'ncm'],
        'quant':     ['quantidade', 'quant'],
        'unit':      ['valor unit', 'preco unit', 'vlr unit', 'vl unit', 'unit'],
        'price':     ['valor total', 'vl total', 'vlr total', 'total'],
    }
    # Todos os headers descpt ordenados por center_x — usados como divisores
    # para apertar a faixa de cada coluna pelo VIZINHO REAL (não só pelos
    # cabeçalhos da lista relevante).
    todos_headers = df_header.sort_values('center_x').reset_index(drop=True)
    if todos_headers.empty:
        return concatenar_por_ponteiro_filtra_tabela_produtos(df, contexto)

    limites = []
    for i in range(len(todos_headers)):
        row = todos_headers.iloc[i]
        x0, x1 = float(row['x0']), float(row['x1'])
        esq = (float(todos_headers.iloc[i - 1]['x1']) + x0) / 2 if i > 0 else 0.0
        dir = (x1 + float(todos_headers.iloc[i + 1]['x0'])) / 2 if i < len(todos_headers) - 1 else x1 + 50.0
        limites.append({'header_norm': _norm(row['text']), 'esq': esq, 'dir': dir})

    # Mapeia cada campo relevante para a faixa do header que casa pelo alias
    faixas = {}
    for campo, alias_list in aliases.items():
        for alias in alias_list:
            for lim in limites:
                if alias in lim['header_norm']:
                    faixas[campo] = (lim['esq'], lim['dir'])
                    break
            if campo in faixas:
                break

    if 'ncm' not in faixas or 'descricao' not in faixas:
        # supervisão humana — caímos para a função antiga, que tem o fallback
        # já implementado e testado.
        return concatenar_por_ponteiro_filtra_tabela_produtos(df, contexto)

    # Coluna descrição estende até a borda esquerda — código do produto e
    # descrição visual ficam à esquerda do header literal em algumas NFs.
    _, dir_desc = faixas['descricao']
    faixas['descricao'] = (0.0, dir_desc)

    # 4. Linhas físicas (cluster por top)
    df = df.sort_values('top', kind='mergesort').reset_index(drop=True)
    df['top_num'] = pd.to_numeric(df['top'], errors='coerce')
    df['linha_id'] = (df['top_num'].diff().abs().fillna(0) > LINE_TOL).cumsum()

    # 5. Linhas-âncora: NCM = 8 dígitos na faixa NCM
    so_digitos = df['text'].astype(str).str.replace(r'\D', '', regex=True)
    df['center_num'] = pd.to_numeric(df['center_x'], errors='coerce')
    ncm_x0, ncm_x1 = faixas['ncm']
    mask_ncm = (so_digitos.str.len() == 8) & df['center_num'].between(ncm_x0, ncm_x1)
    linhas_ancora = sorted(df.loc[mask_ncm, 'linha_id'].unique().tolist())

    if not linhas_ancora:
        # Sem NCM detectável — supervisão humana via função antiga
        return concatenar_por_ponteiro_filtra_tabela_produtos(df.drop(columns=['top_num', 'center_num', 'linha_id']), contexto)

    # 6. Janela por produto e extração por coluna.
    # cabecalho_linha = ÚLTIMA linha física do header (cobre headers em duas
    # linhas, como 'VALOR' top=508 + 'UNIT' top=511 que ficam em linha_id distintas).
    top_header_max = top_min + HEADER_TOL
    cabecalho_linha = int(df.loc[df['top_num'] <= top_header_max, 'linha_id'].max())
    max_linha = int(df['linha_id'].max())
    saida = []
    for i, L in enumerate(linhas_ancora):
        inicio = (linhas_ancora[i - 1] + 1) if i > 0 else (cabecalho_linha + 1)
        fim = linhas_ancora[i + 1] if i + 1 < len(linhas_ancora) else (max_linha + 1)
        janela = df[df['linha_id'].between(inicio, fim - 1)]

        produto = {}
        for campo, faixa in faixas.items():
            esq, dir = faixa
            tokens = janela.loc[janela['center_num'].between(esq, dir), 'text'].astype(str).tolist()
            produto[campo] = ' '.join(t.strip() for t in tokens if t and t.strip())

        if not produto.get('ncm'):
            raise ValueError(
                f"new_concatenar: NCM ausente no produto {i + 1}. Contexto: {contexto}"
            )
        if not produto.get('descricao'):
            raise ValueError(
                f"new_concatenar: descrição vazia no produto {i + 1}. Contexto: {contexto}"
            )

        saida.append({'string_class': 'Descrição do produto', 'text': produto['descricao']})
        saida.append({'string_class': 'NCM/SH',                'text': produto['ncm']})
        saida.append({'string_class': 'QUANT',                 'text': produto.get('quant', '')})
        saida.append({'string_class': 'UNIT',                  'text': produto.get('unit', '')})
        saida.append({'string_class': 'price',                 'text': produto.get('price', '')})

    return pd.DataFrame(saida)


def _montar_df_produtos_humano(nome_saida, contexto_erro=""):
    """
    Supervisão humana isolada: pede `numero_de_produtos_nesta_nf` e, por produto,
    pede descricao/ncm/quant/preco_unitario/valor. Devolve um df no mesmo schema
    que `get_real_transations` consome — para que o caller só precise rodar
    `get_real_transations` por cima.
    """
    print(f"\n[REVISÃO HUMANA — DANFE multi-folha] {nome_saida}")
    if contexto_erro:
        print(f"  Extração automática falhou: {contexto_erro}")
    n_str = _solicitar_campo_humano("numero_de_produtos_nesta_nf", contexto=nome_saida)
    try:
        n_produtos = int(n_str) if n_str else 0
    except (TypeError, ValueError):
        raise ValueError(
            f"DANFE multi-folha {nome_saida}: número de produtos inválido ('{n_str}')."
        )
    if n_produtos < 1:
        raise ValueError(
            f"DANFE multi-folha {nome_saida}: número de produtos deve ser >= 1."
        )

    rows = []
    for i in range(1, n_produtos + 1):
        ctx = f"{nome_saida} (produto {i}/{n_produtos})"
        rows.append({'string_class': 'Descrição do produto', 'text': _solicitar_campo_humano("descricao", contexto=ctx) or ""})
        rows.append({'string_class': 'NCM/SH',                'text': _solicitar_campo_humano("ncm", contexto=ctx) or ""})
        rows.append({'string_class': 'QUANT',                 'text': _solicitar_campo_humano("quant", contexto=ctx) or ""})
        rows.append({'string_class': 'UNIT',                  'text': _solicitar_campo_humano("preco_unitario", contexto=ctx) or ""})
        rows.append({'string_class': 'price',                 'text': _solicitar_campo_humano("valor", contexto=ctx) or ""})
    
    return pd.DataFrame(rows)


def extrair_produtos_pagina_alternativa(pdf_path, page_index, nome_saida):
    """
    Orquestra a extração de produtos em página alternativa do DANFE multi-folha.

    Reúsa `extract_pdf_words` (com `page_index`) e o pipeline product já existente
    no loop principal. Em caso de falha, delega para `_montar_df_produtos_humano`.
    Retorna sempre um df no schema de `get_real_transations`; o caller faz a
    conversão para lista de dicts.
    """
    try:
        df_pagina = extract_pdf_words(pdf_path, page_index)
        df_pagina['string_class'] = df_pagina['text'].apply(list_regex_filter)
        if 'two_merged_price' in df_pagina['string_class'].values:
            df_pagina = fix_merged_prices(df_pagina)
        df_pagina = join_lonely_character(df_pagina)
        df_classes_pagina = concatenate_string_class(df_pagina)

        df_frac = fracionando_nf_produto(df_classes_pagina)
        tabela = df_frac['tabela_produtos']
        if tabela.empty:
            raise ValueError(f"tabela_produtos vazia em {nome_saida} pág. {page_index + 1}.")
        tabela = refine_product_table_classification(tabela)
        tabela_norm = normatize_produt_classes(tabela)
        tabela_filtrada = semantic_filter(tabela_norm)
        if USAR_NOVO_CONCATENAR:
            return new_concatenar_por_ponteiro_filtra_tabela_produtos(tabela_filtrada, nome_saida)
        return concatenar_por_ponteiro_filtra_tabela_produtos(tabela_filtrada, nome_saida)
    except (ValueError, KeyError, IndexError) as e:
        return _montar_df_produtos_humano(nome_saida, contexto_erro=str(e))


def find_invoice_value(df1, df2):
    """
    Usada exclusivamenteo para NF de Serviço

    Retorna o valor da nota com base na coluna string_class fazendo laço em mapping.
    """

    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.lower().strip()

    df1 = df1.reset_index(drop=True).copy()
    df2 = df2.reset_index(drop=True).copy()

    # Lista de strings
    mapping = [
        #"valor liquido", # Não pode capturar o valor líquido
        "valor total",        
        "preco dos servicos",
        "Valor da Nota",
        'Valor dos Serviços',
        'valor dos servicos',
        'Vlr. dos Serviços',
        #"vl. liquido", # Não pode capturar o valor líquido
        #"vl liquido da nota fiscal", # Não pode capturar o valor líquido
    ]

    # 1 - Maioria dos casos
    # Tentando capturar o valor da nota pelo rótulo correto em string_class na terceira parte da nota
    
    for i in range(len(df1)):
        texto_atual_raw = str(df1.at[i, 'text']).strip()
        classe_atual = _normalizar_texto(df1.at[i, 'string_class'])
        if any(_normalizar_texto(rotulo) in classe_atual for rotulo in mapping):
            return texto_atual_raw


    # 2 - Primeiro recuo
    # Tentando capturar o valor da nota pelo rótulo correto em string_class no miolo da nota
    for i in range(len(df1)):
        texto_atual_raw = str(df1.at[i, 'text']).strip()
        texto_atual = _normalizar_texto(texto_atual_raw)
        if any(_normalizar_texto(rotulo) in texto_atual for rotulo in mapping):
            if i + 1 < len(df1):
                return str(df1.at[i + 1, 'text']).strip()
            return texto_atual_raw

    for i in range(len(df2)):
        texto_atual_raw = str(df2.at[i, 'text']).strip()
        classe_atual = _normalizar_texto(df2.at[i, 'string_class'])
        if any(_normalizar_texto(rotulo) in classe_atual for rotulo in mapping):
            return texto_atual_raw

    for i in range(len(df2)):
        texto_atual_raw = str(df2.at[i, 'text']).strip()
        texto_atual = _normalizar_texto(texto_atual_raw)
        if any(_normalizar_texto(rotulo) in texto_atual for rotulo in mapping):
            if i + 1 < len(df2):
                return str(df2.at[i + 1, 'text']).strip()
            return texto_atual_raw

    raise ValueError("Não foi encontrado o valor da Nota de Serviço em 'string_class ou text' (ex.: valor liquido/valor total).")


def concatenar_conteudo_service_table(df):
    """
    Concatena toda a coluna 'text' abaixo da "discriminação dos serviços" em uma única string.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError("concatenar_conteudo recebeu df inválido.")
    if 'text' not in df.columns:
        raise ValueError("A coluna 'text' não existe em concatenar_conteudo.")

    
    # Palavras que podem aparecer nesse bloco de descrição e que não pertencem à df
    mapping = {
        'DISCRIMINAÇÃO',
        'DESCRIÇÃO'
    }

    serie_texto = (
        df['text']
        .fillna("")
        .astype(str)
        .str.strip()
    )

    indice_inicio = None
    for i, texto in enumerate(serie_texto.tolist()):
        texto_upper = texto.upper()
        if any(chave in texto_upper for chave in mapping):
            indice_inicio = i + 1  # começa abaixo da linha que contém o cabeçalho
            break

    if indice_inicio is None:
        raise ValueError("Tabela de serviços com problema. Não foi encontrado descrição em 'text'.")

    conteudo = " ".join(
        [texto for texto in serie_texto.iloc[indice_inicio:].tolist() if texto]
    )

    return conteudo


def get_real_transations(df):
    """
    Extrai os itens da tabela e retorna uma lista de dicionários.
    Cada dicionário representa uma transação com chaves mapeadas.
    """

    mapping = {
        'Descrição do produto': 'descricao',
        'NCM/SH': 'ncm',
        'QUANT': 'quant',
        'UNIT': 'preco_unitario',
        'price': 'valor'
    }

    df = df.reset_index(drop=True)
    pos_descricao = df.index[df['string_class'] == 'Descrição do produto'].tolist()
    if not pos_descricao:
        raise ValueError("get_real_transations: 'Descrição do produto' não encontrada.")

    lista_dicts_produtos = []

    for i, pos_inicio in enumerate(pos_descricao):
        pos_fim = pos_descricao[i + 1] if i < len(pos_descricao) - 1 else len(df)
        bloco = df.iloc[pos_inicio:pos_fim]

        item_dict = {}
        for string_class, key_dict in mapping.items():
            match = bloco[bloco['string_class'] == string_class]
            if match.empty:
                raise ValueError(
                    f"get_real_transations: classe '{string_class}' não encontrada no produto {i + 1}."
                )
            item_dict[key_dict] = match.iloc[0]['text']

        lista_dicts_produtos.append(item_dict)

    return lista_dicts_produtos


def construct_transation(df_service_description, df_service_value):
    """
    Cria um lista de dicionários com as transações. 1 dict para cada transação
    Mas como serviço é só uma tranação então passa um dicionáro dentro da lista
    É assim porque a função consolidate_data_to_dict recebe lista de transações
    tem nf de produto com várias transações
    """

    # Listas de palavras que cortam partes desnecessárias da string
    descarte_descricao_servico = [
        'Retenções',
        'PIS',
        'COFINS',
        'INSS',
        ]

    # Percorre a lista de palavras de descarte e encontra a posição mais cedo na string
    posicoes = [df_service_description.lower().find(chave.lower()) for chave in descarte_descricao_servico] # Posição de cada palavra (-1 se não encontrada)
    posicoes_validas = [p for p in posicoes if p != -1] # Remove os -1 (palavras ausentes)
    if posicoes_validas:
        df_service_description = df_service_description[:min(posicoes_validas)].strip() # Fatia até a primeira ocorrência

    # Mapeamento de nomes para o dicionário final
    # Tem que ser igual ao global default_nf_template
    mapping = {
        'descricao': df_service_description,
        'ncm': 'não se aplica',
        'quant': 1,
        'preco_unitario': df_service_value,
        'valor': df_service_value
    }
    
    # Convetendo em lista. 1 transação.
    mapping = [mapping]

    return mapping


def cnpj_invoice(df):
    """
    Docstring for cnpj_invoice
    
    :param df: Description
    """
        #Para o teste definitivo vou ter que quebrar essa função
        #return {'cnpj': '25.086.034/0001-71'}

    # 1. Selecionamos os í­ndices que são 'price'
    CNPJ_list = df[(df['string_class'] == 'CNPJ')]

    # Carrega lista de CNPJs bloqueados (tomador, municípios, etc.)
    block_path = Path(__file__).resolve().parent / "block_cnpj.json"
    with open(block_path, "r", encoding="utf-8") as f:
        block_cnpj = json.load(f)

    # 2. Rodamos um laço para separar o CNPJ não do agente operacionalizador nem bloqueado
    for i in CNPJ_list['text']:
        i_digits = "".join(filter(str.isdigit, i)) # Normaliza para só dígitos (igual às chaves do JSON)
        if i_digits not in block_cnpj: # CNPJ não está na lista de bloqueados (tomador, municípios, etc.)
            return {'cnpj': i}


# consulta_nome_fornecedor importada de cnpj_lookup.py


def date_invoice(df):
    """
    retorna a data da nf em dict, que será considerada a primeira data
    que encontrar na df

    """

    data = df[(df['string_class'] == 'data')]
 
    return {'data_emissao': data.iloc[0]['text']} #primeira data do filtro 


def num_nf(df):
    """
    Lista de designações que o número da nf pode receber.
    Toda vez que não acha uma nf por causa do nome, eu aumento a designação

    Quando o for acha conteúdo, retorna o primeiro valor, que provavelmente será o 
    número da nf

    """

    designacao_nf = ['NF-e', 'Nº','Nº.','NF', 'NÚMERO', 'Nota Fiscal', "Nota", 'Número da Nota', 'Num. Nota:']

    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.lower().strip()
    '''

    Obs. A partir da V8, encontrei uma nota com um CNPJ, da cidade do paraná, antes do número. Logo, implantei um laço nos índices.
    '''

    # Opção 4 (docs/BUG_TREATMENT_IN_NUM_NF.md) — formato plausível de nº de NF brasileiro:
    # apenas dígitos com separadores de milhar, sem vírgula nem letras.
    formato_nf_valido = re.compile(r'^\d+(?:\.\d{3})*$')

    df = df.reset_index(drop=True).copy()
    data_indices = df[df['string_class'] == 'data'].index.tolist() # Primeiro corte, procurando todos os "datas" em "String_class"
    ponteiros = data_indices + [len(df)]
    inicio = 0

    # Laço dos blocos antes de "data"
    for fim in ponteiros:
        df_filtrado = df.iloc[inicio:fim].copy()
        string_class_normalizada = df_filtrado['string_class'].apply(_normalizar_texto)

        mask_candidatos = pd.Series(False, index=df_filtrado.index)
        # Próximo laço para encontrar os candidatos a Número de NF
        for chave in designacao_nf:
            # Opção 2 (docs/BUG_TREATMENT_IN_NUM_NF.md) — re.escape impede que '.' em
            # chaves como 'Nº.' funcione como wildcard regex em str.contains.
            chave_normalizada = re.escape(_normalizar_texto(chave))
            mask_candidatos = mask_candidatos | string_class_normalizada.str.contains(chave_normalizada, na=False)


        candidatos_idx = df_filtrado[mask_candidatos].index.tolist()
        # Check ---------------------------
        #print('candidatos_idx ', candidatos_idx)

        # Inicializa canditador
        melhores_candidatos = []


        # Terceiro laço para confirmar na coluna "text" quantos qual número tem mais textos correpondentes a designacao_nf
        for idx_candidato in candidatos_idx:

            # 1 - Encontra o número dentro de "text"
            numero_candidato = str(df_filtrado.at[idx_candidato, 'text']).strip()
            # Opção 4 — descarta candidatos que não batem com formato de nº de NF brasileiro.
            if not formato_nf_valido.match(numero_candidato):
                continue
            
            # 2 - Filtra as três linhas acima do texto numero_candidato
            idx_inicio_janela = max(df_filtrado.index.min(), idx_candidato - 3)
            linhas_acima = df_filtrado.loc[idx_inicio_janela:idx_candidato - 1, 'text'].fillna("").astype(str).tolist()
            # 3 - Normaliza os textos
            texto_contexto = _normalizar_texto(" ".join(linhas_acima))

            # 4 - Qual número tem mais correpondências dentro de designcao_nf?
            score = 0
            for chave in designacao_nf:
                if _normalizar_texto(chave) in texto_contexto:
                    score += 1

            melhores_candidatos.append((score, idx_candidato, numero_candidato))
 
        inicio = fim + 1

        if melhores_candidatos:
            melhores_candidatos.sort(key=lambda x: (-x[0], x[1])) # Ordena
            lista_ordenada = [numero for _, _, numero in melhores_candidatos[:3]] # Melhores 3 com base em ordem dentro do df
            # Deduplica preservando ordem: [1, 1, 478] => [1, 478]. Repetidos viram uma única ocorrência
            # em vez de serem descartados (DANFE imprime o nº duas vezes — duplicidade é sinal de confiança).
            numeros_unicos = list(dict.fromkeys(lista_ordenada))
            if numeros_unicos:
                if len(numeros_unicos) == 1:
                    return {'numero_nf': numeros_unicos[0]}
                return {'numero_nf': numeros_unicos}

       
    raise ValueError('Estou sem número de NF. Veja o que aconteceu')



def consolidate_data_to_dict(list_product_transation, *args):
    """
    Consolida metadados globais com os itens da tabela.
    Retorna uma lista de dicionários preenchidos ou levanta erro em caso de falha.
    """

    #[{'codigo_produto': '20982', 'descricao': 'INVERSOR SENOIDAL EPEVER IPOWER PLUS(T) IP1500-42- 1500W/ 48VCC/ 220VCA', 'ncm': '85044090', 'quant': '900,0000', 'preco_unitario': '2.006,0500', 'valor': '1.805.445,00'}, {'codigo_produto': '20523', 'descricao': 'CONTROLADOR DE CARGA MPPT EPEVER 30A 12/24/36/48V XTRA3415N-XDS2 TROP', 'ncm': '85044010', 'quant': '900,0000', 'preco_unitario': '1.057,1200', 'valor': '951.408,00'}]

    nf_data_tabulated = []

    # 1. Iteramos sobre a lista de transações (os produtos extraí­dos da tabela)
    for trans in list_product_transation:
        
        # Criamos uma cópia limpa do template para o item atual
        transacao = default_nf_template.copy()

        # 2. Laço nas chaves do dicionário para preenchimento
        for key in transacao.keys():
            # A - Busca primeiro dentro do dicionário da própria transaÃ§Ã£o
            if key in trans:
                transacao[key] = trans[key]
            # B - Se não achou (ou se a chave no trans tem nome diferente), busca nos *args
            if transacao[key] is None:

                for arg in args:     
           
                    if key in arg:
                        transacao[key] = arg[key]
                        break
                    

        # 3. Validação de Preenchimento
        # Se após percorrer todos os args, algum campo essencial for None, retorna erro
        campos_vazios = [k for k, v in transacao.items() if v is None]
        
        if campos_vazios:
            # Erro detalhado para facilitar o debug de qual item falhou
            raise ValueError(f"Erro: Não foi possível preencher os campos {campos_vazios} "
                             "Valide os padrões de entrada.")

        nf_data_tabulated.append(transacao)

    return nf_data_tabulated


def export_to_consolidate_table(nf_data_tabulated):
    '''
    Função que recebe a linha em dict, cria um pd.df se não existir
    e consolida no df final e faz o log.

    return: df final
    '''
    global df_anexo1_consolidado

    tabela_anexo1_modelo = pd.DataFrame(nf_data_tabulated)

    # 4.1.1 - Se a tabela estiver vazia, use a primeira como modelo
    if df_anexo1_consolidado.empty:
        df_anexo1_consolidado = tabela_anexo1_modelo.copy()
    else:
        df_anexo1_consolidado = pd.concat(
            [df_anexo1_consolidado, tabela_anexo1_modelo],
            ignore_index=True
        )

    # LOG
    log = {
        'id': seq + 1,
        'nome_arquivo': nome_saida,
        'status': 'processado', #aberto - problema - rejeitado - processado
        'erro': None, #caracteres não alfanuméricos - formato imagem - não é nota fiscal
        'next': None, #NA - chamando OCR
    }
    with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")

    return df_anexo1_consolidado


def validar_total_contra_contrato(df, contrato):
    '''
    Resumo do envio:
      - Número total de NFs enviadas (distintas, agrupadas por `numero_nf`)
      - Valor da CDE e sua participação no contrato
      - Soma das NFs e o quanto isso representa do contrato e da CDE

    Imprime resumo no terminal, registra entrada estruturada em log.json e
    retorna o dict de resultado.
    '''
    def _fmt_brl(valor):
        # Formata número como moeda BRL: troca '.' por ',' e ',' por '.' (padrão pt-BR).
        # Ex.: 1234567.89 -> "R$ 1.234.567,89"
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _parse_brl(v):
        # A coluna `valor` chega como string em formato BR (ex.: '1.805.445,00').
        # pd.to_numeric direto não entende '.' como milhar nem ',' como decimal,
        # então normalizamos antes: remove "R$"/espaços, tira pontos de milhar,
        # troca vírgula decimal por ponto. Numéricos passam direto.
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace('R$', '').strip()
        s = s.replace('.', '').replace(',', '.')
        return s

    serie_normalizada = df['valor'].map(_parse_brl)
    # `errors='coerce'` transforma valores não-numéricos remanescentes em NaN;
    # .sum() ignora NaN — protege contra strings inesperadas.
    soma = float(pd.to_numeric(serie_normalizada, errors='coerce').sum())

    valor_contrato = float(contrato['valor_contrato'])
    valor_cde = float(contrato['valor_cde'])

    # Cada linha do df é um item de NF; agrupamos por `numero_nf` para contar
    # quantas NFs distintas foram processadas neste run.
    n_notas = int(df['numero_nf'].nunique())

    # Guards contra divisão por zero (caso algum contrato tenha valor 0 no JSON).
    pct_cde_sobre_contrato      = (valor_cde / valor_contrato) if valor_contrato else 0.0
    pct_enviado_sobre_contrato  = (soma      / valor_contrato) if valor_contrato else 0.0
    pct_enviado_sobre_cde       = (soma      / valor_cde)      if valor_cde      else 0.0

    # Resumo legível no terminal — referência rápida para o operador após o run.
    print(f"\n[ENVIO] Contrato {contrato['numero_contrato']}")
    print(f"  notas enviadas        : {n_notas}")
    print(f"  valor_contrato        : {_fmt_brl(valor_contrato)}")
    print(f"  valor CDE             : {_fmt_brl(valor_cde)}  ({pct_cde_sobre_contrato*100:.2f}% do contrato)")
    print(f"  soma das NFs          : {_fmt_brl(soma)}")
    print(f"  % enviado / contrato  : {pct_enviado_sobre_contrato*100:.4f}%")
    print(f"  % enviado / CDE       : {pct_enviado_sobre_cde*100:.4f}%\n")

    # Entrada estruturada para auditoria entre runs. Campo 'tipo' diferencia
    # essas linhas dos logs por-NF (que têm 'tipo' implícito de processamento).
    resultado = {
        'tipo': 'resumo_envio',
        'contrato': contrato['numero_contrato'],
        'n_notas': n_notas,
        'soma_nfs': soma,
        'valor_contrato': valor_contrato,
        'valor_cde': valor_cde,
        'pct_cde_sobre_contrato': pct_cde_sobre_contrato,
        'pct_enviado_sobre_contrato': pct_enviado_sobre_contrato,
        'pct_enviado_sobre_cde': pct_enviado_sobre_cde,
    }
    # Append (modo "a") — log.json é newline-delimited JSON, um objeto por linha.
    with open("log.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(resultado, ensure_ascii=False) + "\n")

    return resultado


# Flag para escolher entre a função antiga (heurística incremental) e a nova
# (estrutural por janela de NCM + faixas de coluna). Vide
# docs/NEW_concatenar_por_ponteiro_filtra_tabela_produtos.md.
USAR_NOVO_CONCATENAR = True


#__MAIN__

for seq, arquivo in enumerate(tqdm(arquivos_pdf)):

    # 1 - Extração, classificação e tratamento de dados

    # arquivo.stem pega apenas o nome "NF - 4999" sem o ".pdf"
    nome_saida = f'{arquivo.stem}.pdf'
    
    df_nota = extract_pdf_words(arquivo)
    # CHECK-----------------------------------------------
    #if arquivo_investigado in nome_saida:
    #    df_nota.to_excel(f'{SAIDA_RAIZ}/nota_extraidas_{nome_saida}.xlsx', index=False)

    # LOG
    log = {
        'id': seq +1,
        'nome_arquivo': nome_saida,
        'status': 'aberto', #aberto - rejeitado - processado - problema
        'erro': None, #caracteres não alfanuméricos - formato imagem - não é nota fiscal
        'next': 'confirma_tipo_documento', # confirma_tipo_documento - chamando OCR - Assegurando dados padrões de NF
    }
    with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")
    
    
    # 1.1 - Testa condições básicas de uma extração de NF via plumber
    # A df deve ter em "text" textos tipo NFS-E, tomador, produtos, serviços, outras
    if not confirma_tipo_documento(df_nota):
         
        # LOG
        log = {
            'id': seq + 1,
            'nome_arquivo': nome_saida,
            'status': 'problema', #aberto - problema - rejeitado - processado
            'erro': 'poucos dados', #caracteres não alfanuméricos - formato imagem - não é nota fiscal
            'next': 'Chamando OCR', #chamando OCR
        }
        with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")

        
        # 1.1.1.1 Converter PDF em imagem
        dados_nf = extrair_dados_nf_servico_do_pdf(
            arquivo,
            #salvar_texto_em=f"{SAIDA_RAIZ}/exemplo.txt", # Caso precise olhar um arquivo T
        )
        
        # 1.1.1.2 Confirma se não é NF usando OCR
        if dados_nf['is_nf'] == False:
            
            # LOG
            log = {
                'id': seq + 1,
                'nome_arquivo': nome_saida,
                'status': 'rejeitado', #aberto - problema - rejeitado - processado
                'erro': 'não é nota fiscal', #caracteres não alfanuméricos - formato imagem - não é nota fiscal
                'next': 'NA', #NA - chamando OCR
            }
            with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")
            continue

        else:
            '''
            1.1.1.4 - Como o ocr_reader já fez uma extração exportando
            o dicionário no formato para ser concatenado, vou adiantar e chamar aqui
            e encerrar o laço já subindo os dados
            '''

            nf_data_tabulated = export_to_consolidate_table(dados_nf['nf_extraida'])
    
            continue # Próximo laço

    else:

        # VIA PRINCIPAL - A nota fiscal tem os textos esperados para uma extração.
        log = {
        'id': seq +1,
        'nome_arquivo': nome_saida,
        'status': 'processando', #aberto - rejeitado - processado - processando
        'erro': None, #caracteres não alfanuméricos - formato imagem - não é nota fiscal
        'next': 'convertento em xlsx', #chamando OCR - Assegurando dados de NF - convertento em xlsx
        }
        with open("log.json", "a", encoding="utf-8") as f: f.write(json.dumps(log, ensure_ascii=False) + "\n")        


        # 1.3 - Usando regex, classifico cada string de acordo com a natureza 
        df_nota['string_class'] = df_nota['text'].apply(list_regex_filter)
        # Check ---------------------------------------------
        #if arquivo_investigado in nome_saida:
        #    df_nota.to_excel(f'{SAIDA_RAIZ}/df_core_com_string_class.xlsx', index=False)

        """
        2 - Tratar lista de dados que vem muito quebrada do plumber
        """

        # 2.1 - Separar preços que vieram colados no plumber
        # Não há necessidade de chamar a função se não há nenhuma linha com dois preços juntos
        if 'two_merged_price' in df_nota['string_class'].values:
            
            df_nota = fix_merged_prices(df_nota)

        # 2.2 - Tratamento dos dados - Caracteres como "-", "/", "A", "e" apareceram em linhas separadas
        # atrapalhando o script da função concatenate_string_class.
        # Então eu junto esse caractere com a linha acima.
        df_nota = join_lonely_character(df_nota)
        # Check---------------------
        #if arquivo_investigado in nome_saida:
        #       df_nota.to_excel(f'{SAIDA_RAIZ}/df_join_lonely_character.xlsx', index=False)

        # 2.3 - juntando strings separadas
        df_classes_concatenadas = concatenate_string_class(df_nota)
        # Check---------------------
        #if arquivo_investigado in nome_saida:
        #    df_classes_concatenadas.to_excel(f'{SAIDA_RAIZ}/df_classes_concatenadas.xlsx', index=False)

        '''
        2.5 Aqui há mudança de rota. Pois notas de serviços exigem algoritmo diferente
        de notas de materiais. Isso porque o price da nota de serviço aparece depois da
        tabela descritiva. Já a de materia aparece na tabela de descrição dos produtos
        Como não gosto de funções grandes, vou dividir em duas baseação na condição se é
        nota de material ou serviço
        '''

        # 2.4 - Descobrindo se a nota é de serviço ou produto.
        # product_or_service() só lê df['text'] — não depende de string_class refinada,
        # portanto pode rodar antes de qualquer refine_*_classification.
        invoice_type = product_or_service(df_classes_concatenadas)

        # 2.5 - Listando todos os preços
        if invoice_type == 'product':
            # 2.5.1 - Fraciona o df ANTES de refinar a classificação.
            # fracionando_nf_produto() localiza os cortes por palavras-chave em 'text',
            # sem depender de string_class refinada — pode rodar sobre df_classes_concatenadas.
            df_product_service_desciption = fracionando_nf_produto(df_classes_concatenadas)
            #if arquivo_investigado in nome_saida:
            #    df_product_service_desciption['primeiro_terco'].to_excel(f'{SAIDA_RAIZ}/primeiro_terco_nota_com_problema.xlsx')
            #    df_product_service_desciption['tabela_produtos'].to_excel(f'{SAIDA_RAIZ}/miolo_descricao_nota_com_problema.xlsx')
            #    df_product_service_desciption['ultimo_terco'].to_excel(f'{SAIDA_RAIZ}/ultimo_terco_nota_com_problema.xlsx')
            
            # 2.5.2 - Refina APENAS o primeiro terço (metadados: data, CNPJ, total da nota).
            # refine_table_classification usa todos os descpt como âncoras — adequado aqui
            # porque no primeiro terço não há colunas de tabela gerando falsos positivos.
            df_product_service_desciption['primeiro_terco'] = refine_table_classification(
                df_product_service_desciption['primeiro_terco']
            )

            list_product_service_transation = None
            erro_pipeline = None

            # 2.5.3 - Pipeline normal só roda se a tabela tem dados.
            # Tabela vazia = DANFE multi-folha pág. 1 (produtos em pág. 2+).
            if not df_product_service_desciption['tabela_produtos'].empty:
                try:
                    df_product_service_desciption['tabela_produtos'] = refine_product_table_classification(
                        df_product_service_desciption['tabela_produtos']
                    )

                    # 2.6 - Normatizar o texto em df['text']
                    product_sheet_normatized = normatize_produt_classes(df_product_service_desciption['tabela_produtos'])
                    product_sheet_analysed = semantic_filter(product_sheet_normatized)

                    # 2.7 - Concatenando espacialmente a tabela da nf e obtendo descrições
                    if USAR_NOVO_CONCATENAR:
                        df_product_dict = new_concatenar_por_ponteiro_filtra_tabela_produtos(product_sheet_analysed, nome_saida)
                    else:
                        df_product_dict = concatenar_por_ponteiro_filtra_tabela_produtos(product_sheet_analysed, nome_saida)
                    # 2.8 - Converte em dicionário cada lançamento
                    list_product_service_transation = get_real_transations(df_product_dict)
                except ValueError as e:
                    erro_pipeline = e

            # 2.9 - Retry em página alternativa quando o documento se declara
            # multi-folha (estrutural — `Folha N/M` impresso no DANFE).
            if list_product_service_transation is None:
                if eh_danfe_multifolha(arquivo):
                    df_product_dict_pag2 = extrair_produtos_pagina_alternativa(
                        pdf_path=arquivo, page_index=1, nome_saida=nome_saida
                    )
                    list_product_service_transation = get_real_transations(df_product_dict_pag2)
                elif erro_pipeline is not None:
                    raise erro_pipeline
                else:
                    raise ValueError(
                        f"Tabela de produtos vazia em {nome_saida} e DANFE não se declara multi-folha."
                    )

        else:
            # Para serviços: refine_table_classification roda no df completo — comportamento original.
            # No primeiro terço de serviços não há tabela de produtos, então todos os descpt
            # são âncoras legítimas e a função original não gera falsos positivos.
            df_refined_string_class = refine_table_classification(df_classes_concatenadas)

            # 2.5.1 - Separando o df em duas partes chave (deales - descrição da nota)
            df_product_service_desciption = fracionando_nf_servico(df_refined_string_class)
            # CHECK -------------------------------
            #if arquivo_investigado in nome_saida:
            #   df_product_service_desciption['primeiro_terco'].to_excel(f'{SAIDA_RAIZ}/primeiro_terco_nota_com_problema.xlsx')
            #   df_product_service_desciption['tabela_produtos'].to_excel(f'{SAIDA_RAIZ}/miolo_descricao_nota_com_problema.xlsx')
            #    df_product_service_desciption['ultimo_terco'].to_excel(f'{SAIDA_RAIZ}/ultimo_terco_nota_com_problema.xlsx')

            # 2.9 - Transformar todo o conteúdo dentro de 'discriminação dos serviços'
            try:
                df_service_description = concatenar_conteudo_service_table(df_product_service_desciption['tabela_produtos'])
            except ValueError:
                df_service_description = _solicitar_campo_humano("descricao", contexto=nome_saida)
            # 2.10 - Retornando valor total da nota
            try:
                df_service_value = find_invoice_value(df_product_service_desciption['ultimo_terco'], df_product_service_desciption['tabela_produtos'])
            except ValueError:
                df_service_value = _solicitar_campo_humano("valor", contexto=nome_saida)
            # 2.11 - Transformando em um dict com a transação
            list_product_service_transation = construct_transation(df_service_description, df_service_value)
        

        '''export_to_consolidate_table
        # 3 - Extraindo os elementos do anexo I de dentro da df em formato de dicionário

        Esse bloco só retorna dicionários, pois metadados são menos verbosos
        para manipular.

        '''

        # 3.2 - capturar strings obrigatórias (cnpj, nf e data)
        # 3.2.1 - CNPJ do fornecedor
        cnpj_fornecedor = cnpj_invoice(df_product_service_desciption['primeiro_terco'])
        if cnpj_fornecedor is None:
            cnpj_digitado = _solicitar_campo_humano("cnpj", contexto=nome_saida)
            cnpj_fornecedor = {'cnpj': cnpj_digitado}
        # 3.2.2 - nome do fornecedor
        try:
            nome_fornecedor = consulta_nome_fornecedor(cnpj_fornecedor['cnpj'])
        except Exception:
            fornecedor_digitado = _solicitar_campo_humano("fornecedor", contexto=nome_saida)
            nome_fornecedor = {'fornecedor': fornecedor_digitado}
        # 3.2.3 - data da nf
        try:
            data_nota_fiscal = date_invoice(df_product_service_desciption['primeiro_terco'])
        except (ValueError, IndexError):
            data_digitada = _solicitar_campo_humano("data_emissao", contexto=nome_saida)
            data_nota_fiscal = {'data_emissao': data_digitada}
        # 3.2.4 - número da nf
        try:
            numero_nota_fiscal = num_nf(df_product_service_desciption['primeiro_terco'])
        except ValueError:
            numero_digitado = _solicitar_campo_humano("numero_nf", contexto=nome_saida)
            numero_nota_fiscal = {'numero_nf': numero_digitado}
        # 3.2.5 - produtos
        tipo_nota_fical = {'tipo_nota': invoice_type}
        # Check -------------------
        #if arquivo_investigado in nome_saida:
        #    print(type(cnpj_fornecedor),'\n', type(nome_fornecedor),'\n', type(numero_nota_fiscal),'\n', type(tipo_nota_fical))
        #    print(cnpj_fornecedor,'\n', nome_fornecedor,'\n', numero_nota_fiscal,'\n', tipo_nota_fical)


        """
        4 - Juntando todos os dados extraídos numa tabela de excel. Para isso, vou juntar antes
        em um dicionário, depois somar a uma lista de dicionários.
        Por último, converto em uma tabela excel e exporto
        """

        # 4.1 - Consolidando todos os dicionários em um único

        try:
            nf_data_tabulated = consolidate_data_to_dict(list_product_service_transation, tipo_nota_fical, numero_nota_fiscal, data_nota_fiscal, nome_fornecedor, cnpj_fornecedor, CONTRATO)
        except ValueError as e:
            # Extrai a lista de campos vazios do texto da exceção e pede ao operador
            campos_faltantes = re.findall(r"'(\w+)'", str(e))
            preenchimentos_extras = {}
            for campo in campos_faltantes:
                preenchimentos_extras[campo] = _solicitar_campo_humano(campo, contexto=nome_saida)
            nf_data_tabulated = consolidate_data_to_dict(
                list_product_service_transation, tipo_nota_fical, numero_nota_fiscal,
                data_nota_fiscal, nome_fornecedor, cnpj_fornecedor, CONTRATO, preenchimentos_extras
            )
        df_anexo1_consolidado = export_to_consolidate_table(nf_data_tabulated)


"""
5 - Limpeza semântica da coluna descricao via LLM (batch único pós-laço)
"""

#df_anexo1_consolidado = cleaner.batch_clean(df_anexo1_consolidado, MODO_LLM)

"""
6 - Conversão dos lançamentos em tabela excel

"""

validar_total_contra_contrato(df_anexo1_consolidado, CONTRATO)

_nome_safe_contrato = CONTRATO['numero_contrato'].replace('/', '-').replace(' ', '_')
df_anexo1_consolidado.to_excel(f'{SAIDA_RAIZ}/tabela_de_lancamentos_consolidado_{_nome_safe_contrato}.xlsx', index=False)

