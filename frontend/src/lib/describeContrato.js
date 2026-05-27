/**
 * Formato canônico de descrição de contrato usado no app inteiro.
 * Resultado: `SIGLA UF · Xª Tranche · LPT (ECFS 123/2024)`.
 * UF colado na sigla sem separador `·` porque é o pacote de identificação
 * primária do contrato (executor + estado) — o operador procura primeiro
 * por isso. Se a UF estiver ausente, cai pra `SIGLA · Xª Tranche · ...`.
 *
 * Usado no topbar (App.jsx) — contrato ativo na sessão. Após a refatoração
 * de 2026-05-27, deixou de ser usado no dropdown da Notas (removido).
 */
export function describeContrato(c) {
  const siglaUf = [c.sigla, c.uf].filter(Boolean).join(" ");
  const meta = [siglaUf, c.tranche, c.tipo_contrato].filter(Boolean).join(" · ");
  return `${meta} (${c.numero})`;
}
