import { useEffect, useMemo, useState } from "react";

/**
 * F2 — Tela de seleção de contrato.
 *
 * Renderizada quando autenticado MAS sem contrato na sessão.
 * `onSelect(contrato)` é chamado após `POST /api/session/contrato` com sucesso.
 * `onLogout()` permite sair sem selecionar (libera o usuário travado).
 */
export default function ContratoSelector({ onSelect, onLogout, username }) {
  const [contratos, setContratos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
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

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return contratos;
    return contratos.filter((c) => {
      return [c.numero, c.sigla, c.uf, c.tranche]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q));
    });
  }, [contratos, filter]);

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
              <p className="section-kicker">Contrato</p>
              <h2 className="card-title">Selecione o contrato para esta sessão</h2>
              <p className="contrato-help">
                Todos os uploads e consultas seguintes serão associados a este contrato.
                Para trocar, use Sair e entre novamente.
              </p>
            </div>
          </div>

          <input
            type="text"
            className="contrato-filter"
            placeholder="Filtrar por número, sigla, UF ou tranche…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            disabled={loading}
          />

          {loading && <p className="contrato-status">Carregando contratos…</p>}
          {loadError && <p className="inline-error">{loadError}</p>}

          {!loading && !loadError && (
            <>
              <div className="contrato-count">
                {filtered.length} de {contratos.length} contrato{contratos.length === 1 ? "" : "s"}
              </div>

              <ul className="contrato-list">
                {filtered.map((c) => (
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
                      <strong className="contrato-numero">{c.numero}</strong>
                      <span className="contrato-meta">
                        {[c.sigla, c.uf, c.tranche, c.tipo_contrato].filter(Boolean).join(" · ")}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>

              {filtered.length === 0 && (
                <p className="contrato-status">Nenhum contrato corresponde ao filtro.</p>
              )}
            </>
          )}

          {submitError && <p className="inline-error">{submitError}</p>}

          <button
            className="btn-primary"
            type="button"
            onClick={handleConfirm}
            disabled={!selectedId || submitting || loading}
          >
            {submitting ? "Confirmando…" : "Confirmar contrato"}
          </button>
        </section>
      </main>
    </div>
  );
}
