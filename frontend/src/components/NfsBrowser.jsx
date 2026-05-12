import { useEffect, useMemo, useState } from "react";

import { exportNfsResumo } from "../lib/exportExcel";

/**
 * F3b — Consulta de NFs por contrato.
 *
 * Dropdown de contrato no topo + barra de filtros + tabela + footer com
 * contagem e soma. Lê `nf_entries.contrato_id` (populado a partir da F2).
 *
 * Decisões registradas em planning/F3b-consulta-nfs.html:
 * - F3b-a: trocar contrato no dropdown NÃO reseta os outros filtros.
 *          Botão "limpar filtros" disponível como reset explícito.
 * - F3b-b: ao montar, se houver contrato ativo na sessão (selectedContratoId),
 *          pré-seleciona no dropdown.
 */

const EMPTY_FILTERS = {
  q: "",
  data_inicio: "",
  data_fim: "",
  valor_min: "",
  valor_max: "",
  tipo_nota: "",
};

function parseBR(v) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  const s = String(v).replace(/\./g, "").replace(",", ".");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}

function formatBRL(n) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(n);
}

function describeContrato(c) {
  // Formato do item do dropdown: "sigla · tranche · tipo (numero) — N NFs no banco"
  // `nfs_count` vem do endpoint /api/contratos (F4 follow-up, 2026-05-12).
  const meta = [c.sigla, c.tranche, c.tipo_contrato].filter(Boolean).join(" · ");
  const count = typeof c.nfs_count === "number" ? c.nfs_count : 0;
  const label = `${count} ${count === 1 ? "NF" : "NFs"} no banco`;
  return `${meta} (${c.numero}) — ${label}`;
}

