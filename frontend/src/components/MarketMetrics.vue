<script setup lang="ts">
import { computed } from 'vue'
import type { MarketOverview, MarketplaceCode } from '../types'
import { integer, money } from '../utils/formatters'
import { marketplaceByCode } from '../utils/marketplaces'

const props = defineProps<{
  overview: MarketOverview
  marketplaceOverviews?: Record<string, MarketOverview>
  marketplace: string
}>()

const overviewEntries = computed(() => {
  const entries = Object.entries(props.marketplaceOverviews ?? {})
  return entries.length ? entries : [[props.marketplace, props.overview] as [string, MarketOverview]]
})

function metricsFor(overview: MarketOverview, marketplace: string) {
  return [
    { label: '样本', value: String(overview.sample_size), tone: 'neutral' },
    { label: '均价', value: money(overview.avg_price, marketplace), tone: 'neutral' },
    { label: '均评分', value: overview.avg_rating?.toFixed(2) ?? '-', tone: 'neutral' },
    { label: '总销量', value: integer(overview.total_units), tone: 'strong' },
    { label: '总销售额', value: money(overview.total_amount, marketplace), tone: 'strong' },
    {
      label: 'Top10 集中度',
      value: overview.top10_units_share == null ? '-' : `${(overview.top10_units_share * 100).toFixed(1)}%`,
      tone: 'accent',
    },
  ]
}

function marketplaceInfo(code: string) {
  return marketplaceByCode[code as MarketplaceCode] ?? marketplaceByCode.com
}
</script>

<template>
  <section class="metrics-by-marketplace">
    <article v-for="[code, overview] in overviewEntries" :key="code" class="marketplace-metric-group">
      <header>
        <div><span>{{ marketplaceInfo(code).flag }}</span><strong>{{ marketplaceInfo(code).label }}站</strong></div>
        <small>{{ marketplaceInfo(code).currency }}</small>
      </header>
      <div class="metric-strip">
        <article v-for="metric in metricsFor(overview, code)" :key="metric.label" class="metric-card" :data-tone="metric.tone">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
    </article>
  </section>
</template>
