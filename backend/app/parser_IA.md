# parser_IA.md (HISTÓRICO — design do `description_cleaner` antes da migração)

> **Status: HISTÓRICO.** Este documento descreve o design original do `description_cleaner.py` quando ele ainda vivia integrado ao `main_v9.py`. As referências a `main_v9.py` aqui são corretas em contexto histórico. Atualmente (2026-05-05) o cleaner está **desativado em produção** (chamada `cleaner.batch_clean(...)` em `backend/app/main.py:2000` está comentada por questão de performance). O refactor de performance do cleaner é trabalho futuro, fora do escopo das 7 features deste ciclo. Ver `planning/PLAN.md` Decisão #7.

# Objetivo

Resolver extração do parser muito poluída. As notas fiscais não tem dados estruturados em suas descrições e isso não é compatível com uma base de descrição de nota.
Ex. Unitario VALOR TOTAL 1 BM 01 - CONSULTORIA PARA PADRONIZAÇÃO SIGFI- ENERGISA TO- CONTRATO 2023016101 1.00 22.715,17 22.715,17 VALOR TOTAL DA NFS-e R$:22.715,17, Serviço Local Prestação Alíquota Valor Serviço Desc. Incondic. Valor Dedução Valor ISS 1008 8771 2% 32.540,44 0,00 32.540,44 0,00 Natureza da Operação: Exigível com Dedução Descrição do Serviço: Campanha: MLPA- ETO- setembro 2023 Cod.: 210114011902210780070000242971 , CNPJ:, NF: Valor bruto: RS 32540.44, Valor liquido: RS 32540.44 - O que tem relevância semântica: CONSULTORIA PARA PADRONIZAÇÃO SIGFI
Ex2. Comissao: RS 0.00 Vencimento: 20/12/2023 Oficio de Autorizacao de Regime Especial N 039/2023, Processo administrativo No 91452/2023, data de deferimento 16/06/2023 O IR sera recolhido p/ Agencia, conforme Art. 53 da Lei 7.450/85 no valor de 1,5%. Nao  sofre retencao Art. 30 Lei 10.833/2003 Conf. In 459/2004, Art. lo, 2o, Inc. IV. Conforme lei federal 12 .741/2O12- Percentual Aproximado dos Impostos 18,58%- Fonte IBPT Banco: 341 - ITAU, Agencia: 0615, Conta:CORRENTE: 99339-1 Valor Total Desc. Incondicional Dedução Base de Cálculo ISSQN 32.540,44 0,00 32540,44 0,00 0,00 ISSRF IR - O que realmente tem relevância - ENERGISA TO-Campanha: MLPA- ETO- setembro 2023

# Problema

- Notas Fiscais brasileiras são muito desestruturadas.
- Não existem padrões de formatação confiáveis entre emitentes.
- A extração geométrica (pdfplumber) captura texto além da seção de descrição.
- O caminho OCR não tem nenhum filtro semântico.

# Critério de sucesso

- O critério de sucesso é o texto que tem relevância ser passado para a tabela.

---

# Decisões Técnicas

## Abordagem escolhida: Módulo `description_cleaner.py` com `DescriptionCleaner`

Descartada: adicionar função diretamente em `ocr_reader.py` (misturaria responsabilidades, criaria risco de importação circular).

Escolhida: novo módulo independente `description_cleaner.py` — sem dependência de `main_v9.py` nem de `ocr_reader.py`. Ambos importam dele.

## Modo de limpeza

- Controlado pela constante `MODO_LLM` no topo de `main_v9.py`.
- Valores: `"precisao"` (extração mínima e limpa) | `"recall"` (máximo de informação descritiva).
- Propaga para o path OCR via `import ocr_reader; ocr_reader.MODO_LLM_OCR = MODO_LLM`.
- Decisão: usar um único global para facilitar depuração — mudar em um lugar muda o comportamento em todos os paths.

## Lógica de fallback

- O LLM nunca retorna `None`. Fluxo: prompt principal → fallback com system de recall → texto bruto truncado (300 chars).
- Fallback sempre usa `modo="recall"`, independente do `MODO_LLM` configurado.
- Se `OPENROUTER_API_KEY` estiver ausente, retorna o texto bruto sem chamar a API (degradação graciosa).

