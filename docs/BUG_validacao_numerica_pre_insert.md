# BUG — Dado numérico malformado chega ao INSERT sem validação

**Registrado:** 2026-05-19
**Status:** ✅ corrigido no backend em 2026-05-19 (ver "Resolução" ao final).
**Caso disparador:** `bug_fix/NF - 12259.pdf` (NFSe de São Luís/MA)
**Severidade:** alta — corrompe dado silenciosamente em um campo, derruba o INSERT em outro.
**Relacionado:** [`BUG_sessao_sqlalchemy_envenenada.md`](BUG_sessao_sqlalchemy_envenenada.md) — o crash deste bug é o gatilho daquele.

## Sintoma

Upload da NF-12259 falhou com:

```
(psycopg.errors.NotNullViolation) null value in column "preco_unitario"
of relation "nf_entries" violates not-null constraint
```

A row que tentou ser inserida tinha `preco_unitario = None` e `valor_total = 0`,
sendo que o PDF traz, explícito, `Valor Unitário = Valor Total = R$ 160.569,92`.

## Mecanismo

1. O parser, no caminho de NF de serviço, devolveu para os campos `valor` e
   `preco_unitario` **a mesma string não-numérica** (texto com rótulo/prefixo
   grudado, ex.: `"R$ 160.569,92"` ou a linha inteira do rótulo). Não houve
   campo *faltando* — houve campo *mal-extraído*. O parser saiu com exit 0.

2. No backend, `parse_brazilian_decimal` (`normalization.py:30`) só sabe lidar
   com `"1.234,56"`. Em texto com prefixo, `Decimal(...)` levanta
   `InvalidOperation` e a função **retorna `None`**.

3. Em `create_nf_entry` (`server.py:205-207`) as três colunas numéricas tratam
   esse `None` de três jeitos diferentes:

   ```python
   quantidade     = parse_brazilian_decimal(row.get("quant"))            # sem fallback
   preco_unitario = parse_brazilian_decimal(row.get("preco_unitario"))   # sem fallback → None
   valor_total    = parse_brazilian_decimal(row.get("valor")) or 0       # fallback p/ 0
   ```

   - `valor_total` cai no `or 0` → uma NF de R$ 160 mil seria gravada como
     **R$ 0,00, sem erro e sem flag**.
   - `preco_unitario` fica `None` → estoura o `NOT NULL` no `db.flush()`
     (`server.py:214`).

## Os dois problemas de fundo

### A. Tratamento assimétrico de falha de parsing numérico

`valor_total`, `preco_unitario` e `quantidade` deveriam ter **uma política
única**. O `or 0` é, sem ironia, o pior dos comportamentos: o crash ao menos é
visível; o `or 0` persiste valor errado em silêncio. Nenhum dos três deveria
virar `0` calado — falha de conversão de um campo monetário obrigatório é um
evento que precisa ser sinalizado.

### B. Não há camada de validação entre o parser e o banco

Hoje a *constraint `NOT NULL` do Postgres* é o que faz validação semântica da
row — por acidente, no pior ponto possível (dentro do `flush()`, com mensagem
opaca de psycopg). A rede de proteção do F8b (`nf_pending` + modal) **não cobre
esta classe de falha**: ela só dispara em `ParserCampoFaltante` (exit 2),
quando o *parser admite* não ter achado o campo. Aqui o parser "achou" — só
achou errado —, então a row malformada flui sem obstáculo até o INSERT.

## Resolução (2026-05-19)

> Correção **só no backend**. O parser (`main.py`) será corrigido em projeto
> separado; estas mudanças permanecem válidas mesmo com o parser corrigido.

**Decisão de roteamento (revisada):** campo numérico ilegível **não** vira
`erro_parsing`. É roteado para o **fluxo de preenchimento humano do F8b** — a
mesma `nf_pending` + modal que o parser dispara via `ParserCampoFaltante`. O
operador preenche o valor correto pelo modal; o defeito é recuperável sem
reenvio do PDF. (Primeira versão deste fix mandava para `erro_parsing`;
corrigido após revisão — o objetivo é aproveitar a maquinaria do F8b.)

### O que mudou

**`backend/app/normalization.py`** — duas adições (camada de defesa / safety
net):

- `class NfRowValidationError(ValueError)` — exceção tipada para campo
  numérico obrigatório ausente/ilegível. Subclasse de `ValueError`.
- `parse_required_decimal(value, field_name)` — versão estrita de
  `parse_brazilian_decimal`: em falha, levanta `NfRowValidationError`
  nomeando o campo, em vez de devolver `None`.

**`backend/app/server.py`** — três mudanças:

