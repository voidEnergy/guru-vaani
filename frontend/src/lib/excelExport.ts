import ExcelJS from 'exceljs';

export interface ExportMarksheetOptions {
  filename: string;
  sheetName?: string;
  rows: Record<string, string | number>[];
  anchors?: string[];
  rollKey?: string;
  nameKey?: string;
}

/**
 * Triggers a direct browser file download for a Blob.
 */
export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/**
 * Estimates wrapped line count for a cell based on column width and content length.
 * Accounts for explicit line breaks and safe column character width.
 */
export function estimateWrappedLines(text: string, colWidth: number): number {
  if (!text || typeof text !== 'string') return 1;
  const trimmed = text.trim();
  if (!trimmed) return 1;

  const paragraphs = trimmed.split(/\r\n|\r|\n/);
  // Estimate characters per line for 11pt font with cell padding
  const charsPerLine = Math.max(10, Math.floor(colWidth * 0.85));

  let totalLines = 0;
  for (const para of paragraphs) {
    if (!para.length) {
      totalLines += 1;
    } else {
      totalLines += Math.max(1, Math.ceil(para.length / charsPerLine));
    }
  }

  return Math.max(1, totalLines);
}

/**
 * Determines auto-fitted column width with safe minimums per column category:
 * - Roll No: 11
 * - Student Name: min 22
 * - Metadata columns (e.g., Class): min 12
 * - Question/rubric score columns: 11
 * - Total: 12
 * - Feedback (EN): 44
 * - Feedback (HI): 48
 */
export function getColumnWidth(
  colKey: string,
  rows: Record<string, string | number>[],
  anchors: string[] = [],
  rollKey?: string,
  nameKey?: string
): number {
  const isRoll = colKey === (rollKey || 'Roll No') || /roll/i.test(colKey);
  const isName = colKey === (nameKey || 'Student Name') || /name/i.test(colKey);
  const isTotal = colKey === 'Total' || /^total$/i.test(colKey);
  const isFeedbackEn =
    colKey === 'Feedback (EN)' ||
    (colKey.includes('Feedback') && colKey.includes('EN'));
  const isFeedbackHi =
    colKey === 'Feedback (HI)' ||
    (colKey.includes('Feedback') && colKey.includes('HI'));
  const isScore = anchors.includes(colKey);

  // Exact safe minimum widths for feedback columns
  if (isFeedbackEn) return 44;
  if (isFeedbackHi) return 48;

  let safeMin = 12; // default safe minimum for metadata columns like Class
  if (isRoll) {
    safeMin = 11;
  } else if (isName) {
    safeMin = 22;
  } else if (isScore) {
    safeMin = 11;
  } else if (isTotal) {
    safeMin = 12;
  }

  // Calculate dynamic content length across header and all rows
  let maxContentLen = colKey.length;
  for (const row of rows) {
    const val = row[colKey];
    if (val !== undefined && val !== null) {
      const len = String(val).length;
      if (len > maxContentLen) {
        maxContentLen = len;
      }
    }
  }

  return Math.max(safeMin, maxContentLen + 3);
}

/**
 * Generates and downloads a beautifully formatted .xlsx marksheet using ExcelJS.
 */