## Modo OCR

- Segue `MODO_LLM` global (não hardcoded). Consistência preferida sobre otimização pontual.

## ⚠️ Decisão de arquitetura revista: batch pós-laço

**Problema identificado:** chamar `cleaner.clean()` dentro do laço de PDFs (uma chamada por item de descrição) tornou a execução ~40x mais lenta. Script que rodava em 40s passou a rodar em 30min.

**Causa:** latência de rede por chamada (~1-3s) × número de PDFs × número de itens por NF = centenas de chamadas sequenciais.

**Solução aprovada:** remover as chamadas do laço. Após o laço, enviar `df_anexo1_consolidado['descricao']` inteira como lista numerada em lotes. O LLM devolve a lista limpa na mesma ordem e substitui a coluna antes do `.to_excel()`.

**Trade-offs aceitos:**
- Alinhamento da lista de retorno precisa ser garantido (JSON array indexado)
- Lotes necessários se o número de PDFs for muito grande
- A coluna `descricao` fica suja durante o laço e só é limpa no pós-processamento

---

## ⚠️ Decisão de arquitetura revista novamente: abandono do batch, adoção de laço item a item

### Histórico de tentativas e falhas

#### Tentativa 1 — `_BATCH_SIZE = 150` (lotes grandes)

Primeiro teste com batch. Payload de ~225.000 chars por requisição.

**Falhas:**
- `ConnectionResetError(10054)` — servidor fechou a conexão antes de responder. O payload era grande demais para o modelo processar dentro do timeout.
- `Unterminated string` no JSON retornado — o modelo truncava a resposta no meio do array quando o conteúdo gerado ultrapassava o `max_tokens`.

**Causa raiz:** `_BATCH_SIZE` muito alto para modelos gratuitos com limite de contexto e taxa de geração reduzidos.

#### Tentativa 2 — `_BATCH_SIZE = 20` + retry com halving recursivo

Reduzido para 20 itens por lote. Adicionada lógica de divisão ao meio em caso de falha: lote de 20 → 10+10 → 5+5 → 2+3 → itens individuais.

**Falhas observadas via tqdm (modelo `openai/gpt-oss-120b`):**

```
✗ batch falhou: Unterminated string starting at: line 13 column 3 (char 1159)
  → enviando 10 itens
  ✓ tokens: in=659 out=718
  → enviando 10 itens
  ✗ Unterminated string starting at: line 6 column 3 (char 304)
    → enviando 5 itens
    ✓ tokens: in=432 out=400
    → enviando 5 itens
    ✗ Unterminated string starting at: line 1 column 75 (char 74)
      → enviando 2 itens
      ✗ content=None. tokens: in=323 out=80   ← atingiu max_tokens exato
      → enviando 1 item
      ✗ content=None. tokens: in=280 out=80   ← idem
```

**Causa raiz identificada:** a fórmula `max_tokens = min(n * 80, 8000)` produzia `max_tokens=80` para `n=1`. O modelo era cortado pelo limite que nós mesmos definimos — `out=80` era exatamente `max_tokens`. O JSON `["descrição..."]` não cabia e a API retornava `content=null`. O halving recursivo, em vez de recuperar, piorava: cada nível menor tinha um limite de tokens menor, garantindo mais `content=None`.

**Efeito colateral:** 1 lote de 20 com falha gerava ~15 chamadas extras via recursão, acelerando o consumo do rate limit. Com vários lotes falhando em sequência, o servidor respondia com cascata de `429 Too Many Requests`, tornando o processo mais lento do que a abordagem per-item original dentro do laço.

**Tentativa com outros modelos:**
- `nvidia/nemotron-3-super-120b-a12b:free` — retornou JSON inválido em praticamente todos os lotes (maioria `Expecting value: line 1 column 1`), indicando que o modelo ignorava o formato solicitado ou retornava resposta vazia.
- `minimax/minimax-m2.5:free` — rejeitava os input tokens constantemente com 429 antes mesmo de processar.

