# FRONTEND.md

Documentação de design e decisões técnicas do frontend do **GFIP — Recebimento de Notas Fiscais**.

Arquivos relevantes: `frontend/src/App.jsx`, `frontend/src/styles.css`.

---

## Identidade visual

### Referência

O design segue a identidade visual institucional do governo federal brasileiro, tendo como referência direta o site **www.enbpar.gov.br** (Empresa de Navegação da Bacia do Prata).

### Paleta de cores (CSS variables)

```css
--blue:          #1b80c4;   /* accent principal — ENBPar blue */
--blue-dark:     #1565a0;   /* hover/borda do botão primário */
--blue-hover:    #1672b0;   /* estado hover do btn-primary */
--navy:          #0d3558;   /* topbar + footer (institucional escuro) */
--text-primary:  #1e293b;   /* texto principal */
--text-secondary:#4a5568;   /* texto secundário / labels */
--text-muted:    #94a3b8;   /* texto desabilitado / contagens */
--bg:            #f0f4f8;   /* background da página (azul-cinza claro) */
--bg-card:       #ffffff;   /* fundo dos cards */
--border:        rgba(0,0,0,0.1);
--border-light:  #e2e8f0;   /* bordas de cards e inputs */
--shadow:        0 2px 8px rgba(0,0,0,0.08);
--shadow-md:     0 4px 16px rgba(0,0,0,0.10);
--radius:        6px;        /* cards, dropzone */
--radius-sm:     4px;        /* botões, inputs, badges */
--topbar-h:      52px;
```

### O que foi removido da paleta anterior

A versão anterior usava uma paleta quente beige/terracota com glassmorphism. Tudo isso foi substituído:

| Antes | Depois |
|---|---|
| `--terracotta: #b85635` | `--blue: #1b80c4` |
| Backgrounds beige / warm | `#f0f4f8` (azul-cinza frio) |
| `backdrop-filter: blur(...)` | Removido completamente |
| Gradientes radiais decorativos | Removidos |
| `border-radius` 20px+ | Máximo 6px |
| Lora (serif) + DM Sans | Open Sans (governo) |

---

## Tipografia

- **Fonte**: Open Sans, importada do Google Fonts:
  ```css
  @import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap');
  ```
- **Base**: 14px, `line-height` padrão do browser
- **Hierarquia**:
  - Títulos de card: `1.05rem`, `font-weight: 700`, `color: var(--text-primary)`
  - Kickers (labels uppercase acima do título): `0.68rem`, `letter-spacing: 0.14em`, `color: var(--blue)`
  - Labels de campo: `0.8rem`, uppercase, `font-weight: 600`
  - Texto de tabela: `0.82rem`
  - Badges: `0.7rem`, uppercase, `letter-spacing: 0.02em`

---

## Estrutura de layout

```
.app-shell (flex column, min-height 100vh)
  ├── .topbar (sticky, height 52px)
  ├── .main-content (flex column, max-width 1200px, centralizado)
  │     ├── .upload-row (grid 1 col → 2 cols quando há resultados)
  │     │     ├── .card.upload-card
  │     │     └── .card.results-card (condicional)
  │     └── .card.table-card
  └── .app-footer
```

### Topbar

- `background: var(--navy)` — navy escuro institucional
- `border-bottom: 3px solid var(--blue)` — accent azul ENBPar
- Altura fixa `52px`, `position: sticky; top: 0; z-index: 100`
- Brand text: uppercase, branco, `font-weight: 700`
- Logout: botão transparente com `border: 1px solid rgba(255,255,255,0.3)` — discreto no fundo escuro

### Cards

- `background: #ffffff`
- `border: 1px solid var(--border-light)`
- `border-radius: var(--radius)` (6px)
- `box-shadow: var(--shadow)`
- Padding: `20px 22px`

### Auth card

- Mesmo padrão de card, mas com `border-top: 3px solid var(--blue)` como accent institucional
- Centralizado na tela via `display: grid; place-items: center`
- Largura máxima `420px`

### Footer

- `background: var(--navy)` — espelha o topbar (efeito "moldura institucional")
- Texto `#94a3b8` — discreto sobre o fundo escuro
- Duas colunas com `justify-content: space-between`

---

## Componentes

