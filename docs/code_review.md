# Code Review — `recebimento_notas`

> Revisão realizada em: 2026-04-01  
> Modelo: Claude Sonnet 4.6

---

## Visão Geral do Projeto

Aplicação MVP para recebimento, parseamento e armazenamento de Notas Fiscais brasileiras. O usuário faz upload de PDFs, o backend os processa via um script legado Python, extrai dados estruturados, deduplica e persiste em PostgreSQL. O frontend React exibe os registros e permite exportação para Excel.

**Stack:** FastAPI + SQLAlchemy + PostgreSQL / React 19 + Vite / pdfplumber + Tesseract OCR

---

## 1. Segurança (Crítico e Alto)

### 1.1 Credenciais hardcoded em código de produção — CRÍTICO

**Arquivo:** `backend/app/main.py` linhas 36–38

```python
SESSION_SECRET = os.getenv("SESSION_SECRET", "recebedor-nfs-dev-secret")
AUTH_USERNAME = "user"
AUTH_PASSWORD = "password"
```

- `AUTH_USERNAME` e `AUTH_PASSWORD` são literais hardcoded sem nenhum caminho de override via variável de ambiente.
- `SESSION_SECRET` tem um default fraco que qualquer atacante conhece.
- A autenticação compara strings em texto plano — sem hashing.

**Correção:**
```python
SESSION_SECRET = os.environ["SESSION_SECRET"]  # obrigatório, sem default
AUTH_USERNAME = os.environ["AUTH_USERNAME"]
AUTH_PASSWORD = os.environ["AUTH_PASSWORD"]     # armazenar hash bcrypt
```
O campo `password_hash` já existe em `User` mas nunca é usado. A autenticação deveria verificar via `bcrypt.checkpw()` contra esse campo.

---

### 1.2 `https_only=False` no `SessionMiddleware` — ALTO

**Arquivo:** `backend/app/main.py` linha 170

```python
https_only=False,
```

Cookies de sessão trafegam em HTTP sem proteção. Quando o app for implantado (o `proximos_passos.txt` cita Hostinger), sessões estarão vulneráveis a hijacking.

**Correção:** Definir via env var: `https_only=os.getenv("HTTPS_ONLY", "false").lower() == "true"` e ativar em produção.

---

### 1.3 Sem validação de conteúdo do arquivo — ALTO

**Arquivo:** `backend/app/main.py` linhas 270–291

O código verifica apenas `filename.lower().endswith(".pdf")`. Um arquivo malicioso com extensão `.pdf` mas conteúdo arbitrário passa essa verificação, é salvo em disco e processado.

**Correção:** Verificar os magic bytes do arquivo:
```python
header = await file.read(5)
if header != b"%PDF-":
    raise HTTPException(400, "Arquivo inválido: não é um PDF.")
await file.seek(0)
```

---

### 1.4 Sem limite de tamanho de upload — ALTO

Não há limite de `Content-Length`, tamanho máximo por arquivo ou por batch. Um PDF muito grande (ou muitos PDFs) pode esgotar memória ou disco antes de qualquer guarda atuar.

**Correção:** Adicionar limite via `UploadFile` ou middleware:
```python
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
if file.size and file.size > MAX_FILE_SIZE:
    raise HTTPException(413, "Arquivo muito grande.")
```

---

### 1.5 Caminhos do filesystem expostos ao browser — MÉDIO

**Arquivo:** `backend/app/main.py`

A resposta do upload inclui `saved_path` (caminho absoluto no servidor, ex.: `C:\...\banco_de_nf\<uuid>\nota.pdf`) e `debug_dir`, enviados diretamente ao frontend e renderizados na UI. Isso expõe o layout do filesystem do host a usuários autenticados.

**Correção:** Remover esses campos da resposta ou substituí-los por IDs opacos.

---

### 1.6 `requests.get` sem timeout na consulta de CNPJ — MÉDIO

**Arquivo:** `backend/app/main_v9.py`

```python
response = requests.get(url)  # sem timeout
```

Se a API `open.cnpja.com` estiver lenta ou indisponível, o request de upload trava indefinidamente. A função também escreve em `cnpj.json` no disco sincronamente durante o handling do request.

**Correção:**
```python
response = requests.get(url, timeout=10)
```

---

### 1.7 Artefatos de debug gravados em disco sem limpeza — BAIXO