#### Tentativa 3 — laço item a item (solução atual)

**Decisão:** abandonar o batch. Enviar um item por chamada, dentro de um `for` com `tqdm`, com `_CALL_INTERVAL = 0.5s` entre chamadas para respeitar o rate limit.

**Argumentos que justificam a mudança:**
- O batch só é vantajoso se o modelo retorna JSON estruturado de forma confiável. Nenhum dos modelos gratuitos testados fez isso consistentemente.
- Com o halving recursivo falhando, o batch já efetivamente virava item a item — pelo caminho mais caro (mais chamadas, menor `max_tokens`, mais 429).
- Projeção de tempo com batch falhando: ~40 minutos para 135 itens (observado via tqdm: `11:38<29:05` com 29% completo). Projeção com laço individual: ~4-5 minutos (135 × ~2s/chamada).
- `max_tokens=300` fixo por item (já usado em `_call_llm`) nunca gerou `content=None` nos testes.
- Código resultante é mais simples: remove `_clean_chunk_with_retry`, `_call_llm_batch`, `_BATCH_SIZE`, `_USER_BATCH`.

---

# Stack

## Arquivos novos

| Arquivo | Função |
|---|---|
| `description_cleaner.py` | Módulo LLM. Classe `DescriptionCleaner` + singleton `cleaner` exportado. |
| `contexto_programa.json` | Contexto do programa de obras para guiar o LLM. **Preencher antes dos testes.** |

## Arquivos modificados (estado atual — pré-refatoração batch)

| Arquivo | O que mudou |
|---|---|
| `main_v9.py` | Import de `cleaner`; constante `MODO_LLM`; propagação para `ocr_reader`; chamadas em `get_real_transations()` e `construct_transation()` — **a remover na refatoração batch**. |
| `ocr_reader.py` | Import de `cleaner`; global `MODO_LLM_OCR`; chamada em `extrair_descricao()` — **a remover na refatoração batch**. |

## Pontos de integração — estado alvo (batch)

| Quando | Arquivo | Onde |
|---|---|---|
| Após o laço de PDFs, antes do `.to_excel()` | `main_v9.py` | `cleaner.batch_clean(df_anexo1_consolidado, MODO_LLM)` |

## Dependências externas

| Pacote | Uso |
|---|---|
| `requests` | Chamadas HTTP para OpenRouter (já estava em `requirements.txt`) |
| `python-dotenv` | Carregamento do `.env` (instalar: `pip install python-dotenv`) |

## Variáveis de ambiente (`.env`)

| Variável | Descrição |
|---|---|
| `OPENROUTER_API_KEY` | Chave de API OpenRouter. Obrigatória para limpeza LLM funcionar. |
| `OPENROUTER_MODEL` | ID do modelo a usar (ver tabela abaixo). |

## Modelos testados via OpenRouter

Troca é só o valor de `OPENROUTER_MODEL` no `.env`. Endpoint e payload idênticos para todos.

| Modelo | ID para `.env` | Observações |
|---|---|---|
| GPT OSS 120B | `openai/gpt-oss-120b` | Primeiro testado. Contexto limitado — `_BATCH_SIZE` máximo ~20 antes de truncar. |
| Qwen3 Coder | `qwen/qwen3-coder:free` | Contexto maior. A testar — modelo de código, avaliar qualidade na limpeza de texto. |
| Nemotron Super 120B | `nvidia/nemotron-3-super-120b-a12b:free` | MoE (12B ativos). A testar — potencialmente mais rápido pelo MoE. |

## API

- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Temperatura: `0.0` (extração determinística)
- `max_tokens`: proporcional ao tamanho do lote

---

# Checklist antes de rodar

- [ ] Preencher `contexto_programa.json` com dados reais do contrato/programa
- [ ] Verificar que `OPENROUTER_API_KEY` está no `.env`
- [ ] Instalar `python-dotenv` se necessário: `pip install python-dotenv`
- [ ] Apontar `arquivo_investigado` em `main_v9.py` para uma NF de teste conhecida
- [ ] Testar com `MODO_LLM = "recall"` e comparar resultado com `"precisao"`
