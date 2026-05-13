import { useEffect, useState } from "react";

/**
 * F6 — Totais por contrato. Versão compacta horizontal (2026-05-13).
 *
 * Layout em 3 colunas: NFs distintas | vs. contrato (barra) | vs. CDE (barra).
 * Sem subtítulo de contrato (info redundante com o dropdown acima).
 * Aparência: discreta, alinhada com o resto da tela, sem destaque pesado.
 *
 * Recarrega no mount e quando o contrato muda. Sem refresh signal externo —
 * o componente vive dentro do NfsBrowser que remonta a cada switch de aba.
 */

function formatBRL(n) {
  if (n == null || isNaN(n)) return "R$ 0,00";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(n);
}

function formatPct(decimal) {
  if (decimal == null || isNaN(decimal)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(decimal);
}

export default function TotalizadoresCard({ contrato }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!contrato?.id) {
      setData(null);
      return;
    }
    let active = true;
    const ctrl = new AbortController();
    (async () => {
      setLoading(true);
      setError("");
      try {
        const r = await fetch(
          `/api/contratos/${encodeURIComponent(contrato.id)}/totais`,
          { credentials: "same-origin", signal: ctrl.signal }
        );
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const payload = await r.json();
        if (active) setData(payload);
      } catch (e) {
        if (e.name !== "AbortError" && active) setError(e.message);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; ctrl.abort(); };
  }, [contrato?.id]);

  if (!contrato) return null;
  if (error) {
    return (
      <div className="totais-strip">
        <p className="inline-error">Falha ao carregar totais: {error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="totais-strip">
        <p className="section-kicker">Totais</p>
        <p className="totais-loading">{loading ? "Carregando…" : ""}</p>
      </div>
    );
  }

  const soma = parseFloat(data.soma_nfs_enviadas);
  const valorContrato = parseFloat(data.valor_contrato);
  const valorCde = parseFloat(data.valor_cde);
  const participacaoCde = parseFloat(data.participacao_cde);
  const pctContrato = data.pct_enviado_sobre_contrato;
  const pctCde = data.pct_enviado_sobre_cde;
  const semValor = pctContrato === null && pctCde === null;

  return (
    <div className="totais-strip">
      <p className="section-kicker">Totais</p>

      {semValor ? (
        <div className="totais-grid totais-grid--empty">
          <div className="totais-cell totais-nfs">
            <strong>{data.total_nfs_no_banco}</strong> NF{data.total_nfs_no_banco === 1 ? "" : "s"} distinta{data.total_nfs_no_banco === 1 ? "" : "s"} no banco
          </div>
          <div className="totais-cell totais-empty-msg">
            Contrato sem valor definido — percentuais indisponíveis.
          </div>
        </div>
      ) : (
        <div className="totais-grid">
          <div className="totais-cell totais-nfs">
            <strong>{data.total_nfs_no_banco}</strong> NF{data.total_nfs_no_banco === 1 ? "" : "s"} distinta{data.total_nfs_no_banco === 1 ? "" : "s"} no banco
          </div>

          <div className="totais-cell totais-bar-block">
            <div className="totais-bar-head">
              <span className="totais-bar-label">vs. contrato</span>
              <span className="totais-bar-pct">{formatPct(pctContrato)}</span>
            </div>
            <div className="totais-bar">
              <span
                className="totais-bar-fill"
                style={{ width: `${Math.min(100, (pctContrato ?? 0) * 100)}%` }}
              />
            </div>
            <div className="totais-bar-meta">{formatBRL(soma)} de {formatBRL(valorContrato)}</div>
          </div>

          <div className="totais-cell totais-bar-block">
            <div className="totais-bar-head">
              <span className="totais-bar-label">vs. CDE</span>
              <span className="totais-bar-pct">{formatPct(pctCde)}</span>
            </div>
            <div className="totais-bar">
              <span
                className="totais-bar-fill is-cde"
                style={{ width: `${Math.min(100, (pctCde ?? 0) * 100)}%` }}
              />
            </div>
            <div className="totais-bar-meta">
              {formatBRL(soma)} de {formatBRL(valorCde)} ({formatPct(participacaoCde)} do contrato)
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
