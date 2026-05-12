import * as XLSX from "xlsx";

/**
 * Exporta NFs no formato completo da tabela_persistida (tela de upload).
 * Inclui colunas extras como ncm/quant/preco_unitario que vêm do raw_payload.
 */
export function exportEntriesCompletas(rows) {
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
  XLSX.writeFile(workbook, "tabela_persistida_notas.xlsx");
}

/**
 * Exporta NFs no formato resumido da aba Notas (F3b).
 * Só as colunas visíveis na tabela. Nome do arquivo inclui o contrato.
 */
export function exportNfsResumo(rows, contratoNumero) {
  const worksheetRows = rows.map((row) => ({
    numero_nf: row.numero_nf,
    data_emissao: row.data_emissao,
    fornecedor: row.fornecedor,
    cnpj: row.cnpj,
    descricao: row.descricao,
    valor_total: row.valor_total,
    tipo_nota: row.tipo_nota,
  }));
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(worksheetRows), "Notas");
  const safeContrato = (contratoNumero || "sem-contrato").replace(/[^a-zA-Z0-9._-]/g, "_");
  XLSX.writeFile(workbook, `notas_${safeContrato}.xlsx`);
}
