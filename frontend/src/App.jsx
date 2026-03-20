import { useEffect, useState } from "react";

const initialRows = [];

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
  const [apiStatus, setApiStatus] = useState({
    loading: true,
    message: "Conectando ao backend...",
  });
  const [selectedFiles, setSelectedFiles] = useState([]);

  useEffect(() => {
    let active = true;

    async function loadStatus() {
      try {
        const response = await fetch("/api/hello");
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (!active) {
          return;
        }

        setApiStatus({
          loading: false,
          message: `Backend conectado: ${data.app} respondeu "${data.message}".`,
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

    loadStatus();

    return () => {
      active = false;
    };
  }, []);

  function handleFileSelection(event) {
    const files = Array.from(event.target.files ?? []);
    setSelectedFiles(files);
  }

  return (
    <div className="page-shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">MVP em construcao</p>
          <h1>Novo AFI para notas fiscais em PDF.</h1>
          <p className="hero-text">
            Esta interface ja esta pronta para evoluir para upload em lote,
            autenticacao e consulta persistida. Nesta fase, ela confirma o
            frontend real servido pelo backend e prepara o fluxo visual do
            produto.
          </p>
        </div>

        <aside className="hero-panel">
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
              Upload sera habilitado na integracao real
            </button>
            <p>Estrutura pronta para a futura chamada da API de processamento.</p>
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
