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

// Dicas de formato (placeholder) — evitam que o operador digite num formato que
// o /resolve rejeita com 422 (parse_brazilian_decimal / parse_brazilian_date).
const FIELD_HINTS = {
  numero_nf: "ex.: 000012259",
  data_emissao: "DD/MM/AAAA",
  cnpj: "00.000.000/0000-00",
  quant: "ex.: 1",
  preco_unitario: "ex.: 1.234,56",
  valor: "ex.: 1.234,56",
};

// Ordem canônica de renderização no form — identificadores no topo, depois
// metadados, depois detalhes do produto. Operador lê de cima pra baixo no
// mesmo fluxo que aparece no DANFE. Todos são colunas NOT NULL em nf_entries.
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

// Campos numéricos em formato BR — validados client-side (espelham
// normalization.parse_brazilian_decimal no backend).
const DECIMAL_FIELDS = new Set(["quant", "preco_unitario", "valor"]);

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

function isBlank(value) {
  return (value ?? "").trim().length === 0;
}

// Espelha normalization.parse_brazilian_decimal: remove '.', troca ',' por '.'
// e tenta converter para número. Pré-check client-side do que o backend aceita.
function brDecimalIsValid(value) {
  const sanitized = value.trim().replace(/\./g, "").replace(",", ".");
  if (sanitized === "") return false;
  return Number.isFinite(Number(sanitized));
}

// Espelha parse_brazilian_date: o backend exige um DD/MM/AAAA no texto.
function brDateIsValid(value) {
  return /\b\d{2}\/\d{2}\/\d{4}\b/.test(value.trim());
}

// Erro de formato de um campo preenchido (string vazia = ok aqui; o vazio é
// tratado pelo gate de obrigatórios). Só valida campos que o /resolve rejeita
// com 422 — texto livre não é validado.
function fieldError(key, value) {
  if (isBlank(value)) return "";
  if (DECIMAL_FIELDS.has(key)) {
    return brDecimalIsValid(value)
      ? ""
      : "Use número no formato brasileiro (ex.: 1.234,56).";
  }
  if (key === "data_emissao") {
    return brDateIsValid(value) ? "" : "Use o formato DD/MM/AAAA.";
  }
  return "";
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
 * Direita: form com TODOS os campos como inputs editáveis.
 *
 * Obrigatoriedade (revisão 2026-05-19): as 11 colunas do template são NOT
 * NULL, então QUALQUER campo em branco bloqueia o submit — não só os que o
 * backend listou em `missing`. Necessário porque o caminho de OCR (PDF
 * escaneado) falha vários campos mas o parser reporta um por vez; confiar só
 * em `missing` deixava o operador salvar com campos vazios e levar 422.
 */
export default function PendingInputModal({ pending, onResolved, onCancelled }) {
  const { nfPendingId, uploadFileId, filename, prefilled = {}, missing = [] } = pending;

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
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  // Quantos campos o parser realmente extraiu — define o tom do subtítulo.
  const prefilledCount = allFields.filter(
    (f) => !isBlank(formatInitialValue(prefilled[f]))
  ).length;

  // Campos ainda em branco (bloqueiam o submit e ganham marcador *).
  const blankFields = allFields.filter((f) => isBlank(values[f]));

  // Erros de formato dos campos preenchidos.
  const fieldErrors = {};
  for (const f of allFields) {
    const err = fieldError(f, values[f]);
    if (err) fieldErrors[f] = err;
  }

  // Salvar habilitado quando nada está em branco e nada tem erro de formato.
  const canSubmit = blankFields.length === 0 && Object.keys(fieldErrors).length === 0;

  function handleChange(field, value) {
    setValues((prev) => ({ ...prev, [field]: value }));
    if (error) setError("");
  }

  async function handleResolve() {
    if (!canSubmit || submitting) return;
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
            {prefilledCount === 0
              ? "O parser não conseguiu extrair os campos desta NF — provavelmente um PDF escaneado. Preencha os campos conferindo o documento ao lado."
              : "O parser extraiu parte dos campos desta NF. Preencha os que estão em branco (marcados com *) e confira os demais com o documento ao lado."}
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
                const needsValue = isBlank(values[field]);
                const formatErr = fieldErrors[field];
                const inputClass =
                  "pending-modal-input" +
                  (needsValue ? " is-required" : "") +
                  (formatErr ? " has-error" : "");
                const errId = formatErr ? `pending-${field}-error` : undefined;
                return (
                  <div key={field} className="pending-modal-field">
                    <label htmlFor={`pending-${field}`} className="pending-modal-field-label">
                      {fieldLabel(field)}
                      {needsValue && <span className="pending-modal-required"> *</span>}
                    </label>
                    <input
                      id={`pending-${field}`}
                      type="text"
                      value={values[field] ?? ""}
                      onChange={(e) => handleChange(field, e.target.value)}
                      className={inputClass}
                      placeholder={FIELD_HINTS[field] || ""}
                      disabled={submitting}
                      autoComplete="off"
                      aria-invalid={formatErr ? "true" : undefined}
                      aria-describedby={errId}
                    />
                    {formatErr && (
                      <div id={errId} className="pending-modal-field-error">
                        {formatErr}
                      </div>
                    )}
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
                disabled={!canSubmit || submitting}
              >
                {submitting ? "Enviando…" : "Salvar e continuar"}
              </button>
              {!confirmingCancel && (
                <button
                  type="button"
                  className="pending-modal-btn-ghost"
                  onClick={() => setConfirmingCancel(true)}
                  disabled={submitting}
                >
                  Cancelar batch
                </button>
              )}
            </div>

            {confirmingCancel && (
              <div className="pending-modal-cancel-confirm">
                <span>
                  Cancelar interrompe este upload e descarta os PDFs do lote
                  que ainda não foram processados. Tem certeza?
                </span>
                <div className="pending-modal-cancel-confirm-actions">
                  <button
                    type="button"
                    className="pending-modal-btn-danger"
                    onClick={handleCancel}
                    disabled={submitting}
                  >
                    {submitting ? "Cancelando…" : "Confirmar cancelamento"}
                  </button>
                  <button
                    type="button"
                    className="pending-modal-btn-ghost"
                    onClick={() => setConfirmingCancel(false)}
                    disabled={submitting}
                  >
                    Voltar
                  </button>
                </div>
              </div>
            )}

            <p className="pending-modal-foot">
              Campos marcados com * estão em branco e são obrigatórios. Todos
              os campos podem ser corrigidos conferindo o PDF ao lado.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
