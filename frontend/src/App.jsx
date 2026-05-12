import { useEffect, useState } from "react";

import ContratoSelector from "./components/ContratoSelector";
import NfsBrowser from "./components/NfsBrowser";
import { exportEntriesCompletas } from "./lib/exportExcel";

const defaultLoginForm = { username: "user", password: "password" };

// F5 — limite hard de PDFs por batch. Mantém em sincronia com backend
// (server.py: `if len(files) > 550: raise HTTPException(422, ...)`).
// Frontend é rede de segurança duplicada; backend é canônico.
const MAX_FILES_PER_BATCH = 550;

function formatSelectedFiles(files) {
  if (files.length === 0) return "Nenhum PDF selecionado.";
  if (files.length === 1) return files[0].name;
  return `${files.length} arquivos selecionados`;
}

const STATUS_LABELS = {
  // status de progresso (SSE)
  na_fila:     "Na fila",
  salvo:       "Salvo",
  processando: "Processando…",
  // status finais do backend
  processado:  "Processado",
  duplicado:   "Duplicado",
  rejeitado:   "Rejeitado",
  erro_parsing: "Erro de parsing",
  erro_upload:  "Erro de upload",
};

// Mapeamento evento SSE → status intermediário no painel
const SSE_STATUS_MAP = {
  file_queued:  "na_fila",
  file_saved:   "salvo",
  file_parsing: "processando",
};

