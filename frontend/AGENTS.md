# Frontend Notes

## Stack Atual

- React 19
- Vite 7
- JavaScript (sem TypeScript)

## Estrutura

- `src/main.jsx` — ponto de entrada do frontend.
- `src/App.jsx` — **SPA cujo núcleo continua monolítico**: login, upload, tabela_persistida, status badges, SSE consumer. State `currentView ∈ {"upload","notas","contratos"}` comuta entre as três telas via links no topbar. Mantém Map `contratoSlices` para cache de sessão por contrato (F3-c, 2026-05-13).
- `src/components/`
  - `AuthScreen.jsx` *(F1, 2026-05-13/14)* — state machine com 7 sub-views: `login`, `register`, `confirm-needed`, `confirm-result`, `forgot`, `forgot-sent`, `reset`. Detecta `?confirm=X` / `?reset=X` na URL no mount. `IS_LOCAL_DEV` flag mostra hint discreta com `dev@local`/`password` quando hostname é `localhost`.
  - `ContratoSelector.jsx` *(F2)* — tela intermediária pós-login. Dois níveis: Estado → Contrato.
  - `NfsBrowser.jsx` *(F3b)* — aba "Notas". Dropdown de contrato + filtros + tabela + footer com soma BRL. Coluna PDF com botões 👁/⬇ (F4). Strip `TotalizadoresCard` entre filtros e tabela.
  - `ContratosBrowser.jsx` *(F3)* — aba "Contratos". Browser da base estática com filtros (`q`, UF, tipo, tranche, toggles). Clique em linha troca o contrato ativo e leva para Upload.
  - `TotalizadoresCard.jsx` *(F6, 2026-05-13)* — strip horizontal compacto com 3 colunas (NFs distintas | barra vs. contrato | barra vs. CDE). Usado dentro do NfsBrowser. Fetch único em `/api/contratos/{id}/totais`.
- `src/lib/`
  - `exportExcel.js` — 2 variantes: `exportEntriesCompletas` (Upload, 11 colunas) e `exportNfsResumo` (Notas, 7 colunas).
  - `describeContrato.js` — formato canônico `SIGLA · tranche · tipo (numero)` usado em topbar, dropdown Notas, tooltip Contratos.
  - `ufNomes.js` — mapa UF → nome completo + constantes `SEM_UF_KEY`/`SEM_UF_NOME`.
  - `parseBR.js` *(F6)* — converte string BR (`"1.234,56"`) para Number. Compartilhado entre NfsBrowser (soma footer) e App.jsx (rodapé Anexo I).
- `src/styles.css` — estilos globais e layout (~20KB após F3/F3b/F4).
- `vite.config.js` — build emite `assets/app.js` + `assets/index.css` em `backend/app/static/`.
- `package.json` — `npm run build` para produção.

## Estado entregue (MVP, Partes 1-7 + F1 ✅ + F2 ✅ + F3 ✅ + F3b ✅ + F4 ✅ + F5 ✅ + F6 ✅)

- Auth real via `AuthScreen.jsx`: cadastro, confirmação por e-mail, login, reset de senha. Em `APP_ENV=development`, seed automático `dev@local`/`password` agiliza smoke.
- ContratoSelector pós-login (2 níveis), com contrato ativo exibido no topbar no formato `SIGLA · tranche · tipo (numero)`.
- Upload em lote via `POST /api/uploads` com SSE; limite 550 PDFs/batch (F5).
- Aba Notas com filtros, soma BRL e botões 👁/⬇ para abrir/baixar PDF original (F4).
- Aba Contratos: browser filtrável da base estática; clicar em linha troca contrato ativo sem logout.
- Tabela_persistida da Upload filtra por contrato ativo (não mostra NFs de outros contratos).
- Mensagem de duplicidade na Upload menciona o contrato onde a NF já está arquivada.
- Cache de sessão por contrato: trocar contrato preserva o snapshot dos painéis; badge "Último upload {relativo}" sinaliza dados de jornada anterior. Logout zera tudo.
- Estados de carregamento, vazio e erro tratados em todas as telas.

## Limitações que serão resolvidas no próximo ciclo

- **Legacy NFs sem PDF clicável** (pré-F4) — limitação aceita (Decisão F4-d). Botões aparecem disabled com tooltip.
- **Sem e-mails transacionais de upload** — F7 vai adicionar envio de "upload concluído" para o usuário + alerta de `erro_parsing` para admin. Reusa `email_service.py` da F1.
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
