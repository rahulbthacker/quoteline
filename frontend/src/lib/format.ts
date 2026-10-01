const inrWhole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const inrTwo = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const plain = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 4 })

/** ₹1,08,320 */
export function rupees(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  return `₹${inrWhole.format(value)}`
}

/** ₹3.64 Cr above a crore, ₹7.2 L above a lakh, else ₹54,910 */
export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(1)} L`
  return `${sign}₹${inrWhole.format(abs)}`
}

export const money2 = (value: number) => inrTwo.format(value)
export const num = (value: number) => plain.format(value)
export const pct = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined ? '–' : `${(value * 100).toFixed(digits)}%`

export function when(iso: string | null | undefined): string {
  if (!iso) return '–'
  // The API stores UTC; a timestamp without a zone suffix is UTC, not local time.
  const zoned = /[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`
  return new Date(zoned).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
}

export function shortModel(model: string | null | undefined): string {
  if (!model) return 'model'
  if (model.startsWith('claude-opus')) return 'Claude Opus'
  if (model.startsWith('claude-haiku')) return 'Claude Haiku'
  if (model.startsWith('gemini')) return 'Gemini 3.1 Pro'
  return model
}

export const FORMAT_ICON: Record<string, string> = { xlsx: 'XLSX', pdf: 'PDF', docx: 'DOCX', image: 'Photo', eml: 'Email' }
