export type MarketplaceCode = 'com' | 'it' | 'uk' | 'fr' | 'es' | 'de' | 'jp'

export interface RunRequest {
  asins: string[]
  marketplace: MarketplaceCode
  includeSummary: boolean
  includeDetails: boolean
  workers?: number
}

export interface Failure {
  asin: string
  stage: string
  message: string
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