export async function exportMarksheetXlsx({
  filename,
  sheetName = 'GuruVaani_Marksheet',
  rows,
  anchors = [],
  rollKey = 'Roll No',
  nameKey = 'Student Name',
}: ExportMarksheetOptions): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'Guru-Vaani';
  workbook.lastModifiedBy = 'Guru-Vaani';
  workbook.created = new Date();
  workbook.modified = new Date();

  const worksheet = workbook.addWorksheet(sheetName);

  // Freeze row 1 so headers stay visible while scrolling
  worksheet.views = [{ state: 'frozen', ySplit: 1 }];

  if (rows.length === 0) {
    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    triggerBrowserDownload(
      blob,
      filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`
    );
    return;
  }

  // Determine ordered columns from the data
  const columnKeys = Object.keys(rows[0]);

  // Configure columns with dynamic auto-fitted widths
  worksheet.columns = columnKeys.map((key) => ({
    header: key,
    key: key,
    width: getColumnWidth(key, rows, anchors, rollKey, nameKey),
  }));

  // Style Header Row:
  // Row height: 28, bold white 11pt font, Indigo fill (#4338CA), centered vertically and horizontally
  const headerRow = worksheet.getRow(1);
  headerRow.height = 28;

  const thinBorder: Partial<ExcelJS.Borders> = {
    top: { style: 'thin', color: { argb: 'FFCBD5E1' } },
    left: { style: 'thin', color: { argb: 'FFCBD5E1' } },
    bottom: { style: 'thin', color: { argb: 'FFCBD5E1' } },
    right: { style: 'thin', color: { argb: 'FFCBD5E1' } },
  };

  headerRow.eachCell({ includeEmpty: true }, (cell) => {
    cell.font = {
      name: 'Calibri',
      size: 11,
      bold: true,
      color: { argb: 'FFFFFFFF' },
    };
    cell.fill = {
      type: 'pattern',
      pattern: 'solid',
      fgColor: { argb: 'FF4338CA' }, // Indigo #4338CA
    };
    cell.alignment = {
      vertical: 'middle',
      horizontal: 'center',
      wrapText: true,
    };
    cell.border = thinBorder;
  });

  // Enable autoFilter across the header row
  worksheet.autoFilter = {
    from: { row: 1, column: 1 },
    to: { row: rows.length + 1, column: columnKeys.length },
  };

  // Populate data rows with styling, zebra striping, and dynamic row height
  rows.forEach((rowData, index) => {
    const dataRow = worksheet.addRow(rowData);
    const isZebra = index % 2 === 1;

    // Dynamic row height for feedback:
    // row.height = Math.max(22, maxLines * 17 + 6)
    const enText = String(rowData['Feedback (EN)'] ?? '');
    const hiText = String(rowData['Feedback (HI)'] ?? '');
    const hasFeedback = Boolean(enText.trim() || hiText.trim());

    if (hasFeedback) {
      const enLines = estimateWrappedLines(enText, 44);
      const hiLines = estimateWrappedLines(hiText, 48);
      const maxLines = Math.max(enLines, hiLines);
      dataRow.height = Math.max(22, maxLines * 17 + 6);
    } else {
      dataRow.height = 22;
    }

    dataRow.eachCell({ includeEmpty: true }, (cell, colNumber) => {
      const colKey = columnKeys[colNumber - 1];
      const isRoll =
        colKey === (rollKey || 'Roll No') || /roll/i.test(colKey);
      const isName =
        colKey === (nameKey || 'Student Name') || /name/i.test(colKey);
      const isTotal = colKey === 'Total' || /^total$/i.test(colKey);
      const isFeedbackEn =
        colKey === 'Feedback (EN)' ||
        (colKey.includes('Feedback') && colKey.includes('EN'));
      const isFeedbackHi =
        colKey === 'Feedback (HI)' ||
        (colKey.includes('Feedback') && colKey.includes('HI'));
      const isScore = anchors.includes(colKey);

      // Thin grey borders (#CBD5E1) on all cells
      cell.border = thinBorder;

      if (isTotal) {
        // Highlighted Total Column: Bold text with soft tint fill (#EEF2FF)
        cell.font = {
          name: 'Calibri',
          size: 11,
          bold: true,
          color: { argb: 'FF1E293B' },
        };
        cell.fill = {
          type: 'pattern',
          pattern: 'solid',
          fgColor: { argb: 'FFEEF2FF' }, // Soft Indigo tint #EEF2FF
        };
        cell.alignment = { vertical: 'middle', horizontal: 'center' };
      } else {
        cell.font = {
          name: 'Calibri',
          size: 11,
          color: { argb: 'FF1E293B' },
        };

        // Subtle zebra fill (#F8FAFC) on alternating rows
        if (isZebra) {
          cell.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: 'FFF8FAFC' },
          };
        }

        // Alignments:
        // Centered for Roll No and scores
        // Left alignment with wrapText: true for Student Name and both feedback columns
        if (isRoll || isScore) {
          cell.alignment = { vertical: 'middle', horizontal: 'center' };
        } else if (isName || isFeedbackEn || isFeedbackHi) {
          cell.alignment = {
            vertical: 'middle',
            horizontal: 'left',
            wrapText: true,
          };
        } else {
          // Other metadata columns (e.g., Class, Section)
          cell.alignment = { vertical: 'middle', horizontal: 'left' };
        }
      }
    });
  });

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  triggerBrowserDownload(
    blob,
    filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`
  );
}

/**
 * Downloads marksheet CSV prepended with a UTF-8 BOM ("\uFEFF") so
 * Hindi Devanagari text renders cleanly without garbled characters in Microsoft Excel.
 */
export function exportMarksheetCsv(
  filename: string,
  csvContent: string
): void {
  const blob = new Blob(['\uFEFF' + csvContent], {
    type: 'text/csv;charset=utf-8;',
  });
  triggerBrowserDownload(
    blob,
    filename.endsWith('.csv') ? filename : `${filename}.csv`
  );
}