**Arquivo:** `backend/app/parser_adapter.py`

Arquivos `stdout.txt`, `stderr.txt` e planilhas intermediárias são salvos em `parser_debug/<uuid>/` sem nenhum mecanismo de rotação ou limpeza. Com uso contínuo, o diretório cresce indefinidamente.

**Correção:** Adicionar limpeza automática ou mover para um diretório com TTL gerenciado (ex.: `tempfile.TemporaryDirectory()`).

---

## 2. Bugs e Correção

### 2.1 `consulta_nome_fornecedor` retorna string em vez de dict no erro — ALTO

**Arquivo:** `backend/app/main_v9.py` linhas 1055–1060

```python
elif response.status_code == 429:
    return "Erro: Limite de requisições atingido (max 5 por minuto)."
else:
    return f"Erro na consulta: Status {response.status_code}"
except Exception as e:
    return f"Ocorreu um erro: {e}"
```

O caminho feliz retorna `{'fornecedor': nome_empresa}` (dict). Os caminhos de erro retornam uma string pura. Downstream, `consolidate_data_to_dict` faz `if key in arg` iterando como se fosse dict — com uma string, isso vira busca caractere a caractere, produzindo dados errados silenciosamente.

**Correção:**
```python
except Exception as e:
    return {'fornecedor': None, 'error': str(e)}
```
E tratar `None` no downstream.

---

### 2.2 `product_or_service` retorna `ValueError` em vez de lançar — ALTO

**Arquivo:** `backend/app/main_v9.py` linha 1167

```python
return ValueError('Não chegou df até product_or_service' ...)
```

O código **retorna** o objeto exceção em vez de **lançá-lo**. O chamador recebe o `ValueError` como se fosse o valor de `invoice_type` e tenta comparar com `"product"` ou `"service"`, causando falhas confusas.

**Correção:**
```python
raise ValueError('Não chegou df até product_or_service' ...)
```

---

### 2.3 `cnpj_invoice` retorna `None` silenciosamente — ALTO

**Arquivo:** `backend/app/main_v9.py` linhas 979–982

Se todos os CNPJs encontrados estiverem na blocklist, a função cai fora do loop sem retornar nada (retorna `None` implícito). O chamador faz `cnpj_fornecedor['cnpj']`, que lança `TypeError: 'NoneType' object is not subscriptable`.

**Correção:**
```python
raise ValueError(f"Todos os CNPJs encontrados estão bloqueados: {lista_cnpjs}")
```

---

### 2.4 `CONTRATO` hardcoded de forma diferente em dois arquivos — ALTO

**Arquivo:** `backend/app/main_v9.py` linha 76 vs `backend/app/ocr_reader.py` linha 48

```python
# main_v9.py
CONTRATO = {'contrato':'ECM-023-2025'}

# ocr_reader.py
CONTRATO = {'contrato':'ECM/016-2025'}
```

São números de contrato diferentes. O fallback OCR produzirá metadados de contrato diferentes do parser principal. Isso é um defeito de qualidade de dados.

**Correção:** Definir `CONTRATO` em um único lugar (ex.: variável de ambiente ou arquivo de configuração) e importar nos dois módulos.

---

### 2.5 `num_nf` pode retornar uma lista em vez de um único valor — MÉDIO

**Arquivo:** `backend/app/main_v9.py` linha 1150

```python
return {'numero_nf': numeros_unicos}
```

Quando mais de um candidato é encontrado, `numero_nf` vira uma lista Python. Em `normalization.py`, `normalize_text(row.get("numero_nf"))` converte a lista para sua representação em string (`"['123', '456']"`), persistindo dados inválidos no banco.

**Correção:** Decidir explicitamente qual número priorizar (primeiro, o mais frequente, ou lançar erro) e garantir que o retorno seja sempre uma string.

---

### 2.6 Timer de progresso configurado após o upload resolver — BAIXO

**Arquivo:** `frontend/src/App.jsx` linhas 458–469

`processingTimer` é definido depois que `uploadFilesWithProgress` já resolveu. O intervalo que simula progresso de processamento começa após o backend já ter respondido — a animação de "78% processando" nunca é visível ao usuário.

**Correção:** Iniciar o timer imediatamente após o início do upload, antes de aguardar a resposta.

---

### 2.7 File handle não fechado em `ocr_reader.py` — BAIXO

