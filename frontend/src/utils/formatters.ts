export function safe(input: unknown): string {
  return String(input ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function plain(input: unknown): string {
  if (input == null || input === '') return ''
  return String(input)
}

export function fmt(input: unknown): string {
  if (input == null || input === '') return '<span class="empty">—</span>'
  return safe(String(input))
}

export interface CurrencyMeta {
  code: string
  locale: string
}

const marketplaceCurrencies: Record<string, CurrencyMeta> = {
  com: { code: 'USD', locale: 'en-US' },
  us: { code: 'USD', locale: 'en-US' },
  amazoncom: { code: 'USD', locale: 'en-US' },
  it: { code: 'EUR', locale: 'it-IT' },
  italy: { code: 'EUR', locale: 'it-IT' },
  fr: { code: 'EUR', locale: 'fr-FR' },
  france: { code: 'EUR', locale: 'fr-FR' },
  es: { code: 'EUR', locale: 'es-ES' },
  spain: { code: 'EUR', locale: 'es-ES' },
  de: { code: 'EUR', locale: 'de-DE' },
  germany: { code: 'EUR', locale: 'de-DE' },
  uk: { code: 'GBP', locale: 'en-GB' },
  gb: { code: 'GBP', locale: 'en-GB' },
  couk: { code: 'GBP', locale: 'en-GB' },
  jp: { code: 'JPY', locale: 'ja-JP' },
  japan: { code: 'JPY', locale: 'ja-JP' },
  cojp: { code: 'JPY', locale: 'ja-JP' },
}

export function currencyForMarketplace(marketplace: unknown): CurrencyMeta {
  const raw = String(marketplace ?? 'com').trim().toLowerCase()
  const compact = raw.replace(/[^a-z]/g, '')
  return marketplaceCurrencies[raw] || marketplaceCurrencies[compact] || marketplaceCurrencies.com
}

export function money(value: unknown, marketplace: unknown = 'com'): string {
  if (value == null || value === '') return '-'
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''))
  if (!Number.isFinite(numeric)) return '-'
  const currency = currencyForMarketplace(marketplace)
  const fractionDigits = currency.code === 'JPY' ? 0 : 2
  return new Intl.NumberFormat(currency.locale, {
    style: 'currency',
    currency: currency.code,
    currencyDisplay: 'symbol',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(numeric)
}

export function integer(value: unknown): string {
  return typeof value === 'number' ? Math.round(value).toLocaleString() : '-'
}

export function parseList(input: unknown): string[] {
  if (!input) return []
  if (Array.isArray(input)) return input.map(String)
  if (typeof input === 'string') {
    try {
      const parsed = JSON.parse(input)
      return Array.isArray(parsed) ? parsed.map(String) : [String(parsed)]
    } catch {
      return input.split(',').map((item) => item.trim())
    }
  }
  return [String(input)]
}

export function parseTrend(input: unknown): {
  values: Array<{ dk: string; sales: number }>
  max: number
  total: number
} {
  let map: Record<string, unknown> = {}
  if (typeof input === 'string') {
    try {
      map = JSON.parse(input) as Record<string, unknown>
    } catch {
      map = {}
    }
  } else if (input && typeof input === 'object' && !Array.isArray(input)) {
    map = input as Record<string, unknown>
  }
  const values = Object.keys(map)
    .filter((key) => /^\d{6}$/.test(key))
    .sort()
    .map((dk) => ({ dk, sales: Number(map[dk]) || 0 }))
  const max = Math.max(...values.map((item) => item.sales), 1)
  const total = values.reduce((sum, item) => sum + item.sales, 0)
  return { values, max, total }
}