1. **`_invalid_numeric_fields(row)`** — devolve as chaves do parser
   (`quant`/`preco_unitario`/`valor`) cujo valor não converte para `Decimal`
   (`parse_brazilian_decimal` → `None`).

2. **Roteamento no generator do `POST /api/uploads`** — logo após o parser
   retornar, se o `outcome` é `processado` **com exatamente 1 linha** e essa
   linha tem campo numérico inválido, o `outcome` é **convertido em
   `pending_input`**:

   ```python
   if outcome.status == "processado" and len(outcome.rows) == 1:
       campos = _invalid_numeric_fields(outcome.rows[0])
       if campos:
           outcome.status   = "pending_input"
           outcome.prefilled = outcome.rows[0]   # vira a row do modal
           outcome.missing   = campos            # campos a preencher
           outcome.rows      = []
   ```

   O bloco F8b já existente (`if outcome.status == "pending_input":`) então
   trata tudo **sem nenhuma duplicação de código**: cria a `NfPending`, emite
   o SSE `file_pending_input`, suspende o generator no `asyncio.Event` do
   registry, e ao `/resolve` retoma e insere a `NfEntry`. O `/resolve` faz
   `row = {**prefilled, **filled}` — as chaves de `missing` (`preco_unitario`,
   `valor`, …) batem com as chaves da row, então o valor digitado pelo
   operador sobrescreve o valor sujo.

3. **`create_nf_entry`** usa `parse_required_decimal` nos três campos
   numéricos (política única; eliminado o `or 0` isolado de `valor_total`,
   que corrompia em silêncio). Aqui é **last line of defense**: o caminho
   primário (item 2) intercepta antes; este `raise` só dispara em NF
   multi-linha (ver abaixo) ou se o operador digitar lixo no modal. O
   `except` per-file do upload tem um ramo: erro `NfRowValidationError` →
   `status_reason` usa a mensagem (que nomeia o campo).

### Por que só NF de 1 linha vai para o modal

A pendência F8b é **single-row por construção**: `prefilled` é uma row,
`/resolve` insere **uma** `NfEntry`. Rotear uma NF multi-linha (produtos)
para uma única pendência perderia as demais linhas. Então:

- **NF de 1 linha** (serviço — caso da NF-12259, e a maioria esmagadora) →
  modal F8b. ✅
- **NF multi-linha** com campo numérico ilegível → cai no safety net
  `NfRowValidationError` → `erro_parsing` com motivo nomeando o campo. Sem
  perda de dado parcial (o arquivo inteiro é rejeitado), sem `0` silencioso,
  sem crash. Suportar pendência multi-linha exigiria evoluir o schema/spec do
  F8b — fica como melhoria futura.

### Cobertura de teste

`backend/tests/test_upload_row_validation.py`:

- `test_invalid_numeric_fields_detecta_ilegivel_e_ausente` — unidade do helper.
- `test_single_row_illegible_numeric_routes_to_pending` — reproduz a NF-12259
  (`preco_unitario`/`valor` = `"R$ 160.569,92"`); verifica que uma `NfPending`
  é criada com `missing == {preco_unitario, valor}` e `prefilled` carregando a
  row. (O fluxo F8b de suspender/retomar não é dirigível por `TestClient` —
  cada request abre seu event loop; o teste pré-seta o event do registry para
  o generator não suspender. A resolução em si é coberta por
  `test_pending_endpoints.py`.)
- `test_multirow_with_illegible_numeric_marks_erro_parsing` — NF multi-linha
  cai no safety net `erro_parsing`.

### Se o erro reaparecer

- `NotNullViolation` em coluna numérica de `nf_entries` **não deveria mais
  acontecer** — `_invalid_numeric_fields` roteia para o modal, e
  `parse_required_decimal` barra o que escapar. Se acontecer, o defeito é em
  outra coluna (`fornecedor`/`ncm`/`contrato` via `normalize_nullable_text`,
  que ainda pode devolver `None`) — aí o caso é o do doc do SAVEPOINT.
- Upload de NF de 1 linha **não** abrindo o modal para campo sujo → conferir
  se a conversão `outcome → pending_input` ainda roda e se `len(outcome.rows)`
  é mesmo 1 (NF de serviço deveria produzir 1 row via `construct_transation`).
- NF de 1 linha indo para `erro_parsing` em vez do modal → `_invalid_numeric_fields`
  não detectou o campo, ou a conversão foi removida.
- Em qualquer caso de campo sujo: o valor veio errado do parser — inspecionar
  o `parser_debug/` do upload e corrigir a extração no projeto do parser.
