import type { ProductRow } from '../types'
import type { MarketplaceCode } from '../types'
import { fmt, parseList, parseTrend, plain, safe } from './formatters'
import { isNewProduct } from './competitorAnalysis'
import { marketplaceByCode } from './marketplaces'

export interface ProductColumn {
  key: string
  label: string
  labelEn: string
  className?: string
  align?: 'left' | 'center' | 'right'
  defaultVisible?: boolean
  group: 'identity' | 'market' | 'seller' | 'performance'
  sortKey?: string
  sortType?: 'text' | 'number' | 'date'
  render: (product: ProductRow, language?: ProductDisplayLanguage) => string
}

export type ProductDisplayLanguage = 'zh' | 'en'

export const productColumns: ProductColumn[] = [
  { key: 'img', label: '主图', labelEn: 'Image', className: 'img-cell', group: 'identity', render: renderImage },
  { key: 'title', label: '标题', labelEn: 'Title', className: 'title-cell', group: 'identity', sortKey: 'title', sortType: 'text', render: renderTitle },
  { key: 'asin', label: 'ASIN', labelEn: 'ASIN', group: 'identity', sortKey: 'asin', sortType: 'text', render: renderAsin },
  { key: 'marketplace_code', label: '来源站点', labelEn: 'Marketplace', className: 'marketplace-cell', group: 'identity', sortKey: 'marketplace_code', sortType: 'text', render: renderMarketplace },
  { key: 'brand', label: '品牌', labelEn: 'Brand', group: 'identity', sortKey: 'brand', sortType: 'text', render: renderBrand },
  { key: 'badges', label: '徽章', labelEn: 'Badges', group: 'identity', render: (p) => renderBadges(p.badges) },
  { key: 'price', label: '价格', labelEn: 'Price', group: 'market', sortKey: 'price', sortType: 'number', render: renderPrice },
  { key: 'rating', label: '评分', labelEn: 'Rating', group: 'market', sortKey: 'rating', sortType: 'number', render: renderRating },
  { key: 'date', label: '上架时间', labelEn: 'Date Available', group: 'market', sortKey: 'available_date', sortType: 'date', render: renderDate },
  { key: 'variations', label: '变体数', labelEn: 'Variations', align: 'center', group: 'market', sortKey: 'variations', sortType: 'number', render: (p) => fmt(p.variations) },
  { key: 'catpath', label: '类目路径', labelEn: 'Category Path', className: 'cat-path', group: 'market', render: renderCatPath },
  { key: 'bsr', label: 'BSR排名', labelEn: 'BSR Rank', group: 'market', sortKey: 'bsr_list__main_rank', sortType: 'number', render: renderBsr },
  { key: 'seller', label: '卖家', labelEn: 'Seller', group: 'seller', sortKey: 'seller_name', sortType: 'text', render: renderSeller },
  { key: 'sales', label: '销量', labelEn: 'Sales', group: 'performance', sortKey: 'units', sortType: 'number', render: renderSales },
  { key: 'amount', label: '销售额', labelEn: 'Revenue', group: 'performance', sortKey: 'amount', sortType: 'number', render: renderAmount },
  { key: 'trend', label: '销量趋势', labelEn: 'Sales Trend', className: 'trend-cell', group: 'performance', render: renderTrend },
]

function renderImage(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const image = plain(product.image_large || product.image_zoom || product.image)
  const fallback = plain(product.image)
  const url = plain(product.url || '#')
  if (!image) return '<span class="empty">—</span>'
  const badge = isNewProduct(product) ? `<span class="image-badge">${language === 'en' ? 'New' : '新品'}</span>` : ''
  return `<a class="image-link" href="${safe(url)}" target="_blank" rel="noreferrer"><img src="${safe(image)}" onerror="this.src='${safe(fallback)}';this.onerror=null;">${badge}</a>`
}

