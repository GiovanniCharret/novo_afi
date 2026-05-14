import { useEffect, useMemo, useState } from "react";

import { UF_NOMES } from "../lib/ufNomes";

/**
 * F3 — Browser de contratos da base estática.
 *
 * Lê tabela `contratos` (seedada de `base_contratos.json` em F2) via
 * `GET /api/contratos` com filtros opcionais. Sem clique de linha
 * (decisão F3-c — consulta pura). Sem export (F3-e — deferido).
 *
 * Opções dos selects (UF, tipo, tranche) são derivadas de uma resposta
 * inicial sem filtros, no mount, para evitar dependência circular
 * com filtros aplicados.
 */

const EMPTY_FILTERS = {
  q: "",
  uf: "",
  tipo_contrato: "",
  tranche: "",
  com_valor: false,
  incluir_inativos: false,
};

function formatBRL(n) {
  if (n === 0 || n == null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(n);
}

function formatPct(decimal) {
  // backend devolve string tipo "0.8000". Converte para "80,00%".
  const n = parseFloat(decimal);
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export default function ContratosBrowser({ onPick }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [contratos, setContratos] = useState([]);
  const [facets, setFacets] = useState({ ufs: [], tranches: [], tipos: [] });
  const [totalNoBanco, setTotalNoBanco] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pickingId, setPickingId] = useState(null);
  const [pickError, setPickError] = useState("");

  // Facets — derivadas de uma resposta SEM filtros aplicados, no mount.
  // Evita "filtro UF=SP esconde a opção AC do select" (dependência circular).
  useEffect(() => {
    let active = true;
    fetch("/api/contratos", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((data) => {
        if (!active) return;
        const ufs = [...new Set(data.map((c) => c.uf).filter(Boolean))].sort();
        const tranches = [...new Set(data.map((c) => c.tranche).filter(Boolean))].sort();
        const tipos = [...new Set(data.map((c) => c.tipo_contrato).filter(Boolean))].sort();
        setFacets({ ufs, tranches, tipos });
        setTotalNoBanco(data.length);
      })
      .catch(() => { /* facets ficam vazios, mas a tabela ainda funciona */ });
    return () => { active = false; };
  }, []);

  // Fetch principal — debounced + AbortController.
  useEffect(() => {
    const ctrl = new AbortController();
    const tid = setTimeout(async () => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== "" && v !== false && v != null) params.set(k, String(v));
      });
      try {
        const url = params.toString() ? `/api/contratos?${params}` : "/api/contratos";
        const r = await fetch(url, { credentials: "same-origin", signal: ctrl.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setContratos(await r.json());
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { clearTimeout(tid); ctrl.abort(); };
  }, [filters]);

  const algumFiltroAtivo = useMemo(
    () => Object.entries(filters).some(([_, v]) => v !== "" && v !== false),
    [filters]
  );

  const update = (key, val) => setFilters((f) => ({ ...f, [key]: val }));
  const limpar = () => setFilters(EMPTY_FILTERS);

  async function handlePick(contrato) {
    // F3-c (revisada 2026-05-12): clique seleciona o contrato como ativo na sessão
    // e leva o usuário de volta para a aba Upload. Equivalente a abrir o
    // ContratoSelector + confirmar, só que sem o passo do estado.
    if (contrato.ativo === false || pickingId) return;
    setPickingId(contrato.id);
    setPickError("");
    try {
      const r = await fetch("/api/session/contrato", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ contrato_id: contrato.id }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(payload.detail ?? `HTTP ${r.status}`);
      }
      const data = await r.json();
      onPick?.(data);
    } catch (e) {
      setPickError(`Falha ao trocar contrato: ${e.message}`);
      setPickingId(null);
    }
  }

  return (
    <section className="card contratos-browser-card">
      <div className="card-header">
        <div>
          <p className="section-kicker">Consulta</p>
          <h2 className="card-title">Contratos da base</h2>
        </div>
      </div>

      <div className="contratos-filter-bar">
        <input
          type="text"
          className="contratos-q"
          placeholder="Buscar por número ou sigla…"
          value={filters.q}
          onChange={(e) => update("q", e.target.value)}
        />
        <select value={filters.uf} onChange={(e) => update("uf", e.target.value)}>
          <option value="">UF: todas</option>
          {facets.ufs.map((u) => (
            <option key={u} value={u}>{u} — {UF_NOMES[u] ?? u}</option>
          ))}
        </select>
        <select value={filters.tipo_contrato} onChange={(e) => update("tipo_contrato", e.target.value)}>
          <option value="">Tipo: todos</option>
          {facets.tipos.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select value={filters.tranche} onChange={(e) => update("tranche", e.target.value)}>
          <option value="">Tranche: todas</option>
          {facets.tranches.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <label className="contratos-toggle">
          <input
            type="checkbox"
            checked={filters.com_valor}
            onChange={(e) => update("com_valor", e.target.checked)}
          />
          apenas com valor definido
        </label>
        <label className="contratos-toggle">
          <input
            type="checkbox"
            checked={filters.incluir_inativos}
            onChange={(e) => update("incluir_inativos", e.target.checked)}
          />
          incluir inativos
        </label>
        {algumFiltroAtivo && (
          <button type="button" className="btn-link" onClick={limpar}>
            Limpar filtros
          </button>
        )}
        <span className="contratos-count">
          {loading ? "Atualizando…" : `${contratos.length} de ${totalNoBanco} contratos`}
        </span>
      </div>

      {error && <p className="inline-error">{error}</p>}
      {pickError && <p className="inline-error">{pickError}</p>}

      {contratos.length === 0 && !loading ? (
        <div className="contratos-empty">
          <strong>Nenhum contrato corresponde aos filtros</strong>
          <p>Ajuste ou limpe os filtros para ver resultados.</p>
        </div>
      ) : (
        <div className="contratos-table-wrapper">
          <table className="contratos-table">
            <colgroup>
              <col className="col-cnt-num" />
              <col className="col-cnt-fornecedor" />
              <col className="col-cnt-uf" />
              <col className="col-cnt-tranche" />
              <col className="col-cnt-tipo" />
              <col className="col-cnt-valor" />
              <col className="col-cnt-cde" />
              <col className="col-cnt-pct" />
            </colgroup>
            <thead>
              <tr>
                <th>Contrato</th>
                <th>Distribuidora</th>
                <th>UF</th>
                <th>Tranche</th>
                <th>Tipo</th>
                <th className="right">Valor Contrato</th>
                <th className="right">Valor CDE</th>
                <th className="right">% CDE</th>
              </tr>
            </thead>
            <tbody>
              {contratos.map((c) => {
                const inativo = c.ativo === false;
                const isPicking = pickingId === c.id;
                const tooltip = inativo
                  ? "Contrato inativo — não pode ser selecionado"
                  : "Clique para selecionar este contrato e ir para Upload";
                return (
                  <tr
                    key={c.id}
                    className={`contrato-row${inativo ? " is-inactive" : ""}${isPicking ? " is-picking" : ""}`}
                    onClick={() => handlePick(c)}
                    title={tooltip}
                  >
                    <td className="cnt-num">{c.numero}</td>
                    <td>{c.sigla}</td>
                    <td>{c.uf ?? "—"}</td>
                    <td>{c.tranche ?? "—"}</td>
                    <td>{c.tipo_contrato}</td>
                    <td className="right">{formatBRL(parseFloat(c.valor_contrato))}</td>
                    <td className="right">{formatBRL(parseFloat(c.valor_cde))}</td>
                    <td className="right">{formatPct(c.participacao_cde)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
