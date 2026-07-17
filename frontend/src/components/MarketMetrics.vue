<script setup lang="ts">
import { computed } from 'vue'
import type { MarketOverview } from '../types'
import { integer, money } from '../utils/formatters'

const props = defineProps<{ overview: MarketOverview }>()

const metrics = computed(() => [
  { label: '样本', value: String(props.overview.sample_size), tone: 'neutral' },
  { label: '均价', value: money(props.overview.avg_price), tone: 'neutral' },
  { label: '均评分', value: props.overview.avg_rating?.toFixed(2) ?? '-', tone: 'neutral' },
  { label: '总销量', value: integer(props.overview.total_units), tone: 'strong' },
  { label: '总销售额', value: money(props.overview.total_amount), tone: 'strong' },
  {
    label: 'Top10 集中度',
    value: props.overview.top10_units_share == null ? '-' : `${(props.overview.top10_units_share * 100).toFixed(1)}%`,
    tone: 'accent',
  },
])
</script>

<template>
  <section class="metric-strip">
    <article v-for="metric in metrics" :key="metric.label" class="metric-card" :data-tone="metric.tone">
      <span>{{ metric.label }}</span>
      <strong>{{ metric.value }}</strong>
    </article>
  </section>
</template>

