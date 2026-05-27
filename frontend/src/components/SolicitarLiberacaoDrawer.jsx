import { useEffect, useRef, useState } from "react";

const CONTRATO_CODIGO_FALLBACK = "ECFS-123-2024";

function formatBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

function DropZone({ file, accept, hint, onPick, onClear }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const handlePick = (e) => {
    const f = e.target.files?.[0];
    if (f) onPick(f);
    e.target.value = "";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onPick(f);
  };

  if (file) {
    return (
      <div className="lib-drawer-filled">
        <span className="lib-drawer-icon" aria-hidden="true">📎</span>
        <div className="lib-drawer-filled-info">
          <div className="lib-drawer-filename">{file.name}</div>
          <div className="lib-drawer-hint">{formatBytes(file.size)}</div>
        </div>
        <button
          type="button"
          className="lib-drawer-clear"
          onClick={onClear}
          title="Remover"
        >
          ✕
        </button>
      </div>
    );
  }

  return (
    <div
      className={`lib-drawer-drop${isDragging ? " is-dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={handlePick}
      />
      <div className="lib-drawer-drop-icon" aria-hidden="true">⬆</div>
      <div className="lib-drawer-drop-text">
        Arraste o arquivo ou{" "}
        <span className="lib-drawer-drop-link">clique para selecionar</span>
      </div>
      <div className="lib-drawer-drop-hint">{hint}</div>
    </div>
  );
}

export default function SolicitarLiberacaoDrawer({
  parcela,
  estadoAtual,
  contratoCodigo = CONTRATO_CODIGO_FALLBACK,
  onClose,
}) {
  const [signedCarta, setSignedCarta] = useState(null);
  const [anexoII, setAnexoII] = useState(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!parcela) return null;

  const canSubmit = signedCarta && anexoII && !sending;
  const oficioFilename = `oficio_${contratoCodigo}_parcela-${parcela.numero}.pdf`;

  const handleDownload = () => {
    alert(
      `Demo: download do ofício '${oficioFilename}' não implementado.\n` +
        "Em produção, o backend gera o PDF pré-preenchido."
    );
  };

  const handleSubmit = () => {
    if (!canSubmit) return;
    setSending(true);
    setTimeout(() => {
      alert(
        `Demo: solicitação da ${parcela.nome} enviada.\n\n` +
          `• Carta assinada: ${signedCarta.name}\n` +
          `• Anexo II: ${anexoII.name}\n\n` +
          "Em produção, um e-mail de confirmação seria enviado para sua caixa e " +
          "para gestaolpt@enbpar.gov.br."
      );
      setSending(false);
      onClose();
    }, 400);
  };

  return (
    <>
      <div className="lib-drawer-backdrop" onClick={onClose} />
      <aside
        className="lib-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lib-drawer-title"
      >
        <header className="lib-drawer-header">
          <div>
            <h3 id="lib-drawer-title">Solicitar {parcela.nome}</h3>
            <span className="lib-drawer-sub">{contratoCodigo}</span>
          </div>
          <button
            type="button"
            className="lib-drawer-close"
            onClick={onClose}
            title="Fechar (Esc)"
          >
            ✕
          </button>
        </header>

        <div className="lib-drawer-body">
          <div className="lib-drawer-field">
            <div className="lib-drawer-label">Valor</div>
            <div className="lib-drawer-value">
              <strong>{parcela.valor}</strong>
              {parcela.pctContrato && ` (${parcela.pctContrato})`}
            </div>
          </div>

          <div className="lib-drawer-field">
            <div className="lib-drawer-label">
              Snapshot no momento da solicitação
            </div>
            <div className="lib-drawer-value">
              Comprovação financeira{" "}
              <strong>{estadoAtual.comprovado_pct}%</strong> · Avanço físico{" "}
              <strong>{estadoAtual.fisico_pct}%</strong> · Precedência{" "}
              <strong>OK</strong>
            </div>
          </div>

          <div className="lib-drawer-field">
            <div className="lib-drawer-label">
              Passo 1 · Carta de solicitação (gerada)
            </div>
            <div className="lib-drawer-download">
              <span className="lib-drawer-icon" aria-hidden="true">📄</span>
              <div className="lib-drawer-download-info">
                <div className="lib-drawer-filename">{oficioFilename}</div>
                <div className="lib-drawer-hint">
                  4 páginas · imprima, assine e devolva no Passo 2
                </div>
              </div>
              <button
                type="button"
                className="lib-drawer-download-btn"
                onClick={handleDownload}
              >
                Baixar ↓
              </button>
            </div>
          </div>

          <div className="lib-drawer-field">
            <div className="lib-drawer-label">
              Passo 2 · Carta assinada{" "}
              <span className="lib-drawer-req">(obrigatório)</span>
            </div>
            <DropZone
              file={signedCarta}
              accept="application/pdf"
              hint="PDF · até 20 MB · pode ser o mesmo arquivo do Passo 1, assinado"
              onPick={setSignedCarta}
              onClear={() => setSignedCarta(null)}
            />
          </div>

          <div className="lib-drawer-field">
            <div className="lib-drawer-label">
              Passo 3 · Anexo II preenchido{" "}
              <span className="lib-drawer-req">(obrigatório)</span>
            </div>
            <DropZone
              file={anexoII}
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              hint="XLSX · até 5 MB"
              onPick={setAnexoII}
              onClear={() => setAnexoII(null)}
            />
          </div>
        </div>

        <footer className="lib-drawer-footer">
          <div className="lib-drawer-actions">
            <button
              type="button"
              className="lib-drawer-btn"
              onClick={onClose}
              disabled={sending}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="lib-drawer-btn lib-drawer-btn--primary"
              disabled={!canSubmit}
              onClick={handleSubmit}
            >
              {sending ? "Enviando…" : "Enviar solicitação"}
            </button>
          </div>
          {(!signedCarta || !anexoII) && (
            <div className="lib-drawer-hint-foot">
              Anexe a carta assinada e o Anexo II para habilitar o envio
            </div>
          )}
        </footer>
      </aside>
    </>
  );
}