**Arquivo:** `backend/app/ocr_reader.py` linha 352

```python
open(salvar_texto_em, "w", encoding="utf-8").write(texto)
```

O handle não é atribuído nem fechado. O GC do Python fecha eventualmente, mas gera `ResourceWarning` em testes e pode causar perda de dados em ambientes com flush lento.

**Correção:**
```python
with open(salvar_texto_em, "w", encoding="utf-8") as f:
    f.write(texto)
```

---

### 2.8 `date_invoice` pode lançar `IndexError` — MÉDIO

**Arquivo:** `backend/app/main_v9.py` linha 1072

```python
return {'data_emissao': data.iloc[0]['text']}
```

Se `data` estiver vazio, `iloc[0]` lança `IndexError` sem mensagem de contexto.

**Correção:**
```python
if data.empty:
    raise ValueError("Data de emissão não encontrada na NF.")
return {'data_emissao': data.iloc[0]['text']}
```

---

### 2.9 `refreshEntries` sem tratamento de erro — BAIXO

**Arquivo:** `frontend/src/App.jsx` linhas 322–337

A função é `async` e chama `fetch` mas não tem `try/catch`. Se a requisição falhar após um upload bem-sucedido, o erro é silenciosamente engolido e a tabela não é atualizada.

**Correção:**
```javascript
try {
  const resp = await fetch("/nf-entries", { credentials: "include" });
  if (!resp.ok) throw new Error(resp.statusText);
  setEntries(await resp.json());
} catch (err) {
  console.error("Falha ao atualizar entradas:", err);
  // exibir toast/alerta para o usuário
}
```

---

## 3. Performance

### 3.1 Subprocess por PDF é muito lento — MÉDIO

**Arquivo:** `backend/app/parser_adapter.py`

Cada PDF inicia um novo subprocess Python que importa pandas, numpy, pdfplumber, pytesseract, requests, tqdm, etc. Para um batch de 10 PDFs, são 10 subprocesses sequenciais com timeout de até 180s cada.

**Sugestão a longo prazo:** Refatorar `main_v9.py` com um guard `if __name__ == "__main__":` e remover os side-effects de import, permitindo importação direta como biblioteca. Isso eliminaria o overhead de cold-start.

---

### 3.2 Endpoint `nf-entries` sem paginação — MÉDIO

**Arquivo:** `backend/app/main.py` linha 217

```python
entries = db.scalars(select(NfEntry).order_by(NfEntry.created_at.desc())).all()
```

Sem `LIMIT`/`OFFSET`, uma base de dados grande retorna todas as linhas em uma única resposta, consumindo memória e banda.

**Correção:** Adicionar parâmetros `page` e `page_size`:
```python
entries = db.scalars(
    select(NfEntry).order_by(NfEntry.created_at.desc())
    .limit(page_size).offset(page * page_size)
).all()
```

---

### 3.3 `get_sessionmaker()` não é thread-safe — BAIXO

**Arquivo:** `backend/app/db.py` linhas 39–44

O check `if _sessionmaker is None` em código assíncrono concorrente pode construir dois session factories brevemente. SQLAlchemy é resiliente a isso, mas o padrão é frágil. Usar `threading.Lock` ou inicializar na startup do app via `lifespan`.

---

## 4. Qualidade de Código

### 4.1 Lixo de encoding em `main_v9.py` e `ocr_reader.py`

Sequências como `Ã£`, `Ã©`, `Ã‡`, `Ã¢` aparecem em comentários e strings ao longo de ambos os arquivos — são bytes UTF-8 interpretados como Latin-1 durante alguma edição. Prejudica muito a legibilidade.

**Correção:** Reabrir os arquivos com encoding UTF-8 e corrigir os caracteres corrompidos.

---

### 4.2 Global de debug `arquivo_investigado` em produção

**Arquivo:** `backend/app/main_v9.py` linha 29

```python
arquivo_investigado = '459_HEADS PROPAGAND'
```

Variável de debug com um nome de arquivo real deixada no escopo do módulo. Blocos comentados `if arquivo_investigado in nome_saida:` ao longo do arquivo atestam um workflow de debug que nunca foi limpo.

**Correção:** Remover a variável e todos os blocos comentados relacionados.

---

### 4.3 Typos consistentes que funcionam por acidente