function renderTitle(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const url = plain(product.url || '#')
  return `<a href="${safe(url)}" target="_blank" rel="noreferrer">${safe(product.title || (language === 'en' ? '(Untitled)' : '(无标题)'))}</a>`
}

function renderAsin(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const child = language === 'en' ? 'Child ASIN:' : '子ASIN:'
  const parent = language === 'en' ? 'Parent ASIN:' : '父ASIN:'
  return `<div class="asin-line"><span class="lbl">${child}</span> <b>${fmt(product.asin)}</b></div><div class="parent-line"><span class="lbl">${parent}</span> ${fmt(product.parent)}</div>`
}

function renderMarketplace(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const code = String(product.marketplace_code || '').toLowerCase()
  const info = marketplaceByCode[code as MarketplaceCode]
  if (!info) return `<span class="empty">${safe(product.marketplace_station || '—')}</span>`
  const englishLabels: Partial<Record<MarketplaceCode, string>> = {
    com: 'United States', de: 'Germany', uk: 'United Kingdom', jp: 'Japan', fr: 'France', es: 'Spain', it: 'Italy',
  }
  const label = language === 'en' ? englishLabels[code as MarketplaceCode] : `${info.label}站`
  return `<div class="marketplace-source"><span class="marketplace-flag">${safe(info.flag)}</span><b>${safe(label)}</b><small>${safe(code.toUpperCase())}</small></div>`
}