### Botões

**`.btn-primary`**
- `background: var(--blue)`, texto branco, `border: 1px solid var(--blue-dark)`
- `border-radius: var(--radius-sm)` (4px — estilo institucional quadrado)
- Hover: `background: var(--blue-hover)` + sombra azul sutil

**`.btn-ghost`**
- `background: #ffffff`, `border: 1px solid #cbd5e1`, texto `var(--text-primary)`
- Hover: borda e texto mudam para `var(--blue)`

**`.topbar-logout`**
- Transparente, borda e texto brancos (`rgba(255,255,255,...)`)
- Não usa `btn-primary` para não conflitar com o fundo escuro do topbar

### Status badges (`.status-badge`)

Badges de status com semântica de cores Tailwind-inspired, `border-radius: 3px`:

| Classe | Background | Texto | Borda | Uso |
|---|---|---|---|---|
| `.status-na-fila` | `#f8fafc` | `var(--text-muted)` | `var(--border-light)` | Arquivo aguardando envio |
| `.status-salvo` | `#eff8ff` | `var(--blue-dark)` | `#93c5fd` | PDF salvo em disco |
| `.status-processando` | `#fefce8` | `#a16207` | `#fde047` | Parser em execução (+ `badge-pulse`) |
| `.status-processado` | `#dcfce7` | `#15803d` | `#86efac` | Inserido com sucesso |
| `.status-duplicado` | `#fef9c3` | `#854d0e` | `#fde047` | Todas as linhas já existiam |
| `.status-rejeitado` | `#fff7ed` | `#c2410c` | `#fdba74` | Arquivo rejeitado (ex: não é PDF) |
| `.status-erro-parsing` | `#fef2f2` | `#b91c1c` | `#fca5a5` | Falha no parser |
| `.status-erro-upload` | `#fef2f2` | `#b91c1c` | `#fca5a5` | Falha no envio |

O CSS class slug é derivado via `.replace(/_/g, "-")` no `StatusBadge`:
```jsx
function StatusBadge({ status }) {
  const slug = status.replace(/_/g, "-");
  return <span className={`status-badge status-${slug}`}>{STATUS_LABELS[status] ?? status}</span>;
}
```

### Dropzone

- `border: 1.5px dashed #93c5fd` — azul claro
- `background: #f8fbff`
- Hover: borda `var(--blue)`, fundo `#eff8ff`
- Input `display: none` (clique via `<label htmlFor>`)

### Barra de progresso

Três fases com indicadores textuais (① Envio / ② Processamento / ③ Tabela):

```
Phase idle    → .phase-idle   (--text-muted, opacity 0.55)
Phase active  → .phase-active (--blue)
Phase done    → .phase-done   (#16a34a — verde)
```

A barra em si (`.progress-fill`):
- Cor: `var(--blue)`, transição `width 200ms ease`
- Durante processamento: animation `progress-wave` (gradiente animado azul escuro/claro)

**Pesos das fases**:
- Fase 1 (upload/save): 5% → 60%, proporcional a `savedCount / totalFiles`
- Fase 2 (processing): 62% → 83%, proporcional a `doneCount / totalFiles`
- Fase 3 (refresh tabela): 87% → 100%

### Tabela de NFs

**Problema resolvido: header quebrando sobre as linhas**

`position: sticky` em `<th>` dentro de container `overflow-x: auto` não funciona corretamente — o elemento se posiciona relativo ao scroll container, não ao viewport, causando sobreposição visual com as linhas de dados.

**Solução**: remover `position: sticky` e `z-index` do `th`. Usar fundo opaco no header como substituto visual:
```css
th {
  background: #e8edf3;        /* fundo opaco — sem sticky */
  border-bottom: 2px solid #cbd5e1;
  white-space: nowrap;
}
```

**Problema resolvido: células quebrando o layout**

Células longas quebravam o layout ou expandiam colunas indefinidamente.

**Solução**: `table-layout: fixed` + `<colgroup>` com larguras explícitas + CSS nas células:
```css
table { table-layout: fixed; }

td {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: keep-all;
}
```

**Larguras das colunas** (ordem do parser):