| Local | Typo | Correto |
|---|---|---|
| `main_v9.py` + `parser_adapter.py` | `movivo` | `motivo` |
| `main_v9.py` | `unindentfied` | `unidentified` |
| `main_v9.py` | `get_real_transations` | `get_real_transactions` |
| `main_v9.py` | `tipo_nota_fical` | `tipo_nota_fiscal` |
| `main_v9.py` | `normatize_produt_classes` | `normalize_product_classes` |
| `ocr_reader.py` | `POPLLER_PATH` | `POPPLER_PATH` |

O par `movivo`/`movivo` é especialmente perigoso: se um dia normalizar a chave em `main_v9.py` mas não em `parser_adapter.py` (ou vice-versa), a extração falha silenciosamente.

---

### 4.4 `main_v9.py` sem guard `if __name__ == "__main__":`

O loop principal de processamento (linhas 1277–1496) e o `df.to_excel(...)` final executam no nível do módulo sem nenhum guard. Qualquer `import main_v9` acidental executaria o parser inteiro. O arquivo também inicializa `log.json` vazio na linha 61 ao ser importado, destruindo silenciosamente um log existente.

**Correção:** Envolver todo o código de execução:
```python
if __name__ == "__main__":
    # loop principal
    # df_anexo1_consolidado.to_excel(...)
```

---

### 4.5 `App.jsx` monolítico com 780 linhas — BAIXO

Todo o state, effects, handlers e rendering estão em um único componente. A lógica de progresso de upload, formulário de login, tabela de NFs e painel de status de arquivos estão todos entrelaçados.

**Sugestão:** Decompor em componentes menores: `<LoginForm>`, `<UploadPanel>`, `<NfTable>`, `<FileStatusList>`. Isso facilita manutenção e testes futuros.

---

### 4.6 `NfEntryResponse` com tipos excessivamente permissivos

**Arquivo:** `backend/app/main.py` linhas 46–59

Todos os campos são tipados como `str | int | float | None`. Isso anula qualquer benefício de validação do Pydantic. Os tipos reais são conhecidos e deveriam ser declarados explicitamente (ex.: `data_emissao: date | None`, `valor_total: Decimal | None`).

---

## 5. Tabela de Prioridades

| Prioridade | Arquivo | Problema |
|---|---|---|
| **Crítico** | `main.py` | Credenciais hardcoded (`user`/`password`), sem hashing |
| **Crítico** | `main.py` | Session secret com default fraco hardcoded |
| **Alto** | `main.py` | `https_only=False` nos cookies de sessão |
| **Alto** | `main.py` | Sem validação de conteúdo do arquivo (apenas extensão) |
| **Alto** | `main.py` | Sem limite de tamanho de upload |
| **Alto** | `main_v9.py` | `consulta_nome_fornecedor` retorna string em vez de dict no erro |
| **Alto** | `main_v9.py` | `product_or_service` retorna `ValueError` em vez de lançar |
| **Alto** | `main_v9.py` | `cnpj_invoice` retorna `None` silenciosamente |
| **Alto** | `main_v9.py` vs `ocr_reader.py` | `CONTRATO` hardcoded diferente nos dois arquivos |
| **Médio** | `main.py` | Caminhos do filesystem expostos ao browser |
| **Médio** | `main_v9.py` | `requests.get` sem timeout; escreve `cnpj.json` no request path |
| **Médio** | `main_v9.py` | `num_nf` pode retornar lista, persistida como string inválida |
| **Médio** | `main_v9.py` | `date_invoice` lança `IndexError` sem contexto se data não encontrada |
| **Médio** | `main.py` | Sem paginação no endpoint `nf-entries` |
| **Baixo** | `parser_adapter.py` | Typo `"movivo"` na chave do log (funciona por acidente) |
| **Baixo** | `ocr_reader.py` | File handle não fechado em `open(...).write(...)` |
| **Baixo** | `main_v9.py` | Encoding corrompido em comentários e strings |
| **Baixo** | `main_v9.py` | Variável de debug `arquivo_investigado` em produção |
| **Baixo** | `main_v9.py` | Sem guard `if __name__ == "__main__":` |
| **Baixo** | `App.jsx` | `refreshEntries` sem tratamento de erro |
| **Baixo** | `App.jsx` | Timer de animação configurado após resposta (animação nunca visível) |
| **Baixo** | `App.jsx` | Componente monolítico de 780 linhas |