function renderBrand(product: ProductRow): string {
  const brandUrl = plain(product.brand_url)
  const baseUrl = plain(product.amazon_base_url || 'https://www.amazon.com').replace(/\/+$/, '')
  const href = brandUrl
    ? (/^https?:\/\//i.test(brandUrl) ? brandUrl : `${baseUrl}/${brandUrl.replace(/^\/+/, '')}`)
    : '#'
  return `<a class="brand-link" href="${safe(href)}" target="_blank" rel="noreferrer">${fmt(product.brand)}</a>`
}

function renderBadges(input: unknown): string {
  const badges = parseList(input).filter((item) => item && item !== '[]')
  if (!badges.length) return '<span class="empty">—</span>'
  return `<div class="badge-list">${badges.map((item) => `<span>${safe(item)}</span>`).join('')}</div>`
}

function renderPrice(product: ProductRow): string {
  const currency = safe(product.currency || '$')
  const listPrice = product.list_price ? `<div class="strike">${currency}${safe(product.list_price)}</div>` : ''
  const discount = product.discount_off_list_pct ? `<div class="discount">-${safe(product.discount_off_list_pct)}%</div>` : ''
  return `<div><b class="price">${currency}${fmt(product.price)}</b></div>${listPrice}${discount}`
}

function renderRating(product: ProductRow): string {
  const rating = Number(product.rating || 0)
  const rounded = Math.max(0, Math.min(5, Math.round(rating)))
  const starText = rating ? `${'★'.repeat(rounded)}${'☆'.repeat(5 - rounded)}` : '—'
  const meta = product.rating ? `${safe(product.rating)}${product.reviews ? ` (${safe(product.reviews)})` : ''}` : ''
  return `<span class="stars">${safe(starText)}</span><div class="rating-meta">${meta}</div>`
}

function renderDate(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const date = product.available_date ? safe(product.available_date) : '<span class="empty">—</span>'
  const days = product.available_days
    ? `<div class="days-line">${language === 'en' ? `Listed for ${safe(product.available_days)} days` : `上架 ${safe(product.available_days)} 天`}</div>`
    : ''
  return `<div class="date-line">${date}</div>${days}`
}

function renderCatPath(product: ProductRow): string {
  return `<div>${fmt(product.node_label_path || product.node_label_paths_locale)}</div>`
}

function renderBsr(product: ProductRow): string {
  const mainRank = product.bsr_list__main_rank
  const subRank = product.bsr_list__sub_rank
  const mainLabel = product.bsr_list__main_label
  const subLabel = product.bsr_list__sub_label
  if (!mainRank && !subRank) return '<span class="empty">—</span>'
  const main = mainRank ? `<div class="bsr-row main"><span class="lbl">${fmt(mainLabel)}</span><span class="rk">#${safe(mainRank)}</span></div>` : ''
  const sub = subRank ? `<div class="bsr-row sub"><span class="lbl">└ ${fmt(subLabel)}</span><span class="rk">#${safe(subRank)}</span></div>` : ''
  return `<div class="bsr-block">${main}${sub}</div>`
}

function renderSeller(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  return `<div class="seller-block"><div class="name">${fmt(product.seller_name)}</div><div class="nat">${language === 'en' ? 'Country:' : '国家:'} ${fmt(product.seller_dto__nation_name)}</div></div>`
}

function renderSales(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const parent = language === 'en' ? 'Parent sales:' : '父体销量:'
  const child = language === 'en' ? 'Child monthly sales:' : '子体月销:'
  return `<div class="sales-cell"><div><span class="lbl">${parent}</span> <span class="parent-u">${fmt(product.units)}</span></div><div><span class="lbl">${child}</span> <span class="child-u">${fmt(product.month_units)}</span></div></div>`
}

function renderAmount(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const growth = Number(product.amount_growth)
  const hasGrowth = product.amount_growth != null && product.amount_growth !== '' && !Number.isNaN(growth)
  const growthText = hasGrowth ? `<span class="sub ${growth < 0 ? 'neg' : ''}">${growth > 0 ? '+' : ''}${safe(product.amount_growth)}%</span>` : ''
  const subAmount = product.sub_total_amount == null || product.sub_total_amount === -1 || product.sub_total_amount === '' ? null : product.sub_total_amount
  const currency = safe(product.currency || '$')
  return `<div class="sales-cell"><div><span class="lbl">${language === 'en' ? 'Parent:' : '父体:'}</span> <b class="amount">${currency}${fmt(product.amount)}</b> ${growthText}</div><div><span class="lbl">${language === 'en' ? 'Child:' : '子体:'}</span> <span class="child-u">${currency}${fmt(subAmount)}</span></div></div>`
}

function renderTrend(product: ProductRow, language: ProductDisplayLanguage = 'zh'): string {
  const child = parseTrend(product.amz_unit_trend)
  const parent = parseTrend(product.parent_unit_trend)
  if (!child.values.length && !parent.values.length) return `<span class="empty">${language === 'en' ? 'No trend' : '无趋势'}</span>`
  return `<div>${child.values.length ? sparkRow(language === 'en' ? 'Child' : '子体', child, '', language) : ''}${parent.values.length ? sparkRow(language === 'en' ? 'Parent' : '父体', parent, 'parent', language) : ''}</div>`
}

function sparkRow(label: string, trend: { values: Array<{ dk: string; sales: number }>; max: number; total: number }, className: string, language: ProductDisplayLanguage): string {
  const bars = trend.values
    .map((item) => {
      const height = Math.max(item.sales > 0 ? 6 : 2, (item.sales / trend.max) * 100)
      const month = `${item.dk.slice(0, 4)}-${item.dk.slice(4, 6)}`
      return `<div class="bar ${className} ${item.sales === 0 ? 'zero' : ''}" style="height:${height}%">${item.sales > 0 ? `<div class="val">${safe(item.sales)}</div>` : ''}<div class="tip">${safe(month)}${language === 'en' ? ': ' : '：'}${safe(item.sales)} ${language === 'en' ? 'units' : '件'}</div></div>`
    })
    .join('')
  const summary = language === 'en'
    ? `Total ${safe(trend.total)} · Peak ${safe(trend.max)} · ${safe(trend.values.length)} months`
    : `合计 ${safe(trend.total)} · 峰值 ${safe(trend.max)} · ${safe(trend.values.length)}月`
  return `<div class="spark-row"><div class="spark-label">${safe(label)} <span class="spark-sum">${summary}</span></div><div class="spark">${bars}</div></div>`
}
