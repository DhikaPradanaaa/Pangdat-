import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/Pangdat/output/olist_data_quality_final";
const meta = path.join(root, "metadata");
const outputPath = path.join(root, "quality_report.xlsx");
const previewDir = "D:/Pangdat/tmp/quality_report_previews";
const fontFamily = "Arial";

function parseCSV(text) {
  text = text.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const headers = rows.shift() ?? [];
  return rows
    .filter((r) => r.some((value) => value !== ""))
    .map((r) => Object.fromEntries(headers.map((header, index) => [header, r[index] ?? ""])));
}

async function readCSV(filename) {
  return parseCSV(await fs.readFile(path.join(meta, filename), "utf8"));
}

function numberOrBlank(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : value;
}

function columnLetter(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function styleTitle(sheet, lastColumn) {
  sheet.getRange(`A2:${lastColumn}2`).format.font = {
    name: fontFamily,
    size: 14,
    bold: true,
    color: "#1F2937",
  };
  sheet.getRange(`A3:${lastColumn}3`).format.fill = "#1F4E78";
  sheet.getRange(`A3:${lastColumn}3`).format.rowHeight = 3;
}

function applyTableStyle(sheet, headerRange, bodyRange) {
  headerRange.format = {
    fill: "#1F4E78",
    font: { name: fontFamily, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "inside", style: "thin", color: "#FFFFFF" },
  };
  if (bodyRange) {
    bodyRange.format.font = { name: fontFamily, size: 10, color: "#1F2937" };
    bodyRange.format.verticalAlignment = "center";
    bodyRange.format.borders = {
      insideHorizontal: { style: "thin", color: "#E5E7EB" },
      bottom: { style: "thin", color: "#D1D5DB" },
    };
  }
}

function writeDataSheet(workbook, options) {
  const { name, title, columns, rows, numericColumns = [], wrapColumns = [], tabColor = null } = options;
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  if (tabColor) sheet.tabColor = tabColor;
  sheet.getRange("A2").values = [[title]];
  const lastColumn = columnLetter(columns.length - 1);
  styleTitle(sheet, lastColumn);

  const headerRow = 5;
  const values = [columns.map((column) => column.label)];
  for (const row of rows) {
    values.push(columns.map((column) => {
      const value = row[column.key] ?? "";
      return numericColumns.includes(column.key) ? numberOrBlank(value) : value;
    }));
  }
  const lastRow = headerRow + values.length - 1;
  const range = sheet.getRange(`A${headerRow}:${lastColumn}${lastRow}`);
  range.values = values;
  const headerRange = sheet.getRange(`A${headerRow}:${lastColumn}${headerRow}`);
  const bodyRange = lastRow > headerRow ? sheet.getRange(`A${headerRow + 1}:${lastColumn}${lastRow}`) : null;
  applyTableStyle(sheet, headerRange, bodyRange);
  headerRange.format.rowHeight = 30;
  sheet.freezePanes.freezeRows(headerRow);

  for (let i = 0; i < columns.length; i++) {
    const column = columns[i];
    const letter = columnLetter(i);
    const maxLength = Math.max(
      column.label.length,
      ...rows.slice(0, 500).map((row) => String(row[column.key] ?? "").length),
    );
    let width = Math.min(Math.max(maxLength + 2, 11), column.maxWidth ?? 30);
    if (column.width) width = column.width;
    sheet.getRange(`${letter}${headerRow}:${letter}${lastRow}`).format.columnWidth = width;
    if (wrapColumns.includes(column.key) && lastRow > headerRow) {
      sheet.getRange(`${letter}${headerRow + 1}:${letter}${lastRow}`).format.wrapText = true;
    }
    if (numericColumns.includes(column.key) && lastRow > headerRow) {
      sheet.getRange(`${letter}${headerRow + 1}:${letter}${lastRow}`).format.numberFormat = "#,##0";
    }
  }

  if (rows.length) {
    const table = sheet.tables.add(`A${headerRow}:${lastColumn}${lastRow}`, true, `${name.replace(/[^A-Za-z0-9]/g, "")}Table`);
    table.style = "TableStyleMedium2";
    table.showBandedRows = true;
  }
  return { sheet, lastRow, lastColumn, headerRow };
}

const summary = JSON.parse(await fs.readFile(path.join(meta, "summary.json"), "utf8"));
const profiles = await readCSV("table_profile.csv");
const ruleResults = await readCSV("quality_rule_results.csv");
const issues = await readCSV("quality_issues.csv");
const dictionary = await readCSV("data_dictionary.csv");
const transformations = await readCSV("transformation_log.csv");
const sourceRows = await readCSV("sources.csv");
const dimensions = await readCSV("dimension_summary.csv");
const processedUtcLabel = `UTC ${summary.processed_at_utc}`;

const workbook = Workbook.create();
const summarySheet = workbook.worksheets.add("Summary");
summarySheet.showGridLines = false;
summarySheet.tabColor = "#1F4E78";
summarySheet.getRange("A2").values = [["Olist data quality report"]];
styleTitle(summarySheet, "R");

const processedWita = new Intl.DateTimeFormat("id-ID", {
  timeZone: "Asia/Makassar",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
}).format(new Date(summary.processed_at_utc));

summarySheet.getRange("A5:B11").values = [
  ["Metric", "Value"],
  ["Processed (WITA)", processedWita],
  ["Raw source rows", summary.raw_total_rows],
  ["Clean output rows", summary.clean_total_rows],
  ["Detailed issue records", summary.quality_issue_rows],
  ["Automatically corrected", summary.corrected_issue_rows],
  ["Open for review", summary.open_issue_rows],
];
applyTableStyle(summarySheet, summarySheet.getRange("A5:B5"), summarySheet.getRange("A6:B11"));
summarySheet.getRange("B7:B11").format.numberFormat = "#,##0";
summarySheet.getRange("A5:B11").format.columnWidth = 24;
summarySheet.getRange("A5:A11").format.columnWidth = 27;

summarySheet.getRange("D5:E10").values = [
  ["Control", "Count"],
  ["Quarantined issue records", summary.quarantined_issue_rows],
  ["Raw geolocation duplicates removed", 261831],
  ["Canonical ZIP prefixes", 19015],
  ["Order rows with error status", 49],
  ["Canonical ZIP rows with error status", 5],
];
applyTableStyle(summarySheet, summarySheet.getRange("D5:E5"), summarySheet.getRange("D6:E10"));
summarySheet.getRange("E6:E10").format.numberFormat = "#,##0";
summarySheet.getRange("D5:D10").format.columnWidth = 35;
summarySheet.getRange("E5:E10").format.columnWidth = 14;

summarySheet.getRange("A14:I14").values = [[
  "Table", "Raw rows", "Clean rows", "Valid", "Corrected", "Warning", "Error", "Raw duplicates", "Clean duplicates",
]];
const profileValues = profiles.map((row) => [
  row.table,
  numberOrBlank(row.raw_rows),
  numberOrBlank(row.clean_rows),
  numberOrBlank(row.valid_rows),
  numberOrBlank(row.corrected_rows),
  numberOrBlank(row.warning_rows),
  numberOrBlank(row.error_rows),
  numberOrBlank(row.raw_exact_duplicate_rows),
  numberOrBlank(row.clean_exact_duplicate_rows),
]);
summarySheet.getRange(`A15:I${14 + profileValues.length}`).values = profileValues;
applyTableStyle(
  summarySheet,
  summarySheet.getRange("A14:I14"),
  summarySheet.getRange(`A15:I${14 + profileValues.length}`),
);
summarySheet.getRange(`B15:I${14 + profileValues.length}`).format.numberFormat = "#,##0";
summarySheet.getRange("A14:A23").format.columnWidth = 40;
summarySheet.getRange("B14:I23").format.columnWidth = 13;
summarySheet.getRange(`G15:G${14 + profileValues.length}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan",
  formula: 0,
  format: { fill: "#FEE2E2", font: { bold: true, color: "#B91C1C" } },
});
summarySheet.getRange(`F15:F${14 + profileValues.length}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan",
  formula: 0,
  format: { fill: "#FEF3C7", font: { color: "#92400E" } },
});

