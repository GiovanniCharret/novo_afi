# BUG — Erro de banco em um arquivo descarta o lote inteiro de upload

**Registrado:** 2026-05-19
**Status:** ✅ corrigido em 2026-05-19 (ver "Resolução" ao final). Antes:
confirmado em produção — um bloco de upload foi descartado, o `except`
permitiu o fluxo continuar e o lote sumiu.
**Caso disparador:** `bug_fix/NF - 12259.pdf` — o `NotNullViolation` descrito em
[`BUG_validacao_numerica_pre_insert.md`](BUG_validacao_numerica_pre_insert.md).
**Severidade:** crítica — perda total de dados de um lote, silenciosa.

## Sintoma

Um único PDF malformado no meio de um lote de upload faz **todo o lote** ser
descartado do banco — incluindo os arquivos que o stream SSE já reportou como
`processado`. O operador vê a UI quase toda verde; o banco fica vazio.

## Modelo de transação do upload

`POST /api/uploads` usa **uma única `Session` SQLAlchemy para o lote inteiro**:

- `server.py:765` — `with get_session() as db:`. O `get_session` (`db.py:57`)
  só faz `session.close()` no `finally` — **sem commit nem rollback implícito**.
- `sessionmaker`: `autoflush=False, autocommit=False` (`db.py:44`).
- Cada `db.flush()` (do `batch`, de cada `record`, de cada `nf_entry`) manda o
  INSERT ao Postgres **dentro da transação aberta** — não confirma nada.
- No caminho normal (sem pendência F8b) o **único `db.commit()` é o da linha
  1071**, após o loop. Os commits das linhas 888/911 só ocorrem no caminho
  `pending_input`.

Ou seja: num lote de N PDFs sem pendências, as N NFs ficam penduradas numa só
transação não-confirmada até o fim.

## Mecanismo

1. Quando `Session.flush()` levanta erro de banco (`IntegrityError` — caso do
   `NotNullViolation`), o SQLAlchemy **desativa a transação**. A sessão entra
   em estado "doomed": qualquer uso seguinte que precise da transação (outro
   `flush()`, `commit()` ou até um `SELECT`) levanta `PendingRollbackError`,
   até que se faça um `rollback()` explícito. (Comportamento padrão e estável
   do SQLAlchemy 1.4 e 2.0.)

2. O `except Exception` da **linha 1054** captura o `IntegrityError`. Ele:
   - faz `record.status = "erro_parsing"` etc. — apenas atribuições de atributo
     em objeto Python na identity map; não tocam o banco;
   - emite SSE `file_done` com `status: "erro_parsing"`;
   - **não faz `db.rollback()`**. A sessão segue envenenada.

3. O loop continua. Em qualquer subcaso a falha sobe para o `except` externo:
   - **NF malformada não é a última:** a próxima iteração executa o `SELECT` de
     dedup por SHA256 (`server.py:809`) → `PendingRollbackError`. Isso ocorre
     *fora* do `try` interno (que começa em 862) → sobe para o `except` da 1074.
   - **NF malformada é a última:** o loop acaba e `db.commit()` (1071) →
     `PendingRollbackError` → `except` da 1074.

4. O `except` externo (`server.py:1074-1076`) faz `db.rollback()` + emite SSE
   `error`.

## Consequência

O `db.rollback()` da linha 1075 descarta **tudo que foi `flush()`ado na
transação do lote e não foi commitado** — e no caminho normal nada é commitado
antes da 1071. Caem juntos:

- o `UploadBatch`;
- **todos** os `UploadFileRecord`, inclusive os marcados `processado`;
- **todas** as `NfEntry` dos arquivos anteriores bem-sucedidos;
- a própria marcação `erro_parsing` da NF que falhou.

Resultado: **um PDF malformado descarta o lote inteiro**, e o descompasso com o
SSE (que já emitiu os eventos de sucesso antes do rollback) torna a perda
silenciosa — o operador acredita que o upload deu certo.

> Atenuação parcial: se o lote passou por um checkpoint de pendência F8b
> (commits 888/911) **antes** da NF malformada, o trabalho anterior àquele
> checkpoint sobrevive. O estrago depende de ter havido pendência no lote.

## Por que o `except` da 1054 está errado para este caso

Esse handler foi desenhado para **degradação graciosa por arquivo** — válida
apenas para erros que ocorrem **antes de o banco ser tocado** (falha ao
consolidar o `outcome` do parser, `build_business_key`, etc.). São erros
puro-Python; a sessão segue sã e pular o arquivo é legítimo. O comentário da
linha 1059 (`"Erro ao consolidar o retorno do parser."`) revela esse modelo
mental — não previa que **o próprio INSERT falhasse**.

