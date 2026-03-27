import { useEffect, useState } from "react";

const initialRows = [];
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

          <div className="action-row">
            <button type="button" disabled>
              Upload real está desabilitado
            </button>
            {/* <p>Estrutura pronta para a futura chamada da API de processamento.</p> */}
          </div>
        </section>

        <section className="card processing-card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Processamento</p>
              <h2>Status por arquivo</h2>
            </div>
          </div>

          <div className="status-grid">
            <article>
              <strong>Processado</strong>
              <p>Notas novas persistidas com sucesso.</p>
            </article>
            <article>
              <strong>Duplicado</strong>
              <p>Arquivos ja conhecidos pela chave de negocio.</p>
            </article>
            <article>
              <strong>Rejeitado</strong>
              <p>PDF fora do fluxo compativel do MVP.</p>
            </article>
            <article>
              <strong>Erro de parsing</strong>
              <p>Falha na extracao usando o parser legado.</p>
            </article>
          </div>
        </section>

        <section className="card table-card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Consulta</p>
              <h2>Tabela persistida de notas</h2>
            </div>
            <span className="section-badge muted">Estado vazio nesta fase</span>
          </div>

          {initialRows.length === 0 ? (
            <div className="empty-state">
              <h3>Nenhuma nota carregada ainda</h3>
              <p>
                Quando a API real de notas e o banco estiverem conectados, esta
                area passara a refletir o estado persistido da aplicacao.
              </p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Numero</th>
                    <th>CNPJ</th>
                    <th>Emissao</th>
                    <th>Fornecedor</th>
                    <th>Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {initialRows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.numero_nf}</td>
                      <td>{row.cnpj}</td>
                      <td>{row.data_emissao}</td>
                      <td>{row.fornecedor}</td>
                      <td>{row.valor}</td>
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
