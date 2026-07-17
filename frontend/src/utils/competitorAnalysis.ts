import type { ProductRow } from '../types'

export type CompetitorTier = 'all' | 'leader' | 'challenger' | 'long_tail' | 'watchlist'
export type BenchmarkMetric = 'sales' | 'price' | 'rating' | 'bsr' | 'reviews'

export interface CompetitorProfile {
  product: ProductRow
  isNew: boolean
  signals: string[]
}

export const benchmarkLabels: Record<BenchmarkMetric, string> = {
  sales: '销量对标',
  price: '价格对标',
  rating: '评分对标',
  bsr: 'BSR对标',
  reviews: '评论对标',
}

export function buildCompetitorProfiles(products: ProductRow[]): CompetitorProfile[] {
  const sorted = [...products].sort((a, b) => numeric(b.amount) - numeric(a.amount) || numeric(b.units) - numeric(a.units))
  const totalUnits = sorted.reduce((sum, product) => sum + numeric(product.units), 0)
  return sorted.map((product) => {
    const share = totalUnits ? numeric(product.units) / totalUnits : 0
    const signals = competitorSignals(product, share)
    return {
      product,
      isNew: isNewProduct(product),
      signals,
    }
  })
}

export function numeric(value: unknown): number {
  if (value == null || value === '') return 0
  const parsed = Number(String(value).replaceAll(',', ''))
  return Number.isFinite(parsed) ? parsed : 0
}

export function text(value: unknown): string {
  if (value == null || value === '') return '-'
  return String(value)
}

export function pct(delta: number | null): string {
  if (delta == null || !Number.isFinite(delta)) return '-'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${(delta * 100).toFixed(1)}%`
}

export function delta(current: unknown, baseline: unknown): number | null {
  const b = numeric(baseline)
  if (!b) return null
  return (numeric(current) - b) / b
}

export function isNewProduct(product: ProductRow): boolean {
  const days = numeric(product.available_days)
  return days > 0 && days <= 365
}

function competitorSignals(product: ProductRow, share: number): string[] {
  const signals = []
  const units = numeric(product.units)
  const reviews = numeric(product.reviews)
  const rating = numeric(product.rating)
  const availableDays = numeric(product.available_days)
  if (share >= 0.18) signals.push('销量集中')
  if (units >= 1000 && rating && rating < 4.2) signals.push('低评分高销量')
  if (units >= 1000 && reviews && reviews < 500) signals.push('低评论高销量')
  if (availableDays && availableDays <= 365) signals.push('新品')
  if (numeric(product.discount_off_list_pct) > 0) signals.push('折扣竞手')
  if (!product.bsr_list__main_rank && !product.bsr) signals.push('BSR缺失')
  return signals
}