| Coluna CSS | Largura | Campo |
|---|---|---|
| `.col-descricao` | 230px | Descrição do item |
| `.col-ncm` | 76px | NCM |
| `.col-quant` | 58px | Quantidade |
| `.col-preco` | 100px | Preço unitário |
| `.col-nf` | 72px | Número da NF |
| `.col-tipo` | 70px | Tipo de nota |
| `.col-data` | 90px | Data de emissão |
| `.col-cnpj` | 132px | CNPJ |
| `.col-fornecedor` | 160px | Fornecedor |
| `.col-valor` | 90px | Valor total |
| `.col-contrato` | 88px | Contrato |

O `title` em cada `<td>` mostra o valor completo no tooltip nativo do browser.

---

## Progresso por arquivo em tempo real (SSE)

### Problema

O endpoint original retornava um JSON único após processar todos os arquivos. O painel de status mostrava todos os arquivos com "Enviando…" simultaneamente até a resposta final chegar.

### Solução: Server-Sent Events via `fetch` + `ReadableStream`

O `EventSource` nativo não suporta POST. A solução é consumir o stream manualmente:

```javascript
async function uploadWithSSE(files, onEvent) {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  const response = await fetch("/api/uploads", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop(); // fragmento incompleto aguarda próximo chunk

    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) {
        try { onEvent(JSON.parse(line.slice(6))); } catch { }
      }
    }
  }
}
```

**Por que o buffer com `split("\n\n")` e `pop()`**: chunks TCP podem chegar fragmentados. O `pop()` retém o fragmento incompleto e o concatena com o próximo chunk recebido.

### Mapeamento de eventos SSE para status no painel

```javascript
const SSE_STATUS_MAP = {
  file_queued:  "na_fila",
  file_saved:   "salvo",
  file_parsing: "processando",
};
```

Eventos `file_done` e `batch_done` são tratados separadamente (atualizam o status final + contagens).

### Atualização de estado por arquivo sem substituir o array

```javascript
setUploadState((current) => ({
  ...current,
  results: current.results.map((r) =>
    r.filename === event.filename ? { ...r, status: newStatus } : r
  ),
}));
```

O `filename` é a chave de identificação — garante que apenas o arquivo correto avança de estado.

---

## Responsividade

- `< 800px`: painel de upload e resultados ficam empilhados (grid 1 coluna); `topbar-user` some; padding reduzido
- `< 480px`: footer em coluna única; botões do header da tabela quebram linha
- Tabela: `overflow-x: auto` no `.table-wrapper` — scroll horizontal em telas estreitas

---

## Dependências do frontend

| Pacote | Uso |
|---|---|
| `react` + `react-dom` | SPA |
| `vite` | Build + dev server |
| `xlsx` | Export Excel (`exportEntriesToExcel`) |
| Google Fonts (CDN) | Open Sans |

O build emite os assets em `backend/app/static/`, servidos estaticamente pelo FastAPI.

---

## Telas e fluxos planejados (próximo ciclo — F1 a F8)

Esta seção descreve as telas que serão adicionadas. Os critérios de sucesso por feature vivem em `planning/PLAN.md`; aqui só o esqueleto de UX.

### F1 — Auth real (substitui credenciais fixas)

- Tela de **registro** (`/register`): campos `email` + `password`. Política mínima: senha ≥10 caracteres, sem regras de complexidade obrigatórias. Submissão chama `POST /api/auth/register`; após sucesso, mensagem "Verifique seu e-mail para confirmar".
- Tela de **confirmação** (`/auth/confirm?token=...`): consome `GET /api/auth/confirm?token=...`. Sucesso → redireciona para login. Token expirado → mensagem orientando re-registro.
- Tela de **login**: ajustar para usar `email` (não `username`). Mensagem específica para `email_confirmed=False` (403).
- Tela de **esqueci minha senha** (`/forgot-password`): campo `email`. Submissão chama `POST /api/auth/forgot-password`; sempre exibe "Se o e-mail existir, enviamos um link" (sem revelar se existe).
- Tela de **redefinir senha** (`/reset-password?token=...`): inputs `password` + `confirm_password`. `POST /api/auth/reset-password`.

### F2 — Seleção de contrato (entre login e upload)

