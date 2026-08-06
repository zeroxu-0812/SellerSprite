export type MarketplaceCode = 'com' | 'it' | 'uk' | 'fr' | 'es' | 'de' | 'jp'

export interface RunRequest {
  asins: string[]
  marketplaces: MarketplaceCode[]
  marketplace?: MarketplaceCode
  includeSummary: boolean
  includeDetails: boolean
  workers?: number
}

export interface AdminLoginResponse {
  token: string
  expiresInSeconds: number
}

export interface Failure {
  asin: string
  stage: string
  message: string
  marketplace?: MarketplaceCode | string
}

export interface MarketOverview {
  result_count: number | null
  sample_size: number
  avg_price: number | null
  avg_rating: number | null
  avg_reviews: number | null
  total_units: number
  total_amount: number
  top10_units_share: number | null
  price_distribution: Record<string, number>
  rating_distribution: Record<string, number>
}

export interface RunResponse {
  products: ProductRow[]
  overview: MarketOverview
  marketplace_overviews?: Record<string, MarketOverview>
  failures: Failure[]
  output_dir: string
}

export type ProductRow = Record<string, unknown>

export type JobStatus = 'queued' | 'running' | 'done' | 'error'

export interface RunProgress {
  job_id: string
  status: JobStatus
  total: number
  completed: number
  current_asin: string | null
  stage: string
  result: RunResponse | null
  error: string | null
}

export interface MarketplaceUsage {
  count: number
  last_searched_at: string | null
}

export interface SearchUsageEvent {
  marketplace: MarketplaceCode
  asin_count: number
  searched_at: string
}

export interface UsageResponse {
  total: number
  marketplaces: Partial<Record<MarketplaceCode, MarketplaceUsage>>
  recent: SearchUsageEvent[]
}
