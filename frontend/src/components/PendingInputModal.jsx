import { useState } from "react";

// F8b — labels humanos para os 11 campos do default_nf_template. Backend manda
// missing como lista de chaves; UI traduz pra português antes de renderizar.
const FIELD_LABELS = {
  cnpj: "CNPJ",
  fornecedor: "Fornecedor",
  data_emissao: "Data de emissão",
  numero_nf: "Número da NF",
  descricao: "Descrição",
  valor: "Valor total",
  ncm: "NCM",
  quant: "Quantidade",
  preco_unitario: "Preço unitário",
  tipo_nota: "Tipo de nota",
  contrato: "Contrato",
};

function fieldLabel(key) {
  return FIELD_LABELS[key] ?? key;
}

function formatPrefilledValue(value) {
  // O parser entrega valores às vezes como dicts canônicos {"cnpj": "..."}
  // já desencapsulados pela B1, mas defensive aqui — se vier objeto, achatamos.
  if (value == null) return "—";
  if (typeof value === "object") {
    const keys = Object.keys(value);
    if (keys.length === 1) return String(value[keys[0]]);
    return JSON.stringify(value);
  }
  return String(value);
}

/**
 * F8b — modal interativo de preenchimento de NF (Fase C1).
 *
 * Aberto quando o SSE emite `file_pending_input`. Bloqueia o batch até que
 * o operador clique "Salvar e continuar" (POST /resolve) ou "Cancelar batch"
 * (POST /cancel). O backend só destrava o generator SSE após uma dessas
 * chamadas — o modal não fecha por ESC ou clique fora, intencionalmente.
 *
 * Layout: split 2 colunas. Esquerda: PDF inline via iframe da rota F4.
 * Direita: bloco prefilled (read-only) + inputs para campos faltantes +
 * ações.
 */
export default function PendingInputModal({ pending, onResolved, onCancelled }) {
  const { nfPendingId, uploadFileId, filename, prefilled = {}, missing = [] } = pending;

  const [filled, setFilled] = useState(() =>
    Object.fromEntries(missing.map((field) => [field, ""]))
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const allFilled = missing.every((field) => (filled[field] ?? "").trim().length > 0);

  function handleChange(field, value) {
    setFilled((prev) => ({ ...prev, [field]: value }));
    if (error) setError("");
  }

  async function handleResolve() {
    if (!allFilled || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`/api/uploads/pending/${nfPendingId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ filled }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      onResolved();
    } catch (err) {
      setError(err.message || "Falha ao salvar.");
      setSubmitting(false);
    }
  }

  async function handleCancel() {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`/api/uploads/pending/${nfPendingId}/cancel`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${response.status}`);
      }
      onCancelled();
    } catch (err) {
      setError(err.message || "Falha ao cancelar.");
      setSubmitting(false);
    }
  }

  const prefilledEntries = Object.entries(prefilled).filter(([, v]) => v != null && v !== "");

  return (
    <div className="pending-modal-overlay" role="dialog" aria-modal="true">
      <div className="pending-modal">
        <div className="pending-modal-header">
          <div className="pending-modal-eyebrow">Preenchimento necessário</div>
          <h2 className="pending-modal-title">{filename}</h2>
          <p className="pending-modal-subtitle">
            O parser identificou esta NF mas não conseguiu extrair{" "}
            {missing.length === 1
              ? `o campo "${fieldLabel(missing[0])}"`
              : `${missing.length} campos obrigatórios`}
            .
          </p>
        </div>

        <div className="pending-modal-body">
          <div className="pending-modal-pdf">
            <iframe
              src={`/api/uploads/files/${uploadFileId}/pdf`}
              title={`PDF de ${filename}`}
              className="pending-modal-iframe"
            />
            <a
              href={`/api/uploads/files/${uploadFileId}/pdf`}
              target="_blank"
              rel="noreferrer"
              className="pending-modal-pdf-link"
            >
              Abrir em nova aba
            </a>
          </div>

          <div className="pending-modal-form">
            {prefilledEntries.length > 0 && (
              <div className="pending-modal-prefilled">
                <div className="pending-modal-prefilled-label">Já extraído pelo parser</div>
                {prefilledEntries.map(([key, value]) => (
                  <div key={key} className="pending-modal-prefilled-row">
                    <span className="pending-modal-prefilled-k">{fieldLabel(key)}</span>
                    <span className="pending-modal-prefilled-v">{formatPrefilledValue(value)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="pending-modal-fields">
              {missing.map((field) => (
                <div key={field} className="pending-modal-field">
                  <label htmlFor={`pending-${field}`} className="pending-modal-field-label">
                    {fieldLabel(field)} <span className="pending-modal-required">*</span>
                  </label>
                  <input
                    id={`pending-${field}`}
                    type="text"
                    value={filled[field] ?? ""}
                    onChange={(e) => handleChange(field, e.target.value)}
                    className="pending-modal-input"
                    disabled={submitting}
                    autoComplete="off"
                  />
                </div>
              ))}
            </div>

            {error && <div className="pending-modal-error">{error}</div>}

            <div className="pending-modal-actions">
              <button
                type="button"
                className="pending-modal-btn-primary"
                onClick={handleResolve}
                disabled={!allFilled || submitting}
              >
                {submitting ? "Enviando…" : "Salvar e continuar"}
              </button>
              <button
                type="button"
                className="pending-modal-btn-ghost"
                onClick={handleCancel}
                disabled={submitting}
              >
                Cancelar batch
              </button>
            </div>

            <p className="pending-modal-foot">
              Cancelar interrompe este upload e descarta os PDFs que ainda não
              foram processados.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
