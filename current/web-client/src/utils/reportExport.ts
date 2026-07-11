/** Lightweight CSV export for report tables (no Excel dependency needed).

 * Builds a UTF-8 BOM CSV (opens cleanly in Excel) from headers + rows and
 * triggers a browser download. Sufficient parity for the ТМЦ / взаиморасчеты
 * reports, whose data already lives client-side after filtering.
 */
export function downloadCsv(filename: string, headers: string[], rows: Array<Array<string | number | null | undefined>>): void {
  const escape = (value: string | number | null | undefined) => {
    const text = value === null || value === undefined ? '' : String(value)
    if (/[",;\n]/.test(text)) {
      return `"${text.replace(/"/g, '""')}"`
    }
    return text
  }
  const lines = [headers.map(escape).join(';'), ...rows.map((row) => row.map(escape).join(';'))]
  const csv = '\ufeff' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