summarySheet.getRange("K5:M5").values = [["Dimension", "Severity", "Issues"]];
const dimensionValues = dimensions.map((row) => [row.dimension, row.severity, numberOrBlank(row.issue_count)]);
summarySheet.getRange(`K6:M${5 + dimensionValues.length}`).values = dimensionValues;
applyTableStyle(
  summarySheet,
  summarySheet.getRange("K5:M5"),
  summarySheet.getRange(`K6:M${5 + dimensionValues.length}`),
);
summarySheet.getRange(`M6:M${5 + dimensionValues.length}`).format.numberFormat = "#,##0";
summarySheet.getRange("K5:K25").format.columnWidth = 31;
summarySheet.getRange("L5:L25").format.columnWidth = 12;
summarySheet.getRange("M5:M25").format.columnWidth = 12;

summarySheet.getRange("A27").values = [["Catatan penting"]];
summarySheet.getRange("A28").values = [["Tabel bersih tetap mempertahankan baris dq_status=error agar relasi foreign key dapat ditelusuri. Salinannya juga tersedia di karantina."]];
summarySheet.getRange("A29").values = [["Tabel geolokasi dikanonisasi menjadi satu baris per prefix kode pos. Penurunan jumlah baris terjadi karena agregasi yang disengaja, bukan kehilangan rekam."]];
summarySheet.getRange("A30").values = [["Akurasi alamat, identitas, dan koordinat terhadap dunia nyata tidak dapat dibuktikan hanya dari snapshot ini. Peringatan terbuka tetap ditampilkan."]];
summarySheet.getRange("A31").values = [["Untuk penggunaan analitik yang ketat, filter dq_status dan dq_issue_codes pada setiap CSV bersih."]];
for (let row = 27; row <= 31; row++) summarySheet.mergeCells(`A${row}:I${row}`);
summarySheet.getRange("A27:I27").format = {
  fill: "#D9EAF7",
  font: { name: fontFamily, size: 10, bold: true, color: "#1F2937" },
  borders: { preset: "outside", style: "thin", color: "#93C5FD" },
};
summarySheet.getRange("A28:I31").format.font = { name: fontFamily, size: 10, color: "#374151" };
summarySheet.getRange("A28:I31").format.wrapText = true;
summarySheet.getRange("A27:I31").format.rowHeight = 24;