Um `NotNullViolation` nasce **dentro do `db.flush()`** — erro da camada de
banco, que envenena a sessão. O mesmo `except` captura os dois tipos de erro e
só trata um corretamente.

O `except` da linha **1217** (caminho `/resolve` do F8b) repete o padrão
`create_nf_entry` + `except` sem rollback. Como cada `/resolve` usa sessão
própria por request, o estrago ali é menor (só aquele resolve falha), mas
merece a mesma revisão.

## Resolução (2026-05-19)

Adotada a abordagem do **SAVEPOINT por arquivo** — isola a falha sem perder
o resto do lote.

### O que mudou

**`backend/app/server.py`**, no generator do `POST /api/uploads`:

- O loop de inserção das linhas de cada PDF foi envolvido em
  `with db.begin_nested():` (SAVEPOINT). Se um `flush()` falha lá dentro
  (`NotNullViolation`, `UniqueViolation`, etc.), o `__exit__` do
  `begin_nested` faz `ROLLBACK TO SAVEPOINT` — desfaz **só as linhas deste
  arquivo** — e a transação externa **continua viva**. A Session não é mais
  envenenada.
- O `except` per-file (bloco `erro_parsing`) ganhou comentário explicando
  que a Session segue utilizável graças ao SAVEPOINT, e passou a dar
  `status_reason` específico para `NfRowValidationError` (ver doc irmão).
- O loop então segue para o próximo PDF normalmente, e o `db.commit()` final
  (linha ~1071) **persiste os arquivos bem-sucedidos do lote**.

Esquema:

```python
with db.begin_nested():          # SAVEPOINT por arquivo
    for row in outcome.rows:
        ...
        create_nf_entry(db, row, ...)   # flush pode falhar aqui
# falhou → ROLLBACK TO SAVEPOINT, exceção sobe pro except per-file,
#          Session viva, loop continua
```

Funciona tanto no Postgres quanto no SQLite dos testes (ambos suportam
SAVEPOINT; o `begin_nested` do SQLAlchemy emite o comando em ambos).

**`/resolve` (F8b):** o `except` em torno do `create_nf_entry`
(`server.py` ~1242) ganhou um `db.rollback()` antes de levantar o
`HTTP 422` — recupera a Session caso o erro tenha vindo de um `flush()`. A
pendência permanece `aguardando` (nada commitado), liberando retry. Não é
catastrófico como o lote (cada `/resolve` usa Session própria por request),
mas o rollback torna o estado explícito.

### Por que SAVEPOINT e não "commit por arquivo"

Commit por arquivo também resolveria a perda do lote, mas quebraria a
atomicidade desejável de um batch e multiplicaria I/O de commit em lotes de
até 550 PDFs. O SAVEPOINT mantém um único commit no fim, com isolamento por
arquivo — melhor dos dois.

### Cobertura de teste

`backend/tests/test_upload_row_validation.py::test_batch_survives_db_error_in_one_file`
— lote de 2 PDFs; o 2º dispara `IntegrityError` real no `flush` (fornecedor
vazio → `NOT NULL`). Verifica: a `NfEntry` do 1º arquivo **é persistida**, o
1º vira `processado`, o 2º vira `erro_parsing`, o SSE não emite `error` e
emite `batch_done`. Antes do fix este teste falharia — o lote inteiro seria
descartado.

### Pendência conhecida (não corrigida aqui)

O descompasso "SSE promete antes do commit" continua: os eventos `file_done`
de sucesso são emitidos durante o loop, antes do `db.commit()` final. Com o
SAVEPOINT, um erro de banco isolado não derruba mais o lote, então a janela
de inconsistência encolheu muito — mas uma falha no **próprio
`db.commit()`** final (ex.: perda de conexão) ainda emitiria sucessos que
não persistiram. Corrigir exigiria reordenar o SSE para depois do commit, ou
commit incremental. Deixado como melhoria futura.

### Se o erro reaparecer

- "Lote inteiro sumiu após 1 arquivo com erro" **não deveria mais ocorrer**.
  Se ocorrer, verificar se o `with db.begin_nested()` ainda envolve o loop de
  inserção e se algum `db.flush()`/`db.scalar()` foi movido para **fora** do
  SAVEPOINT (uso da Session entre o flush que falhou e o rollback reenvenena).
- `PendingRollbackError` no log do upload = a Session foi usada sem rollback
  após um erro de banco — procurar um caminho de erro novo que escape do
  SAVEPOINT.
