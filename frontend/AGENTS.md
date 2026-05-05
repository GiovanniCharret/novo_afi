# Frontend Notes

## Stack Atual

- React 19
- Vite 7
- JavaScript (sem TypeScript)

## Estrutura

- `src/main.jsx` — ponto de entrada do frontend.
- `src/App.jsx` — **SPA monolitica**: login, upload, tabela, status badges, SSE consumer. ~625 linhas. Toda logica de UI vive aqui.
- `src/styles.css` — estilos globais e layout (~15KB).
- `vite.config.js` — build emite `assets/app.js` + `assets/app.css` em `backend/app/static/`. Renomeia `style.css` para `app.css` via rollup.
- `package.json` — `npm run build` para producao.

## Estado entregue (MVP, Partes 1-7)

- Tela de login com credenciais ficticias (sera removida em F1).
- Upload em lote via `POST /api/uploads` com SSE para progresso por arquivo.
- Tabela persistida lida de `GET /api/nf-entries` com export para Excel via `xlsx`.
- Atualizacao automatica da tabela apos `batch_done`.
- Estados de carregamento, vazio e erro tratados.

## Limitacoes que serao resolvidas no proximo ciclo

- **Autenticacao ficticia** (`user`/`password`) — sera substituida em F1 por cadastro com e-mail + bcrypt + confirmacao por e-mail. Decisoes #1, #2, #5 ja resolvidas em `planning/PLAN.md`.
- **Sem selecao de contrato** — F2 introduz tela de selecao entre login e upload, e o `contrato_id` passa a viver na sessao. Decisao #9 define que o frontend faz o gating local (sem redirect prescrito pelo backend).
- **Sem visualizacao do PDF original** — F4 adiciona acao na linha da tabela.
- **Sem totalizadores graficos** — F6 adiciona card no painel de upload com barras "enviado vs. contrato" e "enviado vs. CDE".
- **Sem tratamento de campo faltando** — F8 introduz modal de preenchimento manual quando o parser nao consegue extrair campo obrigatorio (Decisao #8 Tipo 1). **Bloqueia o batch** ate o usuario preencher.

Detalhes de UX por feature em `docs/FRONTEND.md` -> "Telas e fluxos planejados".

## Padroes a manter no refactor

- **Nao quebrar a SPA monolitica sem decisao explicita.** Componentizacao maior pode acontecer mas e fora do escopo das 7 features.
- **`table-layout: fixed` + `<colgroup>` + ellipsis nas celulas.** Documentado em `docs/FRONTEND.md`. Nao usar `position: sticky` em `<th>` dentro de container `overflow-x: auto`.
- **SSE via `fetch` + `ReadableStream`.** O `EventSource` nativo nao suporta POST. Padrao em `App.jsx` ja resolvido.
- **Identidade visual institucional** (paleta navy/blue + Open Sans + `border-radius` <= 6px). Sem glassmorphism, sem gradientes decorativos. Ver `docs/FRONTEND.md`.

## Build

```powershell
cd frontend
npm install
npm run build
```

Mudancas em `frontend/src/` so aparecem apos `npm run build`. Backend roda com `--reload`, entao mudancas em Python recarregam automaticamente — frontend nao.
