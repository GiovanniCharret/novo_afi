# Frontend Notes

## Stack Atual

- React 19
- Vite 7
- JavaScript (sem TypeScript)

## Estrutura

- `src/main.jsx` — ponto de entrada do frontend.
- `src/App.jsx` — **SPA cujo núcleo continua monolítico**: login, upload, tabela_persistida, status badges, SSE consumer. State `currentView ∈ {"upload","notas"}` comuta entre as duas telas via links no topbar.
- `src/components/`
  - `ContratoSelector.jsx` *(F2)* — tela intermediária pós-login. Dois níveis: Estado → Contrato.
  - `NfsBrowser.jsx` *(F3b)* — aba "Notas". Dropdown de contrato + filtros + tabela + footer com soma BRL. Coluna PDF com botões 👁/⬇ (F4).
- `src/lib/exportExcel.js` — 2 variantes: `exportEntriesCompletas` (Upload, 11 colunas) e `exportNfsResumo` (Notas, 7 colunas).
- `src/styles.css` — estilos globais e layout (~17KB).
- `vite.config.js` — build emite `assets/app.js` + `assets/index.css` em `backend/app/static/`.
- `package.json` — `npm run build` para produção.

## Estado entregue (MVP, Partes 1-7 + F2 ✅ + F3b ✅ + F4 ✅ + F5 ✅)

- Tela de login com credenciais fictícias (será removida em F1).
- ContratoSelector pós-login (2 níveis), com contrato ativo exibido no topbar.
- Upload em lote via `POST /api/uploads` com SSE; limite 550 PDFs/batch (F5).
- Aba Notas com filtros, soma BRL e botões 👁/⬇ para abrir/baixar PDF original (F4).
- Tabela_persistida da Upload filtra por contrato ativo (não mostra NFs de outros contratos).
- Mensagem de duplicidade na Upload menciona o contrato onde a NF já está arquivada.
- Estados de carregamento, vazio e erro tratados em ambas as telas.

## Limitações que serão resolvidas no próximo ciclo

- **Autenticação fictícia** (`user`/`password`) — F1 vai substituir por cadastro com e-mail + bcrypt + confirmação. Decisões #1, #2, #5 resolvidas em `planning/PLAN.md`.
- **Sem browser de contratos** — F3 vai adicionar aba/tela dedicada para consulta da base estática de contratos. Plano em `planning/F3-consulta-contratos.html`.
- **Sem totalizadores gráficos** — F6 vai adicionar card no painel de upload com barras "enviado vs. contrato" e "enviado vs. CDE". Plano em `planning/F6-totalizadores.html`.
- **Legacy NFs sem PDF clicável** (pré-F4) — limitação aceita (Decisão F4-d). Botões aparecem disabled com tooltip.
- **Sem tratamento de campo faltando** — F8b introduz modal de preenchimento manual quando o parser não consegue extrair campo obrigatório (Decisão #8 Tipo 1). **Bloqueia o batch** até o usuário preencher.

Detalhes de UX por feature em `docs/FRONTEND.md` -> "Telas e fluxos planejados".

## Padroes a manter no refactor

- **Núcleo de App.jsx continua monolítico**; componentização nova só para telas isoladas (ContratoSelector, NfsBrowser) ou utilidades (`lib/`). Não fragmentar sem decisão explícita.
- **`table-layout: fixed` + `<colgroup>` + ellipsis nas células.** Documentado em `docs/FRONTEND.md`. Não usar `position: sticky` em `<th>` dentro de container `overflow-x: auto`.
- **SSE via `fetch` + `ReadableStream`.** O `EventSource` nativo não suporta POST. Padrão em `App.jsx` já resolvido.
- **Endpoints filtrados via `AbortController` + debounce 300ms** para evitar rajada de requests enquanto o usuário digita (padrão em `NfsBrowser`).
- **Identidade visual institucional** (paleta navy/blue + Open Sans + `border-radius` <= 6px). Sem glassmorphism, sem gradientes decorativos. Ver `docs/FRONTEND.md`.

## Build

```powershell
cd frontend
npm install
npm run build
```

Mudancas em `frontend/src/` so aparecem apos `npm run build`. Backend roda com `--reload`, entao mudancas em Python recarregam automaticamente — frontend nao.
