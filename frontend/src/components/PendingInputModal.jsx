import { useState } from "react";

// F8b — labels humanos para os 11 campos do default_nf_template. Backend manda
// missing como lista de chaves; UI traduz pra português antes de renderizar.
const FIELD_LABELS = {
  numero_nf: "Número da NF",
  data_emissao: "Data de emissão",
  cnpj: "CNPJ",
  fornecedor: "Fornecedor",
  tipo_nota: "Tipo de nota",
  descricao: "Descrição",
  ncm: "NCM",
  quant: "Quantidade",
  preco_unitario: "Preço unitário",
  valor: "Valor total",
  contrato: "Contrato",
};

// Ordem canônica de renderização no form — identificadores no topo, depois
// metadados, depois detalhes do produto. Operador lê de cima pra baixo no
// mesmo fluxo que aparece no DANFE.
const ORDERED_FIELDS = [
  "numero_nf",
  "data_emissao",
  "cnpj",
  "fornecedor",
  "tipo_nota",
  "descricao",
  "ncm",
  "quant",
  "preco_unitario",
  "valor",
];

function fieldLabel(key) {
  return FIELD_LABELS[key] ?? key;
}

function formatInitialValue(value) {
  // O parser entrega valores às vezes como dicts canônicos {"cnpj": "..."}
  // já desencapsulados pelo backend, mas defensive aqui — se vier objeto,
  // achatamos.
  if (value == null) return "";
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
 * Direita: form com TODOS os campos como inputs editáveis. Campos que o
 * parser conseguiu extrair vêm pré-populados; campos em `missing` vêm
 * vazios e com marcador required. Operador pode corrigir qualquer um.
 * Strings vazias deixadas em campos não-required são descartadas no
 * backend (não sobrescrevem o prefilled).
 */
export default function PendingInputModal({ pending, onResolved, onCancelled }) {
  const { nfPendingId, uploadFileId, filename, prefilled = {}, missing = [] } = pending;

  // Set de campos required (operador precisa preencher) — derivado do missing
  // que o backend mandou.
  const missingSet = new Set(missing);

  // Campos exóticos enviados pelo backend (ex.: 'numero_de_produtos_nesta_nf')
  // que não estão na ordem canônica. Mostram no fim.
  const exoticMissing = missing.filter((f) => !ORDERED_FIELDS.includes(f));
  const allFields = [...ORDERED_FIELDS, ...exoticMissing];

  // Estado: valor de cada input. Inicializa com prefilled[field] (ou vazio
  // se em missing ou se parser não tinha).
  const [values, setValues] = useState(() => {
    const init = {};
    for (const f of allFields) {
      init[f] = formatInitialValue(prefilled[f]);
    }
    return init;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Salvar habilitado quando todos os campos required têm valor não-vazio.
  const allRequiredFilled = missing.every(
    (field) => (values[field] ?? "").trim().length > 0
  );

  function handleChange(field, value) {
    setValues((prev) => ({ ...prev, [field]: value }));
    if (error) setError("");
  }

  async function handleResolve() {
    if (!allRequiredFilled || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`/api/uploads/pending/${nfPendingId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ filled: values }),
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
            . Confira os demais campos extraídos e corrija se necessário.
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
            <div className="pending-modal-fields">
              {allFields.map((field) => {
                const isRequired = missingSet.has(field);
                return (
                  <div key={field} className="pending-modal-field">
                    <label htmlFor={`pending-${field}`} className="pending-modal-field-label">
                      {fieldLabel(field)}
                      {isRequired && <span className="pending-modal-required"> *</span>}
                    </label>
                    <input
                      id={`pending-${field}`}
                      type="text"
                      value={values[field] ?? ""}
                      onChange={(e) => handleChange(field, e.target.value)}
                      className={`pending-modal-input${isRequired ? " is-required" : ""}`}
                      disabled={submitting}
                      autoComplete="off"
                    />
                  </div>
                );
              })}
            </div>

            {error && <div className="pending-modal-error">{error}</div>}

            <div className="pending-modal-actions">
              <button
                type="button"
                className="pending-modal-btn-primary"
                onClick={handleResolve}
                disabled={!allRequiredFilled || submitting}
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
