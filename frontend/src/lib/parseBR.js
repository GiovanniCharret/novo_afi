/**
 * Converte uma string em formato brasileiro (`"1.234,56"`) para Number.
 * Aceita também Numbers (passa direto) e null/undefined (→ 0).
 *
 * Atenção: assume formato BR (separador de milhar `.`, decimal `,`). NÃO usar
 * para parsear strings decimais "puras" (`"1234.56"`) — para essas, use
 * `parseFloat` direto. O endpoint `/api/nf-entries` retorna BR (vem do
 * raw_payload do parser); o endpoint `/api/contratos/{id}/totais` retorna
 * decimais "puras" (via `str(Decimal)`).
 */
export function parseBR(v) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  const s = String(v).replace(/\./g, "").replace(",", ".");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}
