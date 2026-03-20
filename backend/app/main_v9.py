"""
O que tem na 9

Refatoração do main. separando a parte de serviço e de produto.
Separação do fracionando_nf em:

1 - fracionando_nf_produto
2 - fracionando_nf_servico


Vou deixar para revisar a construção das funções novas depois devido 

a todas as fragilidade que julyana está provocando no projeto,
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
from ocr_reader import extrair_dados_nf_servico_do_pdf

# DEPURADOR
arquivo_investigado = 'CGB ENERGIA LTDA - NF 86.pdf'

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
cnpj_tomador = '25.086.034/0001-71'
CAMINHO_RAIZ = "./nfs_analise"
SAIDA_RAIZ = './output_dfs'
# Formato de dicionário por causa da função consolidate_data_to_dict que só recebe
# argumentos em dicionário
CONTRATO = {'contrato':'ECM-023-2025'}
caminho_entrada = Path(CAMINHO_RAIZ)
#rglob("*.pdf") busca recursivamente em todas as subpastas
arquivos_pdf = list(caminho_entrada.rglob("*.pdf"))

# DataFrame acumulador das linhas de todas as NFs processadas
tabela_anexo1_modelo = pd.DataFrame(columns=default_nf_template.keys())
# Cacete!
df_anexo1_consolidado = tabela_anexo1_modelo


def extract_pdf_words(pdf_path):
    """
    Extrai todos os textos, que ficam listatos em text
    O valor que procura está na coluna text
    Use o depurador abaixo para ver a coluna e o df
    """
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]  # Assuming single-page NF
        words = page.extract_words(keep_blank_chars=False, x_tolerance=2, y_tolerance=2)
        df_words = pd.DataFrame(words)

        return df_words


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
    number = re.compile(r'^[0-9.,]*[0-9]$') #r'^\d+(?:[.,]\d+)*$') #'^[1-9.,]*[1-9]$') #'^\d+(?:[.,]\d+)*$' #r'^\d+(?:\.\d+)*$')
    create_date = re.compile(r'\d{2}/\d{2}/\d{4}')
    cnpj = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
    

    # E relação entre index e objeto re
    class_list = [
        
        ('two_merged_price', two_merged_price_pattern),
        ("CNPJ", cnpj),
        ("data", create_date),
        #("price", price), #Price e num são parecidos. Por isso, essa regex precisa vir na frente
        ("num_or_price", number),
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
            row_a['string_class'] = 'price'
            row_a['x1'] = mid_x  # Termina no meio
            row_a['center_x'] = (row_a['x0'] + mid_x) / 2 # Recalcula o centro
            
            # Linha B (Lado Direito da cÃ©lula)
            row_b = row_original.copy()
            row_b['text'] = text2
            row_b['string_class'] = 'price'
            row_b['x0'] = mid_x  # ComeÃ§a do meio
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
    Concatena caracteres solitários à linha anterior apenas se:
    1. Não for um número (caracteres numéricos são preservados).
    2. A classificaÃ§Ã£o for 'unindentfied'.
    """

    indices_to_drop = []
    
    # Iteramos a partir da segunda linha (Ã­ndice 1)
    for i in range(1, len(df)):
        current_text = str(df.iloc[i]['text']).strip()
        current_class = df.iloc[i]['string_class']
        least_class = df.iloc[i-1]['string_class']
        
        # CRITÃ‰RIOS DE FUSÃƒO:
        # Comprimento menor ou igual a 2 E nÃ£o Ã© nÃºmero E classificaÃ§Ã£o Ã© unindentfied
        if len(current_text) <= 2 and not current_text.isdigit() and current_class == "unindentfied" and least_class !='num':
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
    df_grouped = df.groupby('group_id').agg({
        'text': lambda x: ' '.join(map(str, x)),
        'string_class': 'first', # Mantém a classe do primeiro elemento do grupo
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


# def fracionando_nf(df):
#     """
#     Retorna um dicionario com tres DataFrames.

#     Se nao localizar "DADOS ADICIONAIS", usa fallback por salto de "top":
#     detecta um gap anormal comparando o gap atual com a media movel
#     dos gaps anteriores.
#     """

#     #Cada nota tem um espaçamento diferente. Entre a tabela e os dados adicionais. Daí que salto anormal precisa variar,
#     # enquanto não confirmar que um conjunto de palavras não está no meio do df, bem tipo a 
#     # função confirma_tipo_documento.
#     def confirma_tipo_tabela_descricao_serviços(texto):
#         """
#         """

#         texto = " ".join(texto["text"].fillna("").astype(str).tolist())

#         def normalizar(s):
#             s = "" if s is None else str(s)
#             s = unicodedata.normalize("NFKD", s)
#             s = "".join(c for c in s if not unicodedata.combining(c))
#             return s.upper()

#         texto_normalizado = normalizar(texto)

#         chaves_documento_nota_fiscal = [
#             "DESCRIÇÃO",
#             'DISCRIMINAÇÃO',
#             "DETALHADA",
#             "SERVIÇOS",
#         ]

#         qtd_chaves_encontradas = sum(
#             1 for chave in chaves_documento_nota_fiscal if normalizar(chave) in texto_normalizado
#         )
        
#         is_service_descript = qtd_chaves_encontradas >= 1

#         return is_service_descript


#     dic_frac_nf = {
#         "primeiro_terco": pd.DataFrame(columns=df.columns),
#         "tabela_produtos": pd.DataFrame(columns=df.columns),
#         "ultimo_terco": pd.DataFrame(columns=df.columns)
#     }

#     # Chaves de corte baseadas na estrutura padrao de Notas Fiscais
#     chave_corta_primeiro_terco = [
#         'DADOS',
#         'SERVIÇOS',
#         'PRODUTO',
#         'DESCRIÇÃO',
#         'DISCRIMINAÇÃO',
#         'PRODUTOS',
#         'PRODUTO',
#         'PRESTADOS'        
#     ]

#     chave_corta_ultimo_terco = ['DADOS ADICIONAIS', 'INFORMAÇÕES ADICIONAIS', 'OUTRAS INFORMAÇÕES']

#     idx_inicio_tabela = None
#     idx_inicio_adicionais = None

#     # 1. Inicio da tabela tem dois strings de chave_corta_primeiro_terco como separador
#     for chave1 in chave_corta_primeiro_terco:
#         for chave2 in chave_corta_primeiro_terco:
#             if chave1 != chave2:
#                 mask = (
#                     df['text'].str.contains(chave1, case=False, na=False) &
#                     df['text'].str.contains(chave2, case=False, na=False)
#                 )
#                 indices = df[mask].index
#                 if not indices.empty:
#                     idx_inicio_tabela = indices[0]
#                     break
    
#     # 2. Chave que corta o último terço.
#     # Localiza o inicio das informacoes adicionais por palavra-chave.
#     for chave in chave_corta_ultimo_terco:
#         mask = df['text'].str.contains(chave, case=False, na=False)
#         indices = df[mask].index
#         if not indices.empty:
#             idx_inicio_adicionais = indices[0]
#             break   

#     # 2.1 Fallback: se nao achou "DADOS ADICIONAIS", usa salto de top
#     if idx_inicio_tabela is not None and idx_inicio_adicionais is None and 'top' in df.columns:

#         trecho = df.loc[idx_inicio_tabela:].copy()
#         top_num = pd.to_numeric(trecho['top'], errors='coerce')
#         gaps = top_num.diff().abs()
        
#         # Media movel dos gaps anteriores para reduzir falso positivo
#         media_local = gaps.rolling(window=6, min_periods=3).mean().shift(1)

#         for n in range(3, 10): #Vai aumentando o gap

#             # Gap anormal: maior que o padrao local e acima de um piso em pixels
#             salto_anormal = (gaps > (media_local * n)) & (gaps > 12)
#             candidatos = trecho.index[salto_anormal.fillna(False)]
#             idx_inicio_adicionais = candidatos[0]
            
#             if confirma_tipo_tabela_descricao_serviços(df.loc[idx_inicio_adicionais:].copy()):

#                 break #Achou a dimensão que corta os dfs


#     # Sem cabecalho da tabela: Fallback hardcoded corta de trás para frente
#     # Procura a chave em string_class e Descrição em 'text'
#     if idx_inicio_tabela is None:
        
#         if confirma_tipo_tabela_descricao_serviços(df):
        
#             chave_fallbak_parte_superior = [
#                 'Descrição'
#             ]

#             chave_fallbak_parte_inferior = [
#                 'VALOR TOTAL'
#             ]
          
#             for chave in chave_fallbak_parte_inferior:
#                 mask_inferior = df['string_class'].str.contains(chave, case=False, na=False)
#                 indices_inferior = df[mask_inferior].index
#                 if not indices_inferior.empty:
#                     idx_inicio_adicionais = indices_inferior[0]
#                     break

#             df_superior = df.loc[:idx_inicio_adicionais - 1]

#             for chave in chave_fallbak_parte_superior:
#                 mask_superior = df_superior['text'].str.contains(chave, case=False, na=False)
#                 indices_superior = df_superior[mask_superior].index
#                 if not indices_superior.empty:
#                     idx_inicio_tabela = indices_superior[0]
#                     break

#         if idx_inicio_tabela is None:
#             raise ValueError('Não conseguiu dividir a tabela em 3 partes. O que aconteceu?')
        

#     dic_frac_nf['primeiro_terco'] = df.loc[:idx_inicio_tabela].iloc[:-1].copy()


#     if idx_inicio_adicionais is None:
#         # Sem adicionais: assume tabela ate o fim
#         dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:].copy()

#         return dic_frac_nf

#     dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:idx_inicio_adicionais].iloc[:-1].copy()
#     dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()

    
    
#     return dic_frac_nf

# def fracionando_nf(df):
#     """
#     Retorna um dicionario com tres DataFrames.

#     Se nao localizar "DADOS ADICIONAIS", usa fallback por salto de "top":
#     detecta um gap anormal comparando o gap atual com a media movel
#     dos gaps anteriores.
#     """

#     #Cada nota tem um espaçamento diferente. Entre a tabela e os dados adicionais. Daí que salto anormal precisa variar,
#     # enquanto não confirmar que um conjunto de palavras não está no meio do df, bem tipo a 
#     # função confirma_tipo_documento.
#     def confirma_tipo_tabela_descricao_serviços(texto):
#         """
#         """

#         texto = " ".join(texto["text"].fillna("").astype(str).tolist())

#         def normalizar(s):
#             s = "" if s is None else str(s)
#             s = unicodedata.normalize("NFKD", s)
#             s = "".join(c for c in s if not unicodedata.combining(c))
#             return s.upper()

#         texto_normalizado = normalizar(texto)

#         chaves_documento_nota_fiscal = [
#             "DESCRIÇÃO",
#             'DISCRIMINAÇÃO',
#             "DETALHADA",
#             "SERVIÇOS",
#         ]

#         qtd_chaves_encontradas = sum(
#             1 for chave in chaves_documento_nota_fiscal if normalizar(chave) in texto_normalizado
#         )
        
#         is_service_descript = qtd_chaves_encontradas >= 1

#         return is_service_descript

#     def _normalizar_texto(texto):
#         texto = "" if pd.isna(texto) else str(texto)
#         texto = unicodedata.normalize("NFKD", texto)
#         texto = "".join(c for c in texto if not unicodedata.combining(c))
#         return texto.upper()

#     def _candidato_muito_alto(idx):
#         top_limite = pd.to_numeric(df['top'], errors='coerce').quantile(0.20)
#         top_atual = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
#         return pd.notna(top_limite) and pd.notna(top_atual) and top_atual < top_limite

#     def _tem_cabecalho_estrutural(idx):
#         if 'top' not in df.columns:
#             texto_faixa = " ".join(df.loc[[idx], 'text'].fillna("").astype(str).tolist())
#         else:
#             top_ref = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
#             faixa = df[(pd.to_numeric(df['top'], errors='coerce') - top_ref).abs() <= 8].copy()
#             texto_faixa = " ".join(faixa['text'].fillna("").astype(str).tolist())

#         texto_faixa = _normalizar_texto(texto_faixa)
#         tem_item = any(chave in texto_faixa for chave in ['PRODUTO', 'PRODUTOS', 'SERVICO', 'SERVICOS'])
#         tem_descricao = any(chave in texto_faixa for chave in ['DESCRICAO', 'DISCRIMINACAO'])
#         tem_coluna_tabela = any(chave in texto_faixa for chave in ['NCM', 'CFOP', 'QUANT', 'QTD', 'UNIT', 'VALOR', 'TOTAL'])
#         return tem_item and tem_descricao and tem_coluna_tabela

#     def _tem_evidencia_produto_abaixo(idx):
#         if 'top' not in df.columns:
#             trecho = df.loc[idx:].head(25).copy()
#         else:
#             top_ref = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
#             trecho = df[(pd.to_numeric(df['top'], errors='coerce') >= top_ref) & (pd.to_numeric(df['top'], errors='coerce') <= top_ref + 45)].copy()

#         textos = trecho['text'].fillna("").astype(str).str.strip()
#         tem_ncm = textos.str.replace(r'\D', '', regex=True).str.len().eq(8).any()
#         tem_valor = textos.str.contains(r'\d{1,3}(?:\.\d{3})*,\d{2}', regex=True, na=False).any()
#         tem_descricao = trecho['string_class'].astype(str).isin(['descpt', 'unindentfied']).any()
#         return tem_ncm and tem_valor and tem_descricao

#     def _eh_inicio_tabela_valido(idx):
#         if _candidato_muito_alto(idx):
#             #ValueError('Revise NF - tem keywords de tabela antes de 20% de extenção')
#             return False
#         if not _tem_cabecalho_estrutural(idx):
#             ValueError('Revise NF - O cabeçalho não tem informações que parecem com nf de produto')
#             return False 
#         return _tem_evidencia_produto_abaixo(idx)


#     dic_frac_nf = {
#         "primeiro_terco": pd.DataFrame(columns=df.columns),
#         "tabela_produtos": pd.DataFrame(columns=df.columns),
#         "ultimo_terco": pd.DataFrame(columns=df.columns)
#     }

#     # Chaves de corte baseadas na estrutura padrao de Notas Fiscais
#     chave_corta_primeiro_terco = [
#         'DADOS',
#         'SERVIÇOS',
#         'PRODUTO',
#         'DESCRIÇÃO',
#         'DISCRIMINAÇÃO',
#         'PRODUTOS',
#         'PRODUTO',
#         'PRESTADOS'        
#     ]

#     chave_corta_ultimo_terco = ['DADOS ADICIONAIS', 'INFORMAÇÕES ADICIONAIS', 'OUTRAS INFORMAÇÕES']

#     idx_inicio_tabela = None
#     idx_inicio_adicionais = None

    

#     # 1. Inicio da tabela tem dois strings de chave_corta_primeiro_terco como separador
#     encontrou_inicio_valido = False
#     for chave1 in chave_corta_primeiro_terco:
#         for chave2 in chave_corta_primeiro_terco:
#             if chave1 != chave2:
#                 mask = (
#                     df['text'].str.contains(chave1, case=False, na=False) &
#                     df['text'].str.contains(chave2, case=False, na=False)
#                 )
#                 indices = df[mask].index
#                 if not indices.empty:
#                     for idx_candidato in indices:
#                         if _eh_inicio_tabela_valido(idx_candidato):
#                             print('_eh_inicio_tabela_valido:', _eh_inicio_tabela_valido(idx_candidato))
#                             idx_inicio_tabela = idx_candidato
#                             encontrou_inicio_valido = True
#                             break
#             if encontrou_inicio_valido:
#                 break
#         if encontrou_inicio_valido:
#             break
    
#     # 2. Chave que corta o último terço.
#     # Localiza o inicio das informacoes adicionais por palavra-chave.
#     for chave in chave_corta_ultimo_terco:
#         mask = df['text'].str.contains(chave, case=False, na=False)
#         indices = df[mask].index
#         if not indices.empty:
#             idx_inicio_adicionais = indices[0]
#             break   

#     # 2.1 Fallback: se nao achou "DADOS ADICIONAIS", usa salto de top
#     if idx_inicio_tabela is not None and idx_inicio_adicionais is None and 'top' in df.columns:

#         trecho = df.loc[idx_inicio_tabela:].copy()
#         top_num = pd.to_numeric(trecho['top'], errors='coerce')
#         gaps = top_num.diff().abs()
        
#         # Media movel dos gaps anteriores para reduzir falso positivo
#         media_local = gaps.rolling(window=6, min_periods=3).mean().shift(1)

#         for n in range(3, 10): #Vai aumentando o gap

#             # Gap anormal: maior que o padrao local e acima de um piso em pixels
#             salto_anormal = (gaps > (media_local * n)) & (gaps > 12)
#             candidatos = trecho.index[salto_anormal.fillna(False)]
#             idx_inicio_adicionais = candidatos[0]
            
#             if confirma_tipo_tabela_descricao_serviços(df.loc[idx_inicio_adicionais:].copy()):

#                 break #Achou a dimensão que corta os dfs


#     # Sem cabecalho da tabela: Fallback hardcoded corta de trás para frente
#     # Procura a chave em string_class e Descrição em 'text'
#     if idx_inicio_tabela is None:
        
#         if confirma_tipo_tabela_descricao_serviços(df):
        
#             chave_fallbak_parte_superior = [
#                 'Descrição'
#             ]

#             chave_fallbak_parte_inferior = [
#                 'VALOR TOTAL'
#             ]
          
#             for chave in chave_fallbak_parte_inferior:
#                 mask_inferior = df['string_class'].str.contains(chave, case=False, na=False)
#                 indices_inferior = df[mask_inferior].index
#                 if not indices_inferior.empty:
#                     idx_inicio_adicionais = indices_inferior[0]
#                     break

#             df_superior = df.loc[:idx_inicio_adicionais - 1]

#             for chave in chave_fallbak_parte_superior:
#                 mask_superior = df_superior['text'].str.contains(chave, case=False, na=False)
#                 indices_superior = df_superior[mask_superior].index
#                 if not indices_superior.empty:
#                     idx_inicio_tabela = indices_superior[0]
#                     break

#         if idx_inicio_tabela is None:
#             raise ValueError('Não conseguiu dividir a tabela em 3 partes. O que aconteceu?')
        

#     dic_frac_nf['primeiro_terco'] = df.loc[:idx_inicio_tabela].iloc[:-1].copy()


#     if idx_inicio_adicionais is None:
#         # Sem adicionais: assume tabela ate o fim
#         dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:].copy()

#         return dic_frac_nf

#     dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:idx_inicio_adicionais].iloc[:-1].copy()
#     dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()

    
#     return dic_frac_nf



def fracionando_nf_produto(df):
    """
    Fraciona NFs de produto em primeiro terço, tabela de produtos e último terço.
    """
    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.upper()

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
        if 'top' not in df.columns:
            trecho = df.loc[idx:].head(25).copy()
        else:
            top_ref = pd.to_numeric(df.loc[idx, 'top'], errors='coerce')
            trecho = df[(pd.to_numeric(df['top'], errors='coerce') >= top_ref) & (pd.to_numeric(df['top'], errors='coerce') <= top_ref + 45)].copy()

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

    idx_inicio_tabela = None
    idx_inicio_adicionais = None
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
                        if _eh_inicio_tabela_valido(idx_candidato):
                            idx_inicio_tabela = idx_candidato
                            encontrou_inicio_valido = True
                            break
            if encontrou_inicio_valido:
                break
        if encontrou_inicio_valido:
            break

    for chave in chave_corta_ultimo_terco:
        mask = df['text'].str.contains(chave, case=False, na=False)
        indices = df[mask].index
        if not indices.empty:
            idx_inicio_adicionais = indices[0]
            break

    if idx_inicio_tabela is not None and idx_inicio_adicionais is None and 'top' in df.columns:
        trecho = df.loc[idx_inicio_tabela:].copy()
        top_num = pd.to_numeric(trecho['top'], errors='coerce')
        gaps = top_num.diff().abs()
        media_local = gaps.rolling(window=6, min_periods=3).mean().shift(1)

        for n in range(3, 10):
            salto_anormal = (gaps > (media_local * n)) & (gaps > 12)
            candidatos = trecho.index[salto_anormal.fillna(False)]
            if len(candidatos) > 0:
                idx_inicio_adicionais = candidatos[0]
                break

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
    chave_fallbak_parte_inferior = [
        'VALOR TOTAL',
        'VALOR LÍQUIDO',
        'VALOR LIQUIDO',
        'PREÇO DOS SERVIÇOS',
        'PRECO DOS SERVICOS',
        'VL. LÍQUIDO',
        'VL. LIQUIDO'
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
        raise ValueError('Não conseguiu dividir a tabela em 3 partes. O que aconteceu?')

    dic_frac_nf['primeiro_terco'] = df.loc[:idx_inicio_tabela].iloc[:-1].copy()

    if idx_inicio_adicionais is None:
        dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:].copy()
        return dic_frac_nf

    dic_frac_nf['tabela_produtos'] = df.loc[idx_inicio_tabela:idx_inicio_adicionais].iloc[:-1].copy()
    dic_frac_nf['ultimo_terco'] = df.loc[idx_inicio_adicionais:].copy()
    return dic_frac_nf


def fracionando_nf(df):
    """
    Compatibilidade: mantém a assinatura antiga, usando a estratégia de produto.
    """
    return fracionando_nf_produto(df)




def normatize_produt_classes(df):
    """
     Cada NF escreve os títulos dos dados da tabela de produtos de formas diferentes
     normatizar, evita quebrar e torna menos verborragica funções abaixo

     return df com 'string_class' normatizada
    """
    # Só uma constante que pode virar um laço no futuro
    default_text = ["Descrição do produto", "NCM/SH", "QUANT", "UNIT", "price"]

    # 1. Consolida descpt para criar a descrição do produto
    misunderstood_NCM_text = ['ncm', 'NCM/ SH', 'NCM', 'SH']
    misunderstood_quant_text = ['QTD.', 'QUANT.', 'Qtde.']
    misunderstood_unitario_text = ['VALOR UNITÁRIO', 'unitário', 'UNITÁRIO', 'UNITARIO', 'VLR. UNIT.']  
    misunderstood_price_text = ['TOTAL', 'VLR. TOTAL', 'Valor total']
    

    df.loc[df['string_class'].isin(misunderstood_NCM_text), 'string_class'] = 'NCM/SH'
    df.loc[df['string_class'].isin(misunderstood_quant_text), 'string_class'] = 'QUANT'
    df.loc[df['string_class'].isin(misunderstood_unitario_text), 'string_class'] = 'UNIT'
    df.loc[df['string_class'].isin(misunderstood_price_text), 'string_class'] = 'price'


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


def concatenar_por_ponteiro_filtra_tabela_produtos(df, x_tol=30.0):
    """
    Concatena linhas de texto baseando-se no intervalo entre NCM.
    1 - Tem que ter NCM na tabela. 
    
    Conta todos os NCM, serão os produtos
    Células que sofreram concatenação são reclassificadas como 'Descrição do produto'.
    """
    
    # Lista a quantidade de produtos na tabela, via contagem de NCM
    indices_ncm = df[df['string_class'] == 'NCM/SH'].index.tolist()

    if not indices_ncm:
        raise ValueError('NF de produto. Erro no NCM. Não será possível gerar os lançamentos')


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
        return df[df['string_class'] == 'NCM/SH'].index.tolist()

    top_drift = 15.0
    center_x_descricao = encontrar_ponteiro_coluna_descricao(df)
    indices_ncm = encontrar_ponteiros_linha_ncm(df)

    for i, idx_ncm in enumerate(indices_ncm):
        ncm_top = float(df.at[idx_ncm, 'top'])

        # Não o índice NCM
        if i < len(indices_ncm) - 1: # fica sem índice
            next_ncm_top = float(df.at[indices_ncm[i + 1], 'top'])
            #Usa top_drift
            mask_bloco = (df['top'] >= (ncm_top - top_drift)) & (df['top'] < next_ncm_top)
        else:
            mask_bloco = df['top'] >= (ncm_top - top_drift)

        # Filtra só o os top == NCM com top_drift de 15
        df_bloco = df[mask_bloco].copy()
         
        if center_x_descricao is None:
            mask_descpt = df_bloco['string_class'] == 'descpt'
 
        else:

            mask_descpt = (
                (df_bloco['string_class'] == 'descpt') & # Texto de descrição de produto
                ((df_bloco['top'] - ncm_top) <= top_drift) & # Filtro vertical
                
                #x_tol tem muito peso para capturar coisas como abaixo

                      #DESCRIÇÃO DO PRODUTO/SERVIÇO

                #MATERIAL GRAFICO
                #CONFECCAO DE MATERIAL
                #GRAFICO REFERENTE AO
                #PROGRAMA MAIS LUZ PARA
                
                ((df_bloco['center_x'] - center_x_descricao) <= x_tol)
            )



        indices_descpt = df_bloco[mask_descpt].index.tolist()
        if not indices_descpt:
            continue

        texto_concatenado = " ".join(
            df.loc[indices_descpt, 'text'].astype(str).str.strip().tolist()
        ).strip()
        primeiro_descpt = indices_descpt[0]
        df.at[primeiro_descpt, 'text'] = texto_concatenado
        df.at[primeiro_descpt, 'string_class'] = 'Descrição do produto'


    # 3 Remove as linhas desnecessárias. Filtra o df para as classes necessárias
    classes_necessarias = ["Descrição do produto", "NCM/SH", "QUANT", "UNIT", "price"]
    classes_existentes = set(df["string_class"].dropna().astype(str).tolist())

    # Alerta para alguma classe faltante
    for classe in classes_necessarias:
        if classe not in classes_existentes:
            raise ValueError(
                f"concatenar_por_ponteiro: classe esperada não encontrada na função concatenar ponteiro '{classe}'"
            )

    df = df[df['string_class'].isin(classes_necessarias)]
   
    return df


def find_invoice_value(df1, df2):
    """
    Usada exclusivamenteo para NF de Serviço

    Retorna o valor da nota com base na coluna string_class fazendo laço em mapping.
    """
    if df1 is None or not isinstance(df1, pd.DataFrame):
        raise ValueError("find_invoice_value não recebeu df1.")
    if df2 is None or not isinstance(df2, pd.DataFrame):
        raise ValueError("find_invoice_value não recebeu df2.")

    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.lower().strip()

    df1 = df1.reset_index(drop=True).copy()
    df2 = df2.reset_index(drop=True).copy()

    # Lista de strings
    mapping = [
        "valor liquido",
        "valor total",        
        "preco dos servicos",
        "vl. liquido",
        "vl liquido da nota fiscal",
    ]

    for i in range(len(df1)):
        texto_atual_raw = str(df1.at[i, 'text']).strip()
        classe_atual = _normalizar_texto(df1.at[i, 'string_class'])
        if any(rotulo in classe_atual for rotulo in mapping):
            return texto_atual_raw

    for i in range(len(df1)):
        texto_atual_raw = str(df1.at[i, 'text']).strip()
        texto_atual = _normalizar_texto(texto_atual_raw)
        if any(rotulo in texto_atual for rotulo in mapping):
            if i + 1 < len(df1):
                return str(df1.at[i + 1, 'text']).strip()
            return texto_atual_raw

    for i in range(len(df2)):
        texto_atual_raw = str(df2.at[i, 'text']).strip()
        classe_atual = _normalizar_texto(df2.at[i, 'string_class'])
        if any(rotulo in classe_atual for rotulo in mapping):
            return texto_atual_raw

    for i in range(len(df2)):
        texto_atual_raw = str(df2.at[i, 'text']).strip()
        texto_atual = _normalizar_texto(texto_atual_raw)
        if any(rotulo in texto_atual for rotulo in mapping):
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
    
    # Mapeamento de nomes para o dicionário final
    mapping = {
        'Descrição do produto': 'descricao',
        'NCM/SH': 'ncm',
        'QUANT': 'quant',
        'UNIT': 'preco_unitario',
        'price': 'valor'
    }

    indices_descricao = df[df['string_class'] == 'Descrição do produto'].index.tolist()
    if not indices_descricao:
        raise ValueError("get_real_transations encontrou 'Descrição do produto' para montar transações.")

    lista_dicts_produtos = []
    

    for i, idx_inicio in enumerate(indices_descricao):
        if i < len(indices_descricao) - 1:
            idx_fim = indices_descricao[i + 1]
            bloco = df.loc[idx_inicio:idx_fim - 1]
        else:
            bloco = df.loc[idx_inicio:]

        item_dict = {}
        for string_class, key_dict in mapping.items():
            match = bloco[bloco['string_class'] == string_class]
            item_dict[key_dict] = match.iloc[0]['text'] if not match.empty else None

        lista_dicts_produtos.append(item_dict)

    return lista_dicts_produtos  


def construct_transation(df_service_description, df_service_value):
    """
    Cria um lista de dicionários com as transações. 1 dict para cada transação
    Mas como serviço é só uma tranação então passa um dicionáro dentro da lista
    É assim porque a função consolidate_data_to_dict recebe lista de transações
    tem nf de produto com várias transações
    """

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

    # 1. Selecionamos os Ã­ndices que sÃ£o 'price'
    CNPJ_list = df[(df['string_class'] == 'CNPJ')]

    # 2. Rodamos um laÃ§o para separar o CNPJ nÃ£o do agente operacionalizador
    for i in CNPJ_list['text']:
        #sai da funÃ§Ã£o assim que achar o CNPJ do tomador
        if i != cnpj_tomador:
            return {'cnpj': i}


def consulta_nome_fornecedor(cnpj):
    """
    Usa a API do site cnpja.com para obter o nome do fornecedor
    
    :param cnpj: string com o cnpj
    return: string com nome do fornecedor
    """
    # bloqueio
    return {'fornecedor': 'NÃo estará disponível agora. bloqueado com return'}

    # retira tudo do cnpj e deixa só o número. Ex -> 12.420.339/0003-98 - 12420339000398
    cnpj = "".join(filter(str.isdigit, cnpj))

    # URL da API aberta do CNPJá
    url = f"https://open.cnpja.com/office/{cnpj}" #CNPJjá
    # url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}" #brasilAPI
    

    try:

        response = requests.get(url)
        print(response)

        if response.status_code == 200:
            dados = response.json()
            # O campo 'company' contÃ©m o objeto com o nome da empresa
            nome_empresa = dados.get('company', {}).get('name', 'Nome nÃ£o encontrado')
            return {'fornecedor': nome_empresa}
        elif response.status_code == 429:
            return "Erro: Limite de requisiÃ§Ãµes atingido (max 5 por minuto)."
        else:
            return f"Erro na consulta: Status {response.status_code}"
            
    except Exception as e:
        return f"Ocorreu um erro: {e}"


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

    designacao_nf = ['NF-e', 'NF', 'NÚMERO', 'Nota Fiscal', "Nota", 'Número da Nota', 'Num. Nota:']

    def _normalizar_texto(texto):
        texto = "" if pd.isna(texto) else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return texto.lower().strip()
    '''

    Obs. A partir da V8, encontrei uma nota com um CNPJ, da cidade do paraná, antes do número. Logo, implantei um laço nos índices.
    '''

    df = df.reset_index(drop=True).copy()
    data_indices = df[df['string_class'] == 'data'].index.tolist()


    ponteiros = data_indices + [len(df)]
    inicio = 0

    for fim in ponteiros:
        df_filtrado = df.iloc[inicio:fim].copy()
        string_class_normalizada = df_filtrado['string_class'].apply(_normalizar_texto)

        for nome in designacao_nf:
            nome_normalizado = _normalizar_texto(nome)
            mask_header = string_class_normalizada.str.contains(nome_normalizado, na=False)

            all_num = ", ".join(
                df_filtrado.loc[mask_header, 'text']
                .dropna()
                .astype(str)
                .str.strip()
                .tolist()
            )

            if all_num:
                return {'numero_nf': all_num}

        inicio = fim + 1

       
    raise ValueError('Estou sem número de NF. Veja o que aconteceu')


def product_or_service(df):
    """
    Classifica a NF como produto ou serviço com base no texto extraído.

    Retorno:
    - "procuct" para nota de produto/material
    - "service" para nota de serviço
    """

    if df is None or df.empty:
        return ValueError('Não chegou df até product_or_service'
                          'Revise o script')

    # Usa a coluna "text" quando existir; caso contrário, usa a primeira coluna.
    text_series = df["text"].fillna("").astype(str)
    
    corpus = " ".join(text_series.tolist())

    product_keywords = (
        "CÓDIGO PRODUTO",
        "ncm",
        'NCM',
        "cfop",
        "icms",
        'UNITÁRIO',
        "ipi",
        "quant",
        'CFOP',
        "qtd",
        'QTD',
        "valor unitario",
    )

    product_score = sum(1 for k in product_keywords if k in corpus)

    if product_score > 1: 
        return "product"
    
    return "service"


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
            dpi=300,
            # salvar_texto_em="exemplo.txt", # Caso precise olhar um arquivo T
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
        #if '72 - NFE-13230507589' in nome_saida:
            #   df_nota.to_excel(f'{SAIDA_RAIZ}/df_join_lonely_character.xlsx', index=False)

        # 2.3 - juntando strings separadas
        df_classes_concatenadas = concatenate_string_class(df_nota)
        # Check---------------------
        #if '72 - NFE-13230507589' in nome_saida:
        #    df_classes_concatenadas.to_excel(f'{SAIDA_RAIZ}/df_classes_concatenadas.xlsx', index=False)

        # 2.4 - Reclassicando rótulos num_price com base em Ancoragem Horizonta
        df_refined_string_class = refine_table_classification(df_classes_concatenadas)
        # Check ------------------------------------------------
        #if arquivo_investigado in nome_saida:
        #    df_refined_string_class.to_excel(f'{SAIDA_RAIZ}/string_class_num_prices_corretamente_classificadas_{nome_saida}.xlsx')

        '''
        2.5 Aqui há mudança de rota. Pois notas de serviços exigem algoritmo diferente 
        de notas de materiais. Isso porque o price da nota de serviço aparece depois da 
        tabela descritiva. Já a de materia aparece na tabela de descrição dos produtos
        Como não gosto de funções grandes, vou dividir em duas baseação na condição se é 
        nota de material ou serviço
        '''

        # 2.5.1 - Descobrindo se a nota é de serviço ou produto
        invoice_type = product_or_service(df_refined_string_class)
  

        # 2.6 - Listando todos os preços
        if invoice_type == 'product':
            # 2.5.1 - Separando o df em duas partes chave (deales - descrição da nota)
            df_product_service_desciption = fracionando_nf_produto(df_refined_string_class)
            # CHECK -------------------------------
            #if arquivo_investigado in nome_saida:
            #    df_product_service_desciption['primeiro_terco'].to_excel(f'{SAIDA_RAIZ}/primeiro_terco_nota_com_problema.xlsx')
            #    df_product_service_desciption['tabela_produtos'].to_excel(f'{SAIDA_RAIZ}/miolo_descricao_nota_com_problema.xlsx')
            #    df_product_service_desciption['ultimo_terco'].to_excel(f'{SAIDA_RAIZ}/ultimo_terco_nota_com_problema.xlsx')

            # 2. 6 - Normatizar o texto em df['text']           
            product_sheet_normatized = normatize_produt_classes(df_product_service_desciption['tabela_produtos'])

            product_sheet_analysed = semantic_filter(product_sheet_normatized)


            # Check ----------------------------------
            #df_core_classes_concatenadas.to_excel(f'{SAIDA_RAIZ}/lista_lancamentos_{nome_saida}.xlsx')
            # 2.7 - Concatenando espacialmente a tabela da nf e obtendo descriçõ
            # clses no campo string_class
            df_product_dict = concatenar_por_ponteiro_filtra_tabela_produtos(product_sheet_analysed)
            # Check -------------------------------------------------
            #if arquivo_investigado in nome_saida:
            #    df_product_dict.to_excel(f'{SAIDA_RAIZ}/tabela_arrumadinha.xlsx')
            # 2.8 - Converte em dicionário cada lançamento
            list_product_service_transation = get_real_transations(df_product_dict)

        else:
            # 2.5.1 - Separando o df em duas partes chave (deales - descrição da nota)
            df_product_service_desciption = fracionando_nf_servico(df_refined_string_class)
            # CHECK -------------------------------
            #if arquivo_investigado in nome_saida:
            #    df_product_service_desciption['primeiro_terco'].to_excel(f'{SAIDA_RAIZ}/primeiro_terco_nota_com_problema.xlsx')
            #    df_product_service_desciption['tabela_produtos'].to_excel(f'{SAIDA_RAIZ}/miolo_descricao_nota_com_problema.xlsx')
            #    df_product_service_desciption['ultimo_terco'].to_excel(f'{SAIDA_RAIZ}/ultimo_terco_nota_com_problema.xlsx')

            # 2.9 - Transformar todo o conteúdo dentro de 'discriminação dos serviços'
            df_service_description = concatenar_conteudo_service_table(df_product_service_desciption['tabela_produtos'])
            # 2.10 - Retornando valor líquido da nota
            df_service_value = find_invoice_value(df_product_service_desciption['ultimo_terco'], df_product_service_desciption['tabela_produtos'])
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
        # 3.2.2 - nome do fornecedor
        nome_fornecedor = consulta_nome_fornecedor(cnpj_fornecedor['cnpj'])
        # 3.2.3 - data da nf
        data_nota_fiscal = date_invoice(df_product_service_desciption['primeiro_terco'])
        # 3.2.4 - data da nf
        numero_nota_fiscal = num_nf(df_product_service_desciption['primeiro_terco'])
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

        nf_data_tabulated = consolidate_data_to_dict(list_product_service_transation, tipo_nota_fical, numero_nota_fiscal, data_nota_fiscal, nome_fornecedor, cnpj_fornecedor, CONTRATO)
        df_anexo1_consolidado = export_to_consolidate_table(nf_data_tabulated)


"""
5 - Conversão dos lançamentos em tabela excel 

"""

df_anexo1_consolidado.to_excel(f'{SAIDA_RAIZ}/tabela_de_lancamentos_consolidado{CONTRATO['contrato']}.xlsx', index=False)