const profileSheet = writeDataSheet(workbook, {
  name: "Table Profile",
  title: "Table-level quality profile",
  rows: profiles,
  numericColumns: ["raw_rows", "clean_rows", "valid_rows", "corrected_rows", "warning_rows", "error_rows", "raw_exact_duplicate_rows", "clean_exact_duplicate_rows"],
  columns: [
    { key: "table", label: "Table", width: 40 },
    { key: "raw_rows", label: "Raw rows" },
    { key: "clean_rows", label: "Clean rows" },
    { key: "valid_rows", label: "Valid" },
    { key: "corrected_rows", label: "Corrected" },
    { key: "warning_rows", label: "Warning" },
    { key: "error_rows", label: "Error" },
    { key: "raw_exact_duplicate_rows", label: "Raw duplicates", width: 17 },
    { key: "clean_exact_duplicate_rows", label: "Clean duplicates", width: 18 },
  ],
});
profileSheet.sheet.getRange(`B6:I${profileSheet.lastRow}`).format.numberFormat = "#,##0";
profileSheet.sheet.getRange(`G6:G${profileSheet.lastRow}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan", formula: 0,
  format: { fill: "#FEE2E2", font: { bold: true, color: "#B91C1C" } },
});

const ruleSheet = writeDataSheet(workbook, {
  name: "Rule Results",
  title: "Results by quality rule",
  rows: ruleResults,
  numericColumns: ["detected_count", "corrected_count", "quarantined_count", "open_count"],
  wrapColumns: ["description"],
  columns: [
    { key: "rule_id", label: "Rule ID", width: 36 },
    { key: "dimension", label: "Dimension", width: 30 },
    { key: "severity", label: "Severity", width: 12 },
    { key: "description", label: "Description", width: 48 },
    { key: "detected_count", label: "Detected", width: 13 },
    { key: "corrected_count", label: "Corrected", width: 13 },
    { key: "quarantined_count", label: "Quarantined", width: 15 },
    { key: "open_count", label: "Open", width: 12 },
    { key: "result", label: "Result", width: 13 },
  ],
});
ruleSheet.sheet.getRange(`E6:H${ruleSheet.lastRow}`).format.numberFormat = "#,##0";
ruleSheet.sheet.getRange(`I6:I${ruleSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "REVIEW", format: { fill: "#FEF3C7", font: { bold: true, color: "#92400E" } },
});
ruleSheet.sheet.getRange(`I6:I${ruleSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "CORRECTED", format: { fill: "#DCFCE7", font: { bold: true, color: "#166534" } },
});

const issueSheet = writeDataSheet(workbook, {
  name: "Issues",
  title: "Detailed quality issues and disposition",
  rows: issues,
  wrapColumns: ["detail"],
  columns: [
    { key: "table", label: "Table", width: 38 },
    { key: "record_key", label: "Record key", width: 44 },
    { key: "rule_id", label: "Rule ID", width: 37 },
    { key: "dimension", label: "Dimension", width: 30 },
    { key: "severity", label: "Severity", width: 12 },
    { key: "column", label: "Column", width: 28 },
    { key: "original_value", label: "Original value", width: 28 },
    { key: "action", label: "Action", width: 35 },
    { key: "disposition", label: "Disposition", width: 14 },
    { key: "detail", label: "Detail", width: 55 },
  ],
});
issueSheet.sheet.freezePanes.freezeColumns(2);
issueSheet.sheet.getRange(`E6:E${issueSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "error", format: { fill: "#FEE2E2", font: { bold: true, color: "#B91C1C" } },
});
issueSheet.sheet.getRange(`E6:E${issueSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "warning", format: { fill: "#FEF3C7", font: { color: "#92400E" } },
});
issueSheet.sheet.getRange(`I6:I${issueSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "corrected", format: { fill: "#DCFCE7", font: { color: "#166534" } },
});
issueSheet.sheet.getRange(`I6:I${issueSheet.lastRow}`).conditionalFormats.add("containsText", {
  text: "quarantined", format: { fill: "#FEE2E2", font: { color: "#B91C1C" } },
});

