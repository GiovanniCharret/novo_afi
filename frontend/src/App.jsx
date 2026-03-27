import { useEffect, useState } from "react";
import * as XLSX from "xlsx";

const defaultLoginForm = {
  username: "user",
  password: "password",
};

function formatSelectedFiles(files) {
  if (files.length === 0) {
    return "Nenhum PDF selecionado ainda.";
  }

  if (files.length === 1) {
    return `1 arquivo pronto para envio: ${files[0].name}`;
  }

  return `${files.length} arquivos prontos para envio em lote.`;
}

function exportEntriesToExcel(rows) {
  const worksheetRows = rows.map((row) => ({
    descricao: row.descricao,
    ncm: row.ncm,
    quant: row.quantidade,
    preco_unitario: row.preco_unitario,
    numero_nf: row.numero_nf,
    tipo_nota: row.tipo_nota,
    data_emissao: row.data_emissao,
    cnpj: row.cnpj,
    fornecedor: row.fornecedor,
    valor: row.valor_total,
    contrato: row.contrato,
  }));

  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.json_to_sheet(worksheetRows);

  XLSX.utils.book_append_sheet(workbook, worksheet, "Notas");
  XLSX.writeFile(workbook, "tabela_persistida_notas.xlsx");
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
    error: "",
    results: [],
    batchId: null,
    progress: 0,
    phase: "idle",
    progressMessage: "",
  });
  const [loginForm, setLoginForm] = useState(defaultLoginForm);
  const [isSubmittingLogin, setIsSubmittingLogin] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadSession() {
      try {
        const response = await fetch("/api/auth/session", {
          credentials: "same-origin",
        });

        if (response.status === 401) {
          if (!active) {
            return;
          }

          setAuthState({
            loading: false,
            isAuthenticated: false,
            user: null,
            error: "",
          });
          setApiStatus({
            loading: false,
            message: "Aguardando autenticacao.",
          });
          return;
        }

        const data = await response.json();
        if (!active) {
          return;
        }

        setAuthState({
          loading: false,
          isAuthenticated: true,
          user: data.user,
          error: "",
        });
      } catch (error) {
        if (!active) {
          return;
        }

        setApiStatus({
          loading: false,
          message: `Nao foi possivel consultar a sessao: ${error.message}.`,
        });
        setAuthState({
          loading: false,
          isAuthenticated: false,
          user: null,
          error: "Nao foi possivel verificar a autenticacao.",
        });
      }
    }

    loadSession();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!authState.isAuthenticated) {
      return;
    }

    let active = true;

    async function loadStatus() {
      try {
        const response = await fetch("/api/hello", {
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!active) {
          return;
        }
        setApiStatus({
          loading: false,
          message: `Backend conectado: ${data.app} respondeu "${data.message}" para ${data.username}.`,
        });
      } catch (error) {
        if (!active) {
          return;
        }

        setApiStatus({
          loading: false,
          message: `Nao foi possivel consultar a API: ${error.message}.`,
        });
      }
    }

    setApiStatus({
      loading: true,
      message: "Conectando ao backend...",
    });
    loadStatus();

    return () => {
      active = false;
    };
  }, [authState.isAuthenticated]);

  useEffect(() => {
    if (!authState.isAuthenticated) {
      return;
    }

    let active = true;

    async function loadEntries() {
      setEntriesState((current) => ({
        ...current,
        loading: true,
        error: "",
      }));

      try {
        const response = await fetch("/api/nf-entries", {
          credentials: "same-origin",
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const rows = await response.json();
        if (!active) {
          return;
        }

        setEntriesState({
          loading: false,
          rows,
          error: "",
        });
      } catch (error) {
        if (!active) {
          return;
        }

        setEntriesState({
          loading: false,
          rows: [],
          error: `Nao foi possivel carregar os lancamentos: ${error.message}.`,
        });
      }
    }

    loadEntries();

    return () => {
      active = false;
    };
  }, [authState.isAuthenticated]);

  function handleFileSelection(event) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFiles(files);
  }

  function handleLoginChange(event) {
    const { name, value } = event.target;
    setLoginForm((current) => ({
      ...current,
      [name]: value,
    }));
  }

  async function handleLoginSubmit(event) {
    event.preventDefault();
    setIsSubmittingLogin(true);
    setAuthState((current) => ({
      ...current,
      error: "",
    }));

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(loginForm),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail ?? `HTTP ${response.status}`);
      }

      const data = await response.json();
      setAuthState({
        loading: false,
        isAuthenticated: true,
        user: data.user,
        error: "",
      });
    } catch (error) {
      setAuthState({
        loading: false,
        isAuthenticated: false,
        user: null,
        error: `Falha no login: ${error.message}.`,
      });
    } finally {
      setIsSubmittingLogin(false);
    }
  }

  async function handleLogout() {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });

    setSelectedFiles([]);
    setUploadState({
      submitting: false,
      error: "",
      results: [],
      batchId: null,
      progress: 0,
      phase: "idle",
      progressMessage: "",
    });
    setEntriesState({
      loading: false,
      rows: [],
      error: "",
    });
    setAuthState({
      loading: false,
      isAuthenticated: false,
      user: null,
      error: "",
    });
    setApiStatus({
      loading: false,
      message: "Aguardando autenticacao.",
    });
  }

  async function refreshEntries() {
    const response = await fetch("/api/nf-entries", {
      credentials: "same-origin",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const rows = await response.json();
    setEntriesState({
      loading: false,
      rows,
      error: "",
    });
  }

  function uploadFilesWithProgress(files, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();

      files.forEach((file) => {
        formData.append("files", file);
      });

      xhr.open("POST", "/api/uploads");
      xhr.withCredentials = true;

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable) {
          return;
        }

        const percent = Math.min(75, Math.round((event.loaded / event.total) * 75));
        onProgress({
          progress: percent,
          phase: "uploading",
          message: `Enviando arquivos... ${percent}%`,
        });
      };

      xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          try {
            const payload = JSON.parse(xhr.responseText);
            reject(new Error(payload.detail ?? `HTTP ${xhr.status}`));
          } catch {
            reject(new Error(`HTTP ${xhr.status}`));
          }
          return;
        }

        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Resposta invalida do backend."));
        }
      };

      xhr.onerror = () => {
        reject(new Error("Falha de rede durante o upload."));
      };

      xhr.send(formData);
    });
  }

  async function handleUploadSubmit() {
    if (selectedFiles.length === 0) {
      setUploadState({
        submitting: false,
        error: "Selecione ao menos um PDF antes de enviar.",
        results: [],
        batchId: null,
        progress: 0,
        phase: "idle",
        progressMessage: "",
      });
      return;
    }

    let processingTimer = null;

    setUploadState({
      submitting: true,
      error: "",
      results: [],
      batchId: null,
      progress: 2,
      phase: "uploading",
      progressMessage: "Preparando envio...",
    });

    try {
      const payload = await uploadFilesWithProgress(selectedFiles, ({ progress, phase, message }) => {
        setUploadState((current) => ({
          ...current,
          progress,
          phase,
          progressMessage: message,
        }));
      });

      setUploadState((current) => ({
        ...current,
        progress: Math.max(current.progress, 78),
        phase: "processing",
        progressMessage: "Processando arquivos no backend...",
      }));

      processingTimer = window.setInterval(() => {
        setUploadState((current) => {
          if (current.phase !== "processing") {
            return current;
          }

          return {
            ...current,
            progress: current.progress >= 96 ? current.progress : current.progress + 2,
          };
        });
      }, 250);

      setUploadState({
        submitting: false,
        error: "",
        results: payload.files ?? [],
        batchId: payload.batch_id ?? null,
        progress: 100,
        phase: "done",
        progressMessage: "Processamento concluido.",
      });
      setSelectedFiles([]);
      await refreshEntries();
    } catch (error) {
      setUploadState({
        submitting: false,
        error: `Falha no upload: ${error.message}.`,
        results: [],
        batchId: null,
        progress: 0,
        phase: "idle",
        progressMessage: "",
      });
    } finally {
      if (processingTimer) {
        window.clearInterval(processingTimer);
      }
    }
  }

  if (authState.loading) {
    return (
      <div className="auth-shell">
        <section className="auth-card">
          <p className="eyebrow">Autenticacao</p>
          <h1>Verificando sua sessao.</h1>
          <p className="auth-text">Sistema de recolhimento de NF</p>
        </section>
      </div>
    );
  }

  if (!authState.isAuthenticated) {
    return (
      <div className="auth-shell">
        <section className="auth-card">
          <p className="eyebrow">Demonstração</p>
          <h1>Recolhimento de documentos</h1>
          <p className="auth-text">
            MVP do novo sistema de administração de contratos.
          </p>

          <form className="login-form" onSubmit={handleLoginSubmit}>
            <label>
              <span>Usuario</span>
              <input
                name="username"
                type="text"
                value={loginForm.username}
                onChange={handleLoginChange}
                autoComplete="username"
              />
            </label>

            <label>
              <span>Senha</span>
              <input
                name="password"
                type="password"
                value={loginForm.password}
                onChange={handleLoginChange}
                autoComplete="current-password"
              />
            </label>

            <button
              type="submit"
              disabled={isSubmittingLogin}
              style={{ cursor: isSubmittingLogin ? "not-allowed" : "pointer" }}
            >
              {isSubmittingLogin ? "Entrando..." : "Entrar"}
            </button>
          </form>

          <div className="auth-note">
            <strong>Como entrar no site?</strong>
            <p>
              usuario: <code>user</code> | senha: <code>password</code>
            </p>
          </div>

          {authState.error ? <p className="auth-error">{authState.error}</p> : null}
        </section>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Ambiente de upload de NFs</p>
          <h1>Recolhimento de documentos</h1>
          <p className="hero-text">
            Interface pronta para upload em lote,
            autenticacao e consulta persistida.
          </p>
        </div>

        <aside className="hero-panel">
          <div className="hero-panel-top">
            <span className="user-chip">
              Logado como {authState.user?.username ?? "user"}
            </span>
            <button
              type="button"
              className="ghost-button"
              onClick={handleLogout}
              style={{ cursor: "pointer" }}
            >
              Sair
            </button>
          </div>
          <span className={`status-pill ${apiStatus.loading ? "is-loading" : ""}`}>
            {apiStatus.loading ? "Sincronizando" : "Backend online"}
          </span>
          <p>{apiStatus.message}</p>
        </aside>
      </header>

      <main className="dashboard">
        <section className="card upload-card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Upload</p>
              <h2>Envio em lote de PDFs</h2>
            </div>
            <span className="section-badge">Preparado para multiplos arquivos</span>
          </div>

          <label className="upload-dropzone" htmlFor="pdf-upload">
            <input
              id="pdf-upload"
              type="file"
              accept="application/pdf"
              multiple
              onChange={handleFileSelection}
            />
            <strong>Arraste PDFs aqui ou clique para selecionar</strong>
            <span>
              Apenas arquivos compativeis com o parser existente serao aceitos
              nas proximas fases.
            </span>
          </label>

          <div className="inline-status">
            <span className="dot" />
            <p>{formatSelectedFiles(selectedFiles)}</p>
          </div>

          {uploadState.submitting || uploadState.phase === "done" ? (
            <div className="progress-block">
              <div className="progress-meta">
                <strong>
                  {uploadState.phase === "processing"
                    ? "Processando no backend"
                    : uploadState.phase === "done"
                      ? "Upload concluido"
                      : "Fazendo upload"}
                </strong>
                <span>{uploadState.progress}%</span>
              </div>
              <div
                className={`progress-bar ${uploadState.phase === "processing" ? "is-processing" : ""}`}
              >
                <span style={{ width: `${uploadState.progress}%` }} />
              </div>
              <p className="progress-caption">{uploadState.progressMessage}</p>
            </div>
          ) : null}

          <div className="action-row">
            <button
              type="button"
              disabled={uploadState.submitting}
              onClick={handleUploadSubmit}
              style={{ cursor: uploadState.submitting ? "not-allowed" : "pointer" }}
            >
              {uploadState.submitting ? "Enviando PDFs..." : "Enviar PDFs"}
            </button>
            <p>
              O backend processa cada arquivo individualmente e atualiza a base
              persistida quando encontra linhas novas.
            </p>
          </div>

          {uploadState.error ? <p className="inline-error">{uploadState.error}</p> : null}
        </section>

        <section className="card processing-card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Processamento</p>
              <h2>Status por arquivo</h2>
            </div>
            {uploadState.batchId ? (
              <span className="section-badge muted">Lote {uploadState.batchId.slice(0, 8)}</span>
            ) : null}
          </div>

          {uploadState.results.length === 0 ? (
            <div className="empty-state compact">
              <h3>Nenhum arquivo processado nesta sessao</h3>
              <p>
                Ao enviar um lote, esta area passara a mostrar o status retornado
                pelo backend para cada arquivo.
              </p>
            </div>
          ) : (
            <div className="status-grid">
              {uploadState.results.map((item) => (
                <article key={`${item.filename}-${item.status}`}>
                  <strong>{item.filename}</strong>
                  <p>Status: {item.status}</p>
                  <p>
                    Novas linhas: {item.inserted_count} | Duplicadas: {item.duplicate_count}
                  </p>
                  {item.status_reason ? <p>Motivo: {item.status_reason}</p> : null}
                  {item.parser_error ? <p>Erro: {item.parser_error}</p> : null}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="card table-card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Consulta</p>
              <h2>Tabela persistida de notas</h2>
            </div>
            <div className="section-actions">
              <span className="section-badge muted">
                {entriesState.loading ? "Atualizando..." : `${entriesState.rows.length} linhas`}
              </span>
              <button
                type="button"
                className="ghost-button"
                disabled={entriesState.loading || entriesState.rows.length === 0}
                onClick={() => exportEntriesToExcel(entriesState.rows)}
                style={{
                  cursor: entriesState.loading || entriesState.rows.length === 0
                    ? "not-allowed"
                    : "pointer",
                }}
              >
                Exportar Excel
              </button>
            </div>
          </div>

          {entriesState.error ? <p className="inline-error">{entriesState.error}</p> : null}

          {!entriesState.loading && entriesState.rows.length === 0 ? (
            <div className="empty-state">
              <h3>Nenhuma nota carregada ainda</h3>
              <p>
                A base ainda nao possui linhas persistidas. Assim que um upload
                processar lancamentos novos, a tabela sera atualizada automaticamente.
              </p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Descricao</th>
                    <th>NCM</th>
                    <th>Quant</th>
                    <th>Preco unitario</th>
                    <th>Numero NF</th>
                    <th>Tipo nota</th>
                    <th>Data emissao</th>
                    <th>CNPJ</th>
                    <th>Fornecedor</th>
                    <th>Valor</th>
                    <th>Contrato</th>
                  </tr>
                </thead>
                <tbody>
                  {entriesState.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.descricao}</td>
                      <td>{row.ncm}</td>
                      <td>{row.quantidade}</td>
                      <td>{row.preco_unitario}</td>
                      <td>{row.numero_nf}</td>
                      <td>{row.tipo_nota}</td>
                      <td>{row.data_emissao}</td>
                      <td>{row.cnpj}</td>
                      <td>{row.fornecedor}</td>
                      <td>{row.valor_total}</td>
                      <td>{row.contrato}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