- Após login bem-sucedido, frontend chama `GET /api/session/contrato`. Se 404, redireciona para `/contratos` (Decisão #9).
- Tela `/contratos` (seleção): lista filtravel de contratos (~140), busca por `numero` + `sigla`, filtros `uf`, `tipo_contrato` (LPT/MLA), `tranche`. Toggle "apenas com valor definido". Click em um contrato → `POST /api/session/contrato` → redireciona para upload.
- **Topbar passa a exibir o contrato ativo** (número + sigla) ao lado do nome do usuário. Click no contrato no topbar → volta à tela de seleção.

### F3 — Página de consulta de contratos

- Tela acessível via menu do topbar. Mesma fonte de dados do F2 (`GET /api/contratos?...`), mas **sem efeito de seleção** — só consulta.
- Tabela com colunas: Número, Fornecedor (sigla), UF, Tranche, Tipo, Valor Contrato, Valor CDE, % CDE.
- Tabela usa `table-layout: fixed` e ellipsis (mesmas regras da tabela de NFs).

### F4 — Visualizar/baixar PDF

- Coluna nova de **ação** na tabela de NFs: ícone "olho" (abre PDF inline em nova aba via `GET /api/uploads/files/{upload_file_id}/pdf`) e ícone "download" (`?download=true` força attachment com `original_filename`).
- Sem tela nova — só aumento da tabela existente.

### F5 — Limite de 550 PDFs/batch

- Ao selecionar arquivos, se `files.length > 550` → exibir alerta inline e desabilitar botão de envio.
- A validação canônica é do backend (`HTTP 422`). Frontend é só UX preventiva.

### F6 — Card de totalizadores no painel de upload

- Card no topo do painel de upload (antes da seleção de arquivos), exibindo para o contrato ativo:
  - Duas barras horizontais: "Enviado vs. Valor Contrato" e "Enviado vs. Valor CDE", em BRL e %.
  - Contagem de NFs distintas no banco para o contrato.
- Recarrega ao montar e após cada `batch_done` no SSE.
- Quando `valor_contrato = 0`: exibir "Valor contratual não definido" e ocultar a barra correspondente.

### F8 — Modal de preenchimento manual de campos faltando (Decisão #8 Tipo 1)

- Trigger: SSE event `file_pending_input` com `{nf_pending_id, prefilled_fields, missing_fields, original_filename}`.
- Modal abre **bloqueando o batch** — outros arquivos não começam a processar até resolver.
- Layout: título "Preencher campos faltando — `<filename>`"; lista de campos pré-preenchidos visíveis (read-only ou disabled, com indicação de origem); inputs obrigatórios para cada `missing_field` (cnpj, fornecedor, data_emissao, numero_nf, etc. — ver `planning/PLAN.md` Decisão #8 para a lista completa).
- **Validação no client**: nenhum campo pode ser submetido vazio. Botão "Salvar" disabled enquanto houver campo vazio.
- Submissão: `POST /api/uploads/pending/{nf_pending_id}/resolve` com `{cnpj: "...", ...}`. Sucesso → modal fecha, batch retoma.
- **Abandono**: usuário pode fechar modal/browser. Backend marca pendência como `abandonado` após timeout (definido em F8). NF não entra em `nf_entries`. Re-submissão dos PDFs deduplica via `business_key` automaticamente (sem rollback de linhas já inseridas).
- Link "Ver PDF original" no modal abre `GET /api/uploads/files/{upload_file_id}/pdf` em nova aba (depende de F4 estar ativo).

### Status badge novo (F8)

| Classe | Background | Texto | Borda | Uso |
|---|---|---|---|---|
| `.status-aguardando-preenchimento` | `#fef3c7` | `#92400e` | `#fcd34d` | Arquivo com 1+ NF em `nf_pending` |

Mantém o padrão de cores existente.

---

## Comportamento de redirect quando falta contrato (Decisão #9)

- Frontend **não confia em payload de redirect do backend**. Rotas são responsabilidade do frontend.
- Convenção: backend retorna `HTTP 400 {"detail": "Nenhum contrato selecionado."}` quando endpoint que exige contrato é chamado sem `contrato_id` na sessão.
- Frontend, no boot pós-login, chama `GET /api/session/contrato`. Se 404, renderiza `/contratos` (rota interna).
- O 400 do upload serve só como rede de segurança para bug/estado inconsistente.
