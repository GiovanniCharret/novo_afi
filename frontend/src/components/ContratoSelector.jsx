import { useEffect, useMemo, useState } from "react";

/**
 * F2 — Tela de seleção de contrato em dois níveis (Estado → Contrato).
 *
 * Nível 1: lista de estados (UF distintos entre os contratos ativos), com contagem.
 * Nível 2: lista de contratos do estado escolhido, exibindo
 *          `sigla · tranche · tipo_contrato` (linha primária) e `numero` abaixo.
 *
 * Filtro é por step. Confirmar dispara `POST /api/session/contrato` → `onSelect`.
 */

// Map UF → nome completo. Inclui SEM_UF para contratos com uf nulo.
const UF_NOMES = {
  AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia",
  CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás",
  MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso",
  PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná",
  RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima",
  RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo",
  TO: "Tocantins",
};
const SEM_UF_KEY = "__sem_uf__";
const SEM_UF_NOME = "Sem estado definido";

export default function ContratoSelector({ onSelect, onLogout, username }) {
  const [contratos, setContratos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [step, setStep] = useState("estado"); // "estado" | "contrato"
  const [selectedUf, setSelectedUf] = useState(null);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const resp = await fetch("/api/contratos", { credentials: "same-origin" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (!active) return;
        setContratos(data);
      } catch (e) {
        if (!active) return;
        setLoadError(`Não foi possível carregar contratos: ${e.message}`);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  // Estados agregados (com contagem) ordenados pelo nome em pt-BR.
  const estados = useMemo(() => {
    const counts = new Map();
    for (const c of contratos) {
      const key = c.uf || SEM_UF_KEY;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const lista = Array.from(counts.entries()).map(([key, count]) => ({
      key,
      uf: key === SEM_UF_KEY ? null : key,
      nome: key === SEM_UF_KEY ? SEM_UF_NOME : (UF_NOMES[key] ?? key),
      count,
    }));
    lista.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
    return lista;
  }, [contratos]);

  const estadosFiltrados = useMemo(() => {
    if (step !== "estado") return estados;
    const q = filter.trim().toLowerCase();
    if (!q) return estados;
    return estados.filter((e) =>
      e.nome.toLowerCase().includes(q) || (e.uf ?? "").toLowerCase().includes(q)
    );
  }, [estados, filter, step]);

  const contratosDoEstado = useMemo(() => {
    if (!selectedUf && selectedUf !== null) return [];
    return contratos.filter((c) => {
      if (selectedUf === SEM_UF_KEY) return !c.uf;
      return c.uf === selectedUf;
    });
  }, [contratos, selectedUf]);

  const contratosFiltrados = useMemo(() => {
    if (step !== "contrato") return contratosDoEstado;
    const q = filter.trim().toLowerCase();
    if (!q) return contratosDoEstado;
    return contratosDoEstado.filter((c) =>
      [c.sigla, c.tranche, c.tipo_contrato, c.numero]
        .filter(Boolean)
        .some((f) => String(f).toLowerCase().includes(q))
    );
  }, [contratosDoEstado, filter, step]);

  function handleSelectEstado(key) {
    setSelectedUf(key);
    setStep("contrato");
    setSelectedId(null);
    setFilter("");
    setSubmitError("");
  }

  function handleBack() {
    setStep("estado");
    setSelectedUf(null);
    setSelectedId(null);
    setFilter("");
    setSubmitError("");
  }

  async function handleConfirm() {
    if (!selectedId || submitting) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const resp = await fetch("/api/session/contrato", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ contrato_id: selectedId }),
      });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        throw new Error(payload.detail ?? `HTTP ${resp.status}`);
      }
      const contrato = await resp.json();
      onSelect(contrato);
    } catch (e) {
      setSubmitError(`Falha ao selecionar contrato: ${e.message}`);
      setSubmitting(false);
    }
  }

  const estadoAtual = selectedUf === null
    ? null
    : estados.find((e) => e.key === selectedUf);

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="topbar-brand">GFIP - Recebimento de Notas Fiscais</span>
        <div className="topbar-right">
          <span className="topbar-user">{username ?? "user"}</span>
          <button className="topbar-logout" type="button" onClick={onLogout}>
            Sair
          </button>
        </div>
      </header>

      <main className="main-content">
        <section className="card contrato-card">
          <div className="card-header">
            <div>
              {step === "contrato" && estadoAtual && (
                <p className="breadcrumb">
                  <b>Estado:</b> {estadoAtual.nome}
                  {estadoAtual.uf ? ` · ${estadoAtual.uf}` : ""}
                </p>
              )}
              <p className="section-kicker">
                {step === "estado" ? "selecione o estado" : "contrato"}
              </p>
              <h2 className="card-title">Selecione o contrato para esta sessão</h2>
              <p className="contrato-help">
                Todos os uploads e consultas seguintes serão associados ao contrato selecionado.
                Para trocar, use Sair e entre novamente.
              </p>
            </div>
          </div>

          <input
            type="text"
            className="contrato-filter"
            placeholder={step === "estado" ? "Filtrar por estado…" : "Filtrar por sigla, tranche, tipo ou número…"}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            disabled={loading}
          />

          {loading && <p className="contrato-status">Carregando contratos…</p>}
          {loadError && <p className="inline-error">{loadError}</p>}

          {!loading && !loadError && step === "estado" && (
            <>
              <div className="contrato-count">
                {estadosFiltrados.length} de {estados.length} estado{estados.length === 1 ? "" : "s"}
              </div>
              <ul className="contrato-list">
                {estadosFiltrados.map((e) => (
                  <li
                    key={e.key}
                    className="contrato-item estado-item"
                    onClick={() => handleSelectEstado(e.key)}
                  >
                    <span className="estado-name">
                      {e.nome}
                      {e.uf && <span className="estado-uf">{e.uf}</span>}
                    </span>
                    <span className="estado-count">
                      {e.count} contrato{e.count === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
              {estadosFiltrados.length === 0 && (
                <p className="contrato-status">Nenhum estado corresponde ao filtro.</p>
              )}
            </>
          )}

          {!loading && !loadError && step === "contrato" && (
            <>
              <div className="contrato-count">
                {contratosFiltrados.length} de {contratosDoEstado.length} contrato{contratosDoEstado.length === 1 ? "" : "s"}
              </div>
              <ul className="contrato-list">
                {contratosFiltrados.map((c) => (
                  <li
                    key={c.id}
                    className={`contrato-item${selectedId === c.id ? " is-selected" : ""}`}
                    onClick={() => setSelectedId(c.id)}
                  >
                    <input
                      type="radio"
                      name="contrato"
                      value={c.id}
                      checked={selectedId === c.id}
                      onChange={() => setSelectedId(c.id)}
                      className="contrato-radio"
                    />
                    <div className="contrato-info">
                      <span className="contrato-primary">
                        {[c.sigla, c.tranche, c.tipo_contrato].filter(Boolean).join(" · ")}
                      </span>
                      <span className="contrato-secondary">{c.numero}</span>
                    </div>
                  </li>
                ))}
              </ul>
              {contratosFiltrados.length === 0 && (
                <p className="contrato-status">Nenhum contrato corresponde ao filtro.</p>
              )}

              {submitError && <p className="inline-error">{submitError}</p>}

              <div className="btn-row">
                <button
                  className="btn-back"
                  type="button"
                  onClick={handleBack}
                  disabled={submitting}
                >
                  ← Voltar para estados
                </button>
                <button
                  className="btn-primary"
                  type="button"
                  onClick={handleConfirm}
                  disabled={!selectedId || submitting}
                >
                  {submitting ? "Confirmando…" : "Confirmar contrato"}
                </button>
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}
