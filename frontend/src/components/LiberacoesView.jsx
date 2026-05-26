/**
 * Página estática de Liberações de parcelas (brainstorm/demo).
 *
 * Dados ilustrativos hardcoded — não consulta backend. Substitui o wireframe
 * da seção 04 de `design pagina liberacoes/F-liberacoes.html`. Para virar
 * feature real, ver as seções 06 (schema) e 09 (próximos passos) do mesmo HTML.
 */

const ESTADO_ATUAL = {
  comprovado_pct: 47,
  comprovado_valor: "R$ 5.875.000",
  comprovado_nfs: 312,
  fisico_pct: 35,
  fisico_sincronizado_em: "22/05/2026",
  proxima_parcela: "3ª",
  proxima_gatilho_pct: 30,
};

const PRECEDENCIA = [
  {
    rotulo: "Contrato N-1 · ECFS 099/2022",
    estado: "✓ 78% físico",
    detalhe: "Inspeção Final solicitada em 03/03/2026",
    ok: true,
  },
  {
    rotulo: "Contrato N-2 · ECFS 067/2020",
    estado: "✓ encerrado",
    detalhe: "Auditoria independente: 12/11/2025",
    ok: true,
  },
];

const PARCELAS = [
  {
    nome: "Liberação Inicial",
    valor: "R$ 2.500.000",
    gatilho: null,
    status: "done",
    meta: "Liberada em 12/01/2024",
  },
  {
    nome: "2ª Liberação",
    valor: "R$ 2.500.000",
    gatilho: "Fin/Fis 10%",
    status: "done",
    meta: "Liberada em 03/08/2024",
  },
  {
    nome: "3ª Liberação",
    valor: "R$ 2.500.000",
    gatilho: "Fin/Fis 30%",
    status: "ready",
    meta: "Fin 47% ≥ 30% ✓ · Fís 35% ≥ 30% ✓ · Precedência ✓",
    actionLabel: "Solicitar liberação →",
  },
  {
    nome: "4ª Liberação",
    valor: "R$ 1.250.000",
    gatilho: "Fin/Fis 50%",
    status: "blocked",
    meta: "Falta 3% financeiro · 15% físico",
  },
  {
    nome: "5ª · 6ª · Final",
    valor: null,
    gatilho: null,
    status: "collapsed",
    meta: "Recolhidas — expandir para ver detalhes",
  },
];

const STATUS_LABELS = {
  done: "Liberada",
  ready: null, // mostra botão no lugar do label
  blocked: "Bloqueada",
  collapsed: "⌄",
};

export default function LiberacoesView() {
  return (
    <div className="liberacoes-view">
      <section className="card lib-card lib-card--intro">
        <div className="card-header">
          <div>
            <h2 className="card-title">Liberações do contrato</h2>
          </div>
          <span className="section-badge">Modelo</span>
        </div>
        <p className="lib-intro-text">
          Ao solicitar liberação, você receberá a carta de solicitação no seu
          e-mail cadastrado. Assine e envie essa carta para{" "}
          <a href="mailto:gestaolpt@enbpar.gov.br">gestaolpt@enbpar.gov.br</a>{" "}
          junto com o Anexo II preenchido.
        </p>
      </section>

      <div className="lib-row2">
        {/* Card 1: Estado atual */}
        <section className="lib-card lib-state-card">
          <div className="lib-card-title">Estado atual</div>

          <div className="lib-bar-row">
            <span className="lib-bar-label">Comprovação financeira</span>
            <span className="lib-bar-pct">{ESTADO_ATUAL.comprovado_pct}%</span>
          </div>
          <div className="lib-bar">
            <span
              className="lib-bar-fill lib-bar-fill--clay"
              style={{ width: `${ESTADO_ATUAL.comprovado_pct}%` }}
            />
          </div>
          <div className="lib-bar-meta">
            {ESTADO_ATUAL.comprovado_valor} · {ESTADO_ATUAL.comprovado_nfs} NFs
          </div>

          <div className="lib-bar-row lib-bar-row--spaced">
            <span className="lib-bar-label">Avanço físico</span>
            <span className="lib-bar-pct">{ESTADO_ATUAL.fisico_pct}%</span>
          </div>
          <div className="lib-bar">
            <span
              className="lib-bar-fill lib-bar-fill--olive"
              style={{ width: `${ESTADO_ATUAL.fisico_pct}%` }}
            />
          </div>
          <div className="lib-bar-meta">
            Gerenciador · sinc. {ESTADO_ATUAL.fisico_sincronizado_em}
            <button type="button" className="lib-sync-btn" title="Sincronizar agora">↻</button>
          </div>

          <div className="lib-next">
            <span className="lib-next-label">Próxima parcela liberável</span>
            <span className="lib-next-value">
              {ESTADO_ATUAL.proxima_parcela}
            </span>
          </div>
        </section>

        {/* Card 2: Precedência */}
        <section className="lib-card lib-prec-card">
          <div className="lib-card-title">Precedência</div>

          {PRECEDENCIA.map((p) => (
            <div className="lib-prec-row" key={p.rotulo}>
              <div className="lib-prec-head">
                <span className="lib-prec-rotulo">{p.rotulo}</span>
                <span className={`lib-prec-estado${p.ok ? " lib-prec-estado--ok" : ""}`}>
                  {p.estado}
                </span>
              </div>
              <div className="lib-prec-detalhe">{p.detalhe}</div>
            </div>
          ))}

          <div className="lib-prec-warn">
            Próxima parcela (3ª) requer N-1 com prestação contas financeira final
            e N-2 com auditoria independente — ambos ✓
          </div>
        </section>
      </div>

      {/* Timeline */}
      <section className="lib-card lib-timeline-card">
        <div className="lib-card-title">Timeline de parcelas</div>

        {PARCELAS.map((p) => (
          <div className={`lib-tl-row lib-tl-row--${p.status}`} key={p.nome}>
            <span className={`lib-tl-dot lib-tl-dot--${p.status}`} />
            <div className="lib-tl-body">
              <div className="lib-tl-name">
                {p.nome}
                {p.valor && <span className="lib-tl-valor"> · {p.valor}</span>}
                {p.gatilho && <span className="lib-tl-gatilho"> ({p.gatilho})</span>}
              </div>
              <div className="lib-tl-meta">{p.meta}</div>
            </div>
            {p.status === "ready" ? (
              <button
                type="button"
                className="lib-tl-action"
                onClick={() => {
                  // Demo estática: drawer real ainda não existe.
                  alert(
                    "Drawer 'Solicitar liberação' — não implementado nesta demo.\n\n" +
                    "Ver design pagina liberacoes/F-liberacoes.html seção 05."
                  );
                }}
              >
                {p.actionLabel}
              </button>
            ) : (
              <span className={`lib-tl-status lib-tl-status--${p.status}`}>
                {STATUS_LABELS[p.status]}
              </span>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
