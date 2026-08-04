import type { MarketplaceCode } from '../types'

export interface MarketplaceOption {
  code: MarketplaceCode
  label: string
  flag: string
  currency: string
}

export const marketplaces: MarketplaceOption[] = [
  { code: 'com', label: '美国', flag: '🇺🇸', currency: 'USD' },
  { code: 'de', label: '德国', flag: '🇩🇪', currency: 'EUR' },
  { code: 'uk', label: '英国', flag: '🇬🇧', currency: 'GBP' },
  { code: 'jp', label: '日本', flag: '🇯🇵', currency: 'JPY' },
  { code: 'fr', label: '法国', flag: '🇫🇷', currency: 'EUR' },
  { code: 'es', label: '西班牙', flag: '🇪🇸', currency: 'EUR' },
  { code: 'it', label: '意大利', flag: '🇮🇹', currency: 'EUR' },
]

export const marketplaceByCode = Object.fromEntries(
  marketplaces.map((marketplace) => [marketplace.code, marketplace]),
) as Record<MarketplaceCode, MarketplaceOption>
