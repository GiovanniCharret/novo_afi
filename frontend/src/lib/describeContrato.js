/**
 * Formato canônico de descrição de contrato usado no app inteiro.
 * Resultado: `SIGLA · Xª Tranche · LPT (ECFS 123/2024)`.
 *
 * Usado em:
 * - Topbar (App.jsx) — contrato ativo na sessão.
 * - Dropdown da aba Notas (NfsBrowser) — wrapped por NfsBrowser que adiciona
 *   " — N NFs no banco" no fim.
 * - Tooltip / etiqueta no ContratosBrowser ao trocar contrato a partir de F3.
 */
export function describeContrato(c) {
  const meta = [c.sigla, c.tranche, c.tipo_contrato].filter(Boolean).join(" · ");
  return `${meta} (${c.numero})`;
}