writeDataSheet(workbook, {
  name: "Dictionary",
  title: "Clean output data dictionary",
  rows: dictionary,
  wrapColumns: ["grain", "description", "domain_or_format"],
  columns: [
    { key: "table", label: "Table", width: 38 },
    { key: "grain", label: "Grain", width: 52 },
    { key: "column", label: "Column", width: 36 },
    { key: "data_type", label: "Data type", width: 15 },
    { key: "nullable_in_output", label: "Nullable", width: 12 },
    { key: "description", label: "Description", width: 48 },
    { key: "domain_or_format", label: "Domain or format", width: 52 },
  ],
});

writeDataSheet(workbook, {
  name: "Transformations",
  title: "Transformation log",
  rows: transformations,
  numericColumns: ["affected_rows"],
  wrapColumns: ["detail"],
  columns: [
    { key: "table", label: "Table", width: 40 },
    { key: "action", label: "Action", width: 42 },
    { key: "affected_rows", label: "Affected rows", width: 16 },
    { key: "detail", label: "Detail", width: 70 },
  ],
});

const sources = [
  {
    source_file: "Source ZIP",
    role: "OLTP source container",
    location: "C:/Users/LENOVO/Downloads/drive-download-20261012T134929Z-1-001.zip",
    sha256: summary.source_zip_sha256,
    raw_rows: summary.raw_total_rows,
    processed_at_utc: processedUtcLabel,
  },
  {
    source_file: "Data warehouse: teori dan praktek",
    role: "Quality criteria reference, section 10.1.2",
    location: "C:/Users/LENOVO/Downloads/Ebook 9786349719902-Data warehouse  teori dan praktek (1).pdf",
    sha256: "",
    raw_rows: "",
    processed_at_utc: processedUtcLabel,
  },
  ...sourceRows.map((row) => ({
    source_file: row.source_file,
    role: "Extracted raw table",
    location: `raw/${row.source_file}`,
    sha256: row.sha256,
    raw_rows: row.raw_rows,
    processed_at_utc: `UTC ${row.processed_at_utc}`,
  })),
];
writeDataSheet(workbook, {
  name: "Sources",
  title: "Sources and processing provenance",
  rows: sources,
  numericColumns: ["raw_rows"],
  wrapColumns: ["location"],
  tabColor: "#64748B",
  columns: [
    { key: "source_file", label: "Source", width: 42 },
    { key: "role", label: "Role", width: 38 },
    { key: "location", label: "Location", width: 72 },
    { key: "sha256", label: "SHA-256", width: 68 },
    { key: "raw_rows", label: "Rows", width: 14 },
    { key: "processed_at_utc", label: "Processed at UTC", width: 28 },
  ],
});

workbook.recalculate();
const summaryInspect = await workbook.inspect({
  kind: "table",
  sheetId: "Summary",
  range: "A1:R31",
  include: "values,formulas",
  tableMaxRows: 31,
  tableMaxCols: 18,
  maxChars: 12000,
});
const errorInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "Final formula error scan",
  maxChars: 4000,
});

await fs.mkdir(previewDir, { recursive: true });
const previewRanges = {
  Summary: "A1:R31",
  "Table Profile": "A1:I16",
  "Rule Results": "A1:I25",
  Issues: "A1:J25",
  Dictionary: "A1:G25",
  Transformations: "A1:D20",
  Sources: "A1:F20",
};
for (const [sheetName, range] of Object.entries(previewRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1.5, format: "png" });
  const bytes = new Uint8Array(await preview.arrayBuffer());
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`), bytes);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({
  outputPath,
  previewDir,
  summaryInspect: summaryInspect.ndjson,
  errorInspect: errorInspect.ndjson,
}, null, 2));
