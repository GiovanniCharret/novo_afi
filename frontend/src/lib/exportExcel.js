import * as XLSX from "xlsx";

// Colunas canônicas de exportação — idênticas entre a tela de Upload
// (tabela_persistida do Anexo I) e a aba Notas (F3b). Ordem espelha a
// tabela_persistida do Anexo I. Ambas as telas consomem `/api/nf-entries`,
// que serializa as 11 colunas, então o mesmo builder serve às duas.
function buildWorksheet(rows) {
  const worksheetRows = rows.map((row) => ({
    descricao: row.descricao,
    ncm: row.ncm,
    quant: row.quantidade,
    preco_unitario: row.preco_unitario,
    numero_nf: row.numero_nf,
    tipo_nota: row.tipo_nota,
    data_emissao: row.data_emissao,
    cnpj: row.cnpj,
    fornecedor: row.fornecedor,
    valor: row.valor_total,
    contrato: row.contrato,
  }));
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(worksheetRows), "Notas");
  return workbook;
}

/**
 * Exporta NFs da tela de Upload (tabela_persistida do Anexo I).
 */
export function exportEntriesCompletas(rows) {
  XLSX.writeFile(buildWorksheet(rows), "tabela_persistida_notas.xlsx");
}

/**
 * Exporta NFs da aba Notas (F3b). Mesmas colunas e ordem do Upload —
 * só o nome do arquivo difere, incluindo o contrato para contexto.
 */
export function exportNfsResumo(rows, contratoNumero) {
  const safeContrato = (contratoNumero || "sem-contrato").replace(/[^a-zA-Z0-9._-]/g, "_");
  XLSX.writeFile(buildWorksheet(rows), `notas_${safeContrato}.xlsx`);
}