export default function NfsBrowser({ selectedContratoId }) {
  const [contratos, setContratos] = useState([]);
  const [contratoId, setContratoId] = useState(selectedContratoId ?? "");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [nfs, setNfs] = useState([]);
  const [tiposDisponiveis, setTiposDisponiveis] = useState([]);
  const [totalNoContrato, setTotalNoContrato] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Lista de contratos pra popular o dropdown — mount-only.
  useEffect(() => {
    let active = true;
    fetch("/api/contratos", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((data) => { if (active) setContratos(data); })
      .catch(() => { /* dropdown vazio = empty state ainda funciona */ });
    return () => { active = false; };
  }, []);

  // Facets (tipos disponíveis) + total do contrato — recarrega quando o
  // contrato muda. Fetch separado, sem outros filtros, para popular o select
  // "tipo" sem virar circular.
  useEffect(() => {
    let active = true;
    if (!contratoId) {
      setTiposDisponiveis([]);
      setTotalNoContrato(0);
      return;
    }
    fetch(`/api/nf-entries?contrato_id=${encodeURIComponent(contratoId)}`,
          { credentials: "same-origin" })
      .then((r) => r.json())
      .then((rows) => {
        if (!active) return;
        const tipos = [...new Set(rows.map((r) => r.tipo_nota).filter(Boolean))].sort();
        setTiposDisponiveis(tipos);
        setTotalNoContrato(rows.length);
      })
      .catch(() => { /* mantém facets vazias */ });
    return () => { active = false; };
  }, [contratoId]);

  // Fetch principal — debounced + AbortController.
  useEffect(() => {
    if (!contratoId) {
      setNfs([]);
      return;
    }
    const ctrl = new AbortController();
    const tid = setTimeout(async () => {
      setLoading(true);
      setError("");
      const params = new URLSearchParams();
      params.set("contrato_id", contratoId);
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== "" && v != null) params.set(k, v);
      });
      try {
        const r = await fetch(`/api/nf-entries?${params}`,
                             { credentials: "same-origin", signal: ctrl.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setNfs(data);
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { clearTimeout(tid); ctrl.abort(); };
  }, [contratoId, filters]);

  const soma = useMemo(
    () => nfs.reduce((acc, n) => acc + parseBR(n.valor_total), 0),
    [nfs]
  );

  const algumFiltroAtivo = useMemo(
    () => Object.values(filters).some((v) => v !== ""),
    [filters]
  );

  const update = (key, val) => setFilters((f) => ({ ...f, [key]: val }));
  const limpar = () => setFilters(EMPTY_FILTERS);

  const contratoSelecionado = useMemo(
    () => contratos.find((c) => c.id === contratoId),
    [contratos, contratoId]
  );

  return (
    <section className="card nfs-card">
      <div className="card-header">
        <div>
          <p className="section-kicker">Consulta</p>
          <h2 className="card-title">Notas fiscais por contrato</h2>
        </div>
        <button
          className="btn-ghost"
          type="button"
          disabled={nfs.length === 0}
          onClick={() => exportNfsResumo(nfs, contratoSelecionado?.numero)}
        >
          Exportar Excel
        </button>
      </div>

      <div className="nfs-picker">
        <label htmlFor="nfs-contrato">Contrato:</label>
        <select
          id="nfs-contrato"
          value={contratoId}
          onChange={(e) => setContratoId(e.target.value)}
        >
          <option value="">— Selecione um contrato —</option>
          {contratos.map((c) => (
            <option key={c.id} value={c.id}>{describeContrato(c)}</option>
          ))}
        </select>
      </div>

      {!contratoId ? (
        <div className="nfs-empty">
          <strong>Selecione um contrato para ver as NFs</strong>
          <p>Use o dropdown acima. Você pode filtrar por número, data, fornecedor, CNPJ, valor ou tipo após escolher.</p>
        </div>
      ) : (
        <>
          <div className="nfs-filter-bar">
            <input
              type="text"
              className="nfs-q"
              placeholder="Buscar (nº, fornecedor, CNPJ, descrição)…"
              value={filters.q}
              onChange={(e) => update("q", e.target.value)}
            />
            <div className="nfs-group">
              <span className="nfs-group-label">data:</span>
              <input
                type="date"
                value={filters.data_inicio}
                onChange={(e) => update("data_inicio", e.target.value)}
              />
              <span className="nfs-group-sep">até</span>
              <input
                type="date"
                value={filters.data_fim}
                onChange={(e) => update("data_fim", e.target.value)}
              />
            </div>
            <div className="nfs-group">
              <span className="nfs-group-label">valor:</span>
              <input
                type="number"
                step="0.01"
                placeholder="min"
                value={filters.valor_min}
                onChange={(e) => update("valor_min", e.target.value)}
              />
              <span className="nfs-group-sep">até</span>
              <input
                type="number"
                step="0.01"
                placeholder="max"
                value={filters.valor_max}
                onChange={(e) => update("valor_max", e.target.value)}
              />
            </div>
            <select
              value={filters.tipo_nota}
              onChange={(e) => update("tipo_nota", e.target.value)}
            >
              <option value="">Tipo: todos</option>
              {tiposDisponiveis.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            {algumFiltroAtivo && (
              <button type="button" className="btn-link" onClick={limpar}>
                Limpar filtros
              </button>
            )}
            <span className="nfs-count">
              {loading ? "Atualizando…" : `${nfs.length} de ${totalNoContrato} NFs`}
            </span>
          </div>

          {error && <p className="inline-error">{error}</p>}

          {nfs.length === 0 && !loading ? (
            <div className="nfs-empty">
              <strong>Nenhuma NF encontrada</strong>
              <p>
                {algumFiltroAtivo
                  ? "Ajuste ou limpe os filtros."
                  : "Este contrato não tem NFs no banco. NFs anteriores à F2 podem não estar associadas ao contrato."}
              </p>
            </div>
          ) : (
            <div className="nfs-table-wrapper">
              <table className="nfs-table">
                <colgroup>
                  <col className="col-nfs-num" />
                  <col className="col-nfs-data" />
                  <col className="col-nfs-fornecedor" />
                  <col className="col-nfs-cnpj" />
                  <col className="col-nfs-descricao" />
                  <col className="col-nfs-valor" />
                  <col className="col-nfs-tipo" />
                  <col className="col-nfs-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Número</th>
                    <th>Emissão</th>
                    <th>Fornecedor</th>
                    <th>CNPJ</th>
                    <th>Descrição</th>
                    <th className="right">Valor total</th>
                    <th>Tipo</th>
                    <th className="center">PDF</th>
                  </tr>
                </thead>
                <tbody>
                  {nfs.map((nf) => {
                    const hasPdf = Boolean(nf.upload_file_id);
                    const pdfUrl = hasPdf
                      ? `/api/uploads/files/${encodeURIComponent(nf.upload_file_id)}/pdf`
                      : null;
                    return (
                      <tr key={nf.id}>
                        <td className="nfs-num" title={String(nf.numero_nf ?? "")}>{nf.numero_nf}</td>
                        <td title={String(nf.data_emissao ?? "")}>{nf.data_emissao}</td>
                        <td title={String(nf.fornecedor ?? "")}>{nf.fornecedor}</td>
                        <td className="nfs-num" title={String(nf.cnpj ?? "")}>{nf.cnpj}</td>
                        <td title={String(nf.descricao ?? "")}>{nf.descricao}</td>
                        <td className="right" title={String(nf.valor_total ?? "")}>{nf.valor_total}</td>
                        <td title={String(nf.tipo_nota ?? "")}>{nf.tipo_nota}</td>
                        <td className="nfs-actions">
                          <button
                            type="button"
                            className="icon-btn"
                            disabled={!hasPdf}
                            title={hasPdf ? "Abrir PDF em nova aba" : "PDF não disponível (anterior à F4)"}
                            onClick={() => hasPdf && window.open(pdfUrl, "_blank", "noopener,noreferrer")}
                          >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          </button>
                          <button
                            type="button"
                            className="icon-btn"
                            disabled={!hasPdf}
                            title={hasPdf ? "Baixar PDF" : "PDF não disponível (anterior à F4)"}
                            onClick={() => hasPdf && window.open(`${pdfUrl}?download=true`, "_blank", "noopener,noreferrer")}
                          >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                              <polyline points="7 10 12 15 17 10" />
                              <line x1="12" y1="15" x2="12" y2="3" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <div className="nfs-foot">
            <span><strong>{nfs.length}</strong> NF{nfs.length === 1 ? "" : "s"} filtrada{nfs.length === 1 ? "" : "s"} (de {totalNoContrato} no contrato)</span>
            <span>Soma: <strong>{formatBRL(soma)}</strong></span>
          </div>
        </>
      )}
    </section>
  );
}