function StatusBadge({ status }) {
  const slug = status.replace(/_/g, "-");
  return (
    <span className={`status-badge status-${slug}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export default function App() {
  const [authState, setAuthState] = useState({
    loading: true,
    isAuthenticated: false,
    user: null,
    error: "",
  });
  const [apiStatus, setApiStatus] = useState({
    loading: false,
    message: "Aguardando autenticacao.",
  });
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [entriesState, setEntriesState] = useState({
    loading: false,
    rows: [],
    error: "",
  });
  const [uploadState, setUploadState] = useState({
    submitting: false,
    results: [],
    batchId: null,
    progress: 0,
    phase: "idle",
    progressMessage: "",
  });
  const [loginForm, setLoginForm] = useState(defaultLoginForm);
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);
  // F2 — contrato selecionado na sessão. null = ainda não selecionou (boot ou pós-logout).
  // Após login, fetch GET /api/session/contrato decide entre ContratoSelector e área de upload.
  const [selectedContrato, setSelectedContrato] = useState(null);
  const [contratoBootChecked, setContratoBootChecked] = useState(false);
  // F3b — aba ativa na área logada: "upload" | "notas". "contratos" reservado para F3.
  const [currentView, setCurrentView] = useState("upload");

  useEffect(() => {
    let active = true;
    async function loadSession() {
      try {
        const response = await fetch("/api/auth/session", { credentials: "same-origin" });
        if (response.status === 401) {
          if (!active) return;
          setAuthState({ loading: false, isAuthenticated: false, user: null, error: "" });
          setApiStatus({ loading: false, message: "Aguardando autenticacao." });
          return;
        }
        const data = await response.json();
        if (!active) return;
        setAuthState({ loading: false, isAuthenticated: true, user: data.user, error: "" });
      } catch (error) {
        if (!active) return;
        setApiStatus({ loading: false, message: `Nao foi possivel consultar a sessao: ${error.message}.` });
        setAuthState({ loading: false, isAuthenticated: false, user: null, error: "Nao foi possivel verificar a autenticacao." });
      }
    }
    loadSession();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!authState.isAuthenticated) return;
    let active = true;
    async function loadStatus() {
      try {
        const response = await fetch("/api/hello", { credentials: "same-origin" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (!active) return;
        setApiStatus({ loading: false, message: `Backend conectado: ${data.app} respondeu "${data.message}" para ${data.username}.` });
      } catch (error) {
        if (!active) return;
        setApiStatus({ loading: false, message: `Nao foi possivel consultar a API: ${error.message}.` });
      }
    }
    setApiStatus({ loading: true, message: "Conectando ao backend..." });
    loadStatus();
    return () => { active = false; };
  }, [authState.isAuthenticated]);

  // F2 — após autenticação, verificar se já há contrato selecionado na sessão.
  // 200 → setSelectedContrato (vai direto para upload). 404 → null (mostra seletor).
  useEffect(() => {
    if (!authState.isAuthenticated) {
      setSelectedContrato(null);
      setContratoBootChecked(false);
      return;
    }
    let active = true;
    async function checkContrato() {
      try {
        const response = await fetch("/api/session/contrato", { credentials: "same-origin" });
        if (!active) return;
        if (response.status === 404) {
          setSelectedContrato(null);
        } else if (response.ok) {
          setSelectedContrato(await response.json());
        }
      } catch {
        // Falha de rede — assume sem contrato (seletor mostra erro de carga lá).
        if (active) setSelectedContrato(null);
      } finally {
        if (active) setContratoBootChecked(true);
      }
    }
    checkContrato();
    return () => { active = false; };
  }, [authState.isAuthenticated]);

  useEffect(() => {
    if (!authState.isAuthenticated) return;
    if (!selectedContrato) return;  // F2 — só carrega entries quando há contrato
    let active = true;
    async function loadEntries() {
      setEntriesState((current) => ({ ...current, loading: true, error: "" }));
      try {
        // F3b follow-up — tabela_persistida filtra por contrato ativo. Sem filtro,
        // trocar de contrato repopulava com TODAS as NFs do banco (bug visual:
        // "tabela se mantinha" entre sessões).
        const url = `/api/nf-entries?contrato_id=${encodeURIComponent(selectedContrato.id)}`;
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const rows = await response.json();
        if (!active) return;
        setEntriesState({ loading: false, rows, error: "" });
      } catch (error) {
        if (!active) return;
        setEntriesState({ loading: false, rows: [], error: `Nao foi possivel carregar os lancamentos: ${error.message}.` });
      }
    }
    loadEntries();
    return () => { active = false; };
  }, [authState.isAuthenticated, selectedContrato]);

  function handleFileSelection(event) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFiles(files);
  }

  function handleLoginChange(event) {
    const { name, value } = event.target;
    setLoginForm((current) => ({ ...current, [name]: value }));
  }

  async function handleLoginSubmit(event) {
    event.preventDefault();
    setIsSubmittingLogin(true);
    setAuthState((current) => ({ ...current, error: "" }));
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(loginForm),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? `HTTP ${response.status}`);
      }
      const data = await response.json();
      setAuthState({ loading: false, isAuthenticated: true, user: data.user, error: "" });
    } catch (error) {
      setAuthState({ loading: false, isAuthenticated: false, user: null, error: `Falha no login: ${error.message}.` });
    } finally {
      setIsSubmittingLogin(false);
    }
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    setSelectedFiles([]);
    setUploadState({ submitting: false, error: "", results: [], batchId: null, progress: 0, phase: "idle", progressMessage: "" });
    setEntriesState({ loading: false, rows: [], error: "" });
    setAuthState({ loading: false, isAuthenticated: false, user: null, error: "" });
    setApiStatus({ loading: false, message: "Aguardando autenticacao." });
    // F2 — backend já limpa contrato_id da sessão no logout; refletir no estado local.
    setSelectedContrato(null);
    setContratoBootChecked(false);
  }

  async function refreshEntries() {
    if (!selectedContrato) {
      setEntriesState({ loading: false, rows: [], error: "" });
      return;
    }
    const url = `/api/nf-entries?contrato_id=${encodeURIComponent(selectedContrato.id)}`;
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rows = await response.json();
    setEntriesState({ loading: false, rows, error: "" });
  }

  async function uploadWithSSE(files, onEvent) {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));

    const response = await fetch("/api/uploads", {
      method: "POST",
      credentials: "same-origin",
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail ?? `HTTP ${response.status}`);
    }

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
          try {
            onEvent(JSON.parse(line.slice(6)));
          } catch {
            // linha SSE malformada — ignorar
          }
        }
      }
    }
  }

  function buildPendingResults(files) {
    return files.map((file) => ({
      filename: file.name,
      status: "na_fila",
      status_reason: null,
      parser_error: null,
      inserted_count: 0,
      duplicate_count: 0,
    }));
  }

  function buildUploadErrorResults(files, message) {
    return files.map((file) => ({
      filename: file.name, status: "erro_upload", status_reason: "Falha no envio do arquivo.",
      parser_error: message, inserted_count: 0, duplicate_count: 0,
      timeline: ["Upload iniciado.", "Falha antes de concluir o processamento no backend."],
    }));
  }

  async function handleUploadSubmit() {
    if (selectedFiles.length === 0) {
      setUploadState({ submitting: false, results: [], batchId: null, progress: 0, phase: "idle", progressMessage: "" });
      return;
    }

    const totalFiles = selectedFiles.length;

    setUploadState({
      submitting: true,
      results: buildPendingResults(selectedFiles),
      batchId: null,
      progress: 3,
      phase: "uploading",
      progressMessage: `Enviando ${totalFiles} arquivo${totalFiles > 1 ? "s" : ""}…`,
    });

    try {
      let batchId = null;
      let savedCount = 0;
      let doneCount = 0;

      await uploadWithSSE(selectedFiles, (event) => {
        // Eventos de progresso intermediário por arquivo
        if (event.event in SSE_STATUS_MAP) {
          const newStatus = SSE_STATUS_MAP[event.event];

          // Calcular progresso global baseado no evento
          let progress;
          let phase = "uploading";
          let progressMessage;

          if (event.event === "file_saved") {
            savedCount++;
            // Fase 1: 5% → 60% proporcional aos arquivos salvos
            progress = 5 + Math.round((savedCount / totalFiles) * 55);
            progressMessage = `Salvando arquivos… (${savedCount}/${totalFiles})`;
          } else if (event.event === "file_parsing") {
            // Transição para fase 2 no primeiro arquivo processando
            phase = "processing";
            progress = Math.max(62, 62 + Math.round((doneCount / totalFiles) * 20));
            progressMessage = "Processando PDFs no backend…";
          } else {
            // file_queued: mantém progresso atual
            progress = undefined;
          }

          setUploadState((current) => ({
            ...current,
            ...(progress !== undefined ? { progress } : {}),
            phase,
            progressMessage: progressMessage ?? current.progressMessage,
            results: current.results.map((r) =>
              r.filename === event.filename ? { ...r, status: newStatus } : r
            ),
          }));
          return;
        }

        // Evento de conclusão por arquivo
        if (event.event === "file_done") {
          doneCount++;
          const processingProgress = Math.min(83, 62 + Math.round((doneCount / totalFiles) * 20));
          setUploadState((current) => ({
            ...current,
            phase: "processing",
            progress: processingProgress,
            progressMessage: `Processando PDFs… (${doneCount}/${totalFiles})`,
            results: current.results.map((r) =>
              r.filename === event.filename
                ? {
                    ...r,
                    status: event.status,
                    status_reason: event.status_reason ?? null,
                    parser_error: event.parser_error ?? null,
                    inserted_count: event.inserted_count ?? 0,
                    duplicate_count: event.duplicate_count ?? 0,
                  }
                : r
            ),
          }));
          return;
        }

        // Evento de lote concluído
        if (event.event === "batch_done") {
          batchId = event.batch_id;
          setUploadState((current) => ({
            ...current,
            batchId,
            progress: 87,
            phase: "refreshing",
            progressMessage: "Atualizando tabela de notas…",
          }));
        }
      });

      setSelectedFiles([]);
      await refreshEntries();

      setUploadState((current) => ({
        ...current,
        submitting: false,
        progress: 100,
        phase: "done",
        progressMessage: "Concluído.",
      }));
    } catch (error) {
      setUploadState({
        submitting: false,
        results: buildUploadErrorResults(selectedFiles, error.message),
        batchId: null,
        progress: 0,
        phase: "idle",
        progressMessage: "",
      });
    }
  }

  if (authState.loading) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="eyebrow">Sistema</p>
          <h1 className="auth-title">Verificando sessão…</h1>
        </div>
      </div>
    );
  }

  if (!authState.isAuthenticated) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <p className="eyebrow">Demonstração</p>
          <h1 className="auth-title">Recolhimento<br />de documentos</h1>
          <p className="auth-subtitle">MVP do novo sistema de administração de contratos.</p>
          <form className="login-form" onSubmit={handleLoginSubmit}>
            <label className="field">
              <span className="field-label">Usuário</span>
              <input name="username" type="text" value={loginForm.username} onChange={handleLoginChange} autoComplete="username" />
            </label>
            <label className="field">
              <span className="field-label">Senha</span>
              <input name="password" type="password" value={loginForm.password} onChange={handleLoginChange} autoComplete="current-password" />
            </label>
            <button type="submit" className="btn-primary" disabled={isSubmittingLogin}>
              {isSubmittingLogin ? "Entrando…" : "Entrar"}
            </button>
          </form>
          <div className="auth-hint">
            usuário: <code>user</code> &nbsp;·&nbsp; senha: <code>password</code>
          </div>
          {authState.error && <p className="auth-error">{authState.error}</p>}
        </div>
      </div>
    );
  }

  // F2 — entre autenticação e seleção de contrato, mostra um spinner para
  // evitar flash da tela de seleção quando o usuário já tinha contrato.
  if (!contratoBootChecked) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1 className="auth-title">Carregando…</h1>
        </div>
      </div>
    );
  }

  // F2 — sem contrato selecionado, redireciona para a tela de seleção.
  if (!selectedContrato) {
    return (
      <ContratoSelector
        onSelect={(contrato) => setSelectedContrato(contrato)}
        onLogout={handleLogout}
        username={authState.user?.username}
      />
    );
  }

  const hasResults = uploadState.results.length > 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="topbar-brand">GFIP - Recebimento de Notas Fiscais</span>
        <nav className="topbar-nav">
          <button
            type="button"
            className={`topbar-link${currentView === "upload" ? " is-active" : ""}`}
            onClick={() => setCurrentView("upload")}
          >
            Upload
          </button>
          <button
            type="button"
            className={`topbar-link${currentView === "notas" ? " is-active" : ""}`}
            onClick={() => setCurrentView("notas")}
          >
            Notas
          </button>
        </nav>
        <div className="topbar-right">
          {/* F2 — contrato ativo na topbar */}
          <span className="topbar-contrato" title={`${selectedContrato.sigla} · ${selectedContrato.uf ?? ""}`.trim()}>
            {selectedContrato.numero}
          </span>
          <span
            className={`status-dot ${apiStatus.loading ? "is-loading" : "is-online"}`}
            title={apiStatus.message}
          />
          <span className="topbar-user">{authState.user?.username ?? "user"}</span>
          <button className="topbar-logout" type="button" onClick={handleLogout}>
            Sair
          </button>
        </div>
      </header>

      <main className="main-content">
        {currentView === "notas" && (
          <NfsBrowser selectedContratoId={selectedContrato?.id} />
        )}

        {currentView === "upload" && (<>
        <div className={`upload-row${hasResults ? " upload-row--split" : ""}`}>
          <section className="card upload-card">
            <div className="card-header">
              <div>
                <p className="section-kicker">Upload</p>
                <h2 className="card-title">Envio em lote de PDFs</h2>
              </div>
              {!hasResults && (
                <span className="section-badge">Múltiplos arquivos</span>
              )}
            </div>

            <label className="dropzone" htmlFor="pdf-upload">
              <input
                id="pdf-upload"
                type="file"
                accept="application/pdf"
                multiple
                onChange={handleFileSelection}
              />
              <svg className="dropzone-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path d="M7 16a4 4 0 0 1-.88-7.903A5 5 0 1 1 15.9 6L16 6a5 5 0 0 1 1 9.9M15 13l-3-3m0 0l-3 3m3-3v12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <strong className="dropzone-label">Arraste PDFs ou clique para selecionar</strong>
            </label>

            <div className="file-status">
              <span className="file-dot" />
              <span>{formatSelectedFiles(selectedFiles)}</span>
            </div>

            {selectedFiles.length > MAX_FILES_PER_BATCH && (
              <div className="inline-error" role="alert">
                Excedeu o limite de {MAX_FILES_PER_BATCH} arquivos por lote. Reduza a seleção para enviar.
              </div>
            )}

            {(uploadState.submitting || uploadState.phase === "done") && (
              <div className="progress-block">
                <div className="progress-phases">
                  <span className={uploadState.phase === "uploading" ? "phase-active" : (uploadState.progress > 60 ? "phase-done" : "phase-idle")}>
                    ① Envio
                  </span>
                  <span className={uploadState.phase === "processing" ? "phase-active" : (uploadState.progress > 85 ? "phase-done" : "phase-idle")}>
                    ② Processamento
                  </span>
                  <span className={uploadState.phase === "refreshing" ? "phase-active" : (uploadState.phase === "done" ? "phase-done" : "phase-idle")}>
                    ③ Tabela
                  </span>
                </div>
                <div className="progress-track">
                  <div
                    className={`progress-fill${uploadState.phase === "processing" ? " is-processing" : ""}`}
                    style={{ width: `${uploadState.progress}%` }}
                  />
                </div>
                <span className="progress-label">{uploadState.progressMessage}</span>
              </div>
            )}

            <button
              className="btn-primary upload-btn"
              type="button"
              disabled={uploadState.submitting || selectedFiles.length > MAX_FILES_PER_BATCH}
              onClick={handleUploadSubmit}
            >
              {uploadState.submitting ? "Enviando…" : "Enviar PDFs"}
            </button>
          </section>

          {hasResults && (
            <section className="card results-card">
              <div className="card-header">
                <div>
                  <p className="section-kicker">Processamento</p>
                  <h2 className="card-title">Status por arquivo</h2>
                </div>
                {uploadState.batchId && (
                  <span className="batch-label" title={uploadState.batchId}>
                    Lote {uploadState.batchId.slice(0, 8)}
                  </span>
                )}
              </div>

              <ul className="results-list">
                {uploadState.results.map((item, index) => (
                  <li key={`${item.filename}-${index}`} className="result-item">
                    <div className="result-row">
                      <span className="result-filename" title={item.filename}>{item.filename}</span>
                      <StatusBadge status={item.status} />
                    </div>
                    <div className="result-counts">
                      <span>{item.inserted_count} inserido{item.inserted_count !== 1 ? "s" : ""}</span>
                      <span className="count-sep">·</span>
                      <span>{item.duplicate_count} duplicado{item.duplicate_count !== 1 ? "s" : ""}</span>
                    </div>
                    {item.status_reason && <p className="result-reason">{item.status_reason}</p>}
                    {item.parser_error && <p className="result-error" title={item.parser_error}>{item.parser_error}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <section className="card table-card">
          <div className="card-header">
            <div>
              <p className="section-kicker">Consulta</p>
              <h2 className="card-title">Anexo I</h2>
            </div>
            <div className="table-header-right">
              <span className="row-count">
                {entriesState.loading ? "Atualizando…" : `${entriesState.rows.length} registros`}
              </span>
              <button
                className="btn-ghost"
                type="button"
                disabled={entriesState.loading || entriesState.rows.length === 0}
                onClick={() => exportEntriesCompletas(entriesState.rows)}
              >
                Exportar Excel
              </button>
            </div>
          </div>

          {entriesState.error && <p className="inline-error">{entriesState.error}</p>}

          {!entriesState.loading && entriesState.rows.length === 0 ? (
            <div className="empty-state">
              <p>Nenhuma nota carregada ainda. Envie PDFs para popular a base.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <colgroup>
                  <col className="col-descricao" />
                  <col className="col-ncm" />
                  <col className="col-quant" />
                  <col className="col-preco" />
                  <col className="col-nf" />
                  <col className="col-tipo" />
                  <col className="col-data" />
                  <col className="col-cnpj" />
                  <col className="col-fornecedor" />
                  <col className="col-valor" />
                  <col className="col-contrato" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Descrição</th>
                    <th>NCM</th>
                    <th>Qtd</th>
                    <th>Preço unit.</th>
                    <th>NF</th>
                    <th>Tipo</th>
                    <th>Emissão</th>
                    <th>CNPJ</th>
                    <th>Fornecedor</th>
                    <th>Valor</th>
                    <th>Contrato</th>
                  </tr>
                </thead>
                <tbody>
                  {entriesState.rows.map((row) => (
                    <tr key={row.id}>
                      <td title={String(row.descricao ?? "")}>{row.descricao}</td>
                      <td title={String(row.ncm ?? "")}>{row.ncm}</td>
                      <td title={String(row.quantidade ?? "")}>{row.quantidade}</td>
                      <td title={String(row.preco_unitario ?? "")}>{row.preco_unitario}</td>
                      <td title={String(row.numero_nf ?? "")}>{row.numero_nf}</td>
                      <td title={String(row.tipo_nota ?? "")}>{row.tipo_nota}</td>
                      <td title={String(row.data_emissao ?? "")}>{row.data_emissao}</td>
                      <td title={String(row.cnpj ?? "")}>{row.cnpj}</td>
                      <td title={String(row.fornecedor ?? "")}>{row.fornecedor}</td>
                      <td title={String(row.valor_total ?? "")}>{row.valor_total}</td>
                      <td title={String(row.contrato ?? "")}>{row.contrato}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        </>)}
      </main>

      <footer className="app-footer">
        <span>MVP · Novo AFI</span>
        <span>Sistema de recolhimento de notas fiscais</span>
      </footer>
    </div>
  );
}
