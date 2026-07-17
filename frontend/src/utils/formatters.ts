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

export function money(value: unknown): string {
  return typeof value === 'number'
    ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`
    : '-'
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

