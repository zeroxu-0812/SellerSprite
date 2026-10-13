<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ApiError, getTraffic } from '../api'
import type { ProductRow, TrafficResponse, TrafficShare } from '../types'
import { type ProductColumn, productColumns } from '../utils/columns'
import { exportCompetitorTableHtml, type ExportLanguage } from '../utils/exportHtml'
import {
  benchmarkLabels,
  buildCompetitorProfiles,
  type BenchmarkMetric,
} from '../utils/competitorAnalysis'
import CompetitorProfilePanel from './CompetitorProfilePanel.vue'

const props = defineProps<{
  products: ProductRow[]
  marketplace: string
}>()

const query = ref('')
const density = ref<'compact' | 'standard'>('compact')
const exportLanguage = ref<ExportLanguage>('zh')
const selectedKeys = ref(new Set(productColumns.map((column) => column.key)))
const selectedProduct = ref<ProductRow | null>(null)
const sortKey = ref<string>('amount')
const sortDirection = ref<'asc' | 'desc'>('desc')
const activeMetric = ref<BenchmarkMetric>('sales')
const baselineAsin = ref('')
const trafficQueuePaused = ref(false)
const trafficStates = reactive(new Map<string, RowTrafficState>())
let trafficGeneration = 0

type RowTrafficState =
  | { status: 'loading' }
  | { status: 'done'; response: TrafficResponse }
  | { status: 'error'; message: string }

const profiles = computed(() => buildCompetitorProfiles(props.products))
const visibleColumns = computed(() => productColumns.filter((column) => selectedKeys.value.has(column.key)))
const columnGroups = [
  { key: 'identity', label: '基础' },
  { key: 'market', label: '市场' },
  { key: 'seller', label: '卖家' },
  { key: 'performance', label: '表现' },
] as const
const benchmarkOptions = computed(() => Object.entries(benchmarkLabels) as Array<[BenchmarkMetric, string]>)
const selectedProfile = computed(() => profiles.value.find((profile) => profile.product === selectedProduct.value) || profiles.value[0] || null)
const baselineProfile = computed(() => {
  if (!baselineAsin.value) return profiles.value[0] || null
  return profiles.value.find((profile, index) => productKey(profile.product, index) === baselineAsin.value) || profiles.value[0] || null
})

const filteredProducts = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  const products = profiles.value.map((profile) => profile.product)
  const filtered = keyword
    ? products.filter((product) =>
    ['asin', 'title', 'brand', 'seller_name', 'marketplace_code', 'marketplace_station'].some((key) =>
      String(product[key] ?? '').toLowerCase().includes(keyword),
    ),
  )
    : products
  const activeColumn = productColumns.find((column) => column.key === sortKey.value)
  if (!activeColumn?.sortKey) return filtered
  return [...filtered].sort((a, b) => compareProducts(a, b, activeColumn) * (sortDirection.value === 'asc' ? 1 : -1))
})

function toggleColumn(key: string) {
  const next = new Set(selectedKeys.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  selectedKeys.value = next
}

function toggleGroup(group: ProductColumn['group']) {
  const groupKeys = productColumns.filter((column) => column.group === group).map((column) => column.key)
  const next = new Set(selectedKeys.value)
  const allVisible = groupKeys.every((key) => next.has(key))
  groupKeys.forEach((key) => {
    if (allVisible) {
      next.delete(key)
    } else {
      next.add(key)
    }
  })
  selectedKeys.value = next
}

function isGroupActive(group: ProductColumn['group']) {
  return productColumns.filter((column) => column.group === group).every((column) => selectedKeys.value.has(column.key))
}

function setSort(column: ProductColumn) {
  if (!column.sortKey) return
  if (sortKey.value === column.key) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = column.key
    sortDirection.value = column.sortType === 'text' || column.sortType === 'date' ? 'asc' : 'desc'
  }
}

function compareProducts(a: ProductRow, b: ProductRow, column: ProductColumn): number {
  const key = column.sortKey || column.key
  const av = sortableValue(a[key], column.sortType)
  const bv = sortableValue(b[key], column.sortType)
  if (av == null && bv == null) return 0
  if (av == null) return 1
  if (bv == null) return -1
  if (typeof av === 'number' && typeof bv === 'number') return av - bv
  return String(av).localeCompare(String(bv), 'zh-Hans-CN')
}

function sortableValue(value: unknown, type: ProductColumn['sortType']): string | number | null {
  if (value == null || value === '') return null
  if (type === 'number') {
    const number = Number(String(value).replaceAll(',', ''))
    return Number.isFinite(number) ? number : null
  }
  if (type === 'date') {
    const time = Date.parse(String(value))
    return Number.isFinite(time) ? time : null
  }
  return String(value).toLowerCase()
}

function productKey(product: ProductRow, index = 0): string {
  const marketplace = String(product.marketplace_code || product.marketplace_station || props.marketplace || 'com').toLowerCase()
  return `${marketplace}:${String(product.asin || product.title || index)}`
}

function rowKey(product: ProductRow, index: number): string {
  return productKey(product, index)
}

function marketplaceFor(product: ProductRow): string {
  return String(product.marketplace_code || props.marketplace || 'com')
}

function trafficIdentity(product: ProductRow) {
  const asin = String(product.asin || '').trim().toUpperCase()
  if (!/^[A-Z0-9]{10}$/.test(asin)) return null
  const marketplace = marketplaceFor(product).trim().toLowerCase()
  return { asin, marketplace, key: `${marketplace}:${asin}` }
}

function trafficState(product: ProductRow) {
  const identity = trafficIdentity(product)
  return identity ? trafficStates.get(identity.key) : undefined
}

function trafficSnapshot(product: ProductRow): TrafficShare | null {
  const state = trafficState(product)
  return state?.status === 'done' ? state.response.snapshot : null
}

function trafficErrorMessage(product: ProductRow) {
  const state = trafficState(product)
  return state?.status === 'error' ? state.message : ''
}

async function fetchProductTraffic(product: ProductRow) {
  const identity = trafficIdentity(product)
  if (!identity) return true
  trafficStates.set(identity.key, { status: 'loading' })
  try {
    const response = await getTraffic(identity.asin, identity.marketplace)
    trafficStates.set(identity.key, { status: 'done', response })
    return true
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    trafficStates.set(identity.key, { status: 'error', message })
    return !(error instanceof ApiError && (error.status === 401 || error.status === 429))
  }
}

async function loadTrafficQueue() {
  const generation = ++trafficGeneration
  trafficQueuePaused.value = false
  for (const product of props.products) {
    if (generation !== trafficGeneration) return
    const identity = trafficIdentity(product)
    if (!identity || trafficStates.has(identity.key)) continue
    const shouldContinue = await fetchProductTraffic(product)
    if (!shouldContinue) {
      trafficQueuePaused.value = true
      return
    }
  }
}

async function retryTraffic(product: ProductRow) {
  const shouldContinue = await fetchProductTraffic(product)
  if (shouldContinue) void loadTrafficQueue()
}

function formatTraffic(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function trafficPieStyle(share: TrafficShare) {
  const organicEnd = Math.max(0, Math.min(100, share.organic * 100))
  const adsEnd = Math.max(organicEnd, Math.min(100, (share.organic + share.ads) * 100))
  return {
    background: `conic-gradient(#159a69 0 ${organicEnd}%, #1687d2 ${organicEnd}% ${adsEnd}%, #d98927 ${adsEnd}% 100%)`,
  }
}

function trafficTooltip(share: TrafficShare) {
  return `最近30天：自然 ${formatTraffic(share.organic)}，广告 ${formatTraffic(share.ads)}，推荐 ${formatTraffic(share.recommendation)}`
}

function productTrafficPieStyle(product: ProductRow) {
  const share = trafficSnapshot(product)
  return share ? trafficPieStyle(share) : undefined
}

function productTrafficTooltip(product: ProductRow) {
  const share = trafficSnapshot(product)
  return share ? trafficTooltip(share) : '暂无流量数据'
}

function productTrafficPercent(product: ProductRow, key: 'organic' | 'ads') {
  const share = trafficSnapshot(product)
  return share ? formatTraffic(share[key]) : '--'
}

function renderExportTraffic(product: ProductRow) {
  const identity = trafficIdentity(product)
  if (!identity) return '<span class="traffic-export-status">无有效 ASIN</span>'
  const state = trafficState(product)
  if (!state) {
    const label = trafficQueuePaused.value ? '队列已暂停' : '尚未读取'
    return `<span class="traffic-export-status">${label}</span>`
  }
  if (state.status === 'loading') return '<span class="traffic-export-status">读取中</span>'
  if (state.status === 'error') return '<span class="traffic-export-status error">读取失败</span>'
  const share = state.response.snapshot
  if (!share) return '<span class="traffic-export-status">暂无数据</span>'
  const organicEnd = Math.max(0, Math.min(100, share.organic * 100))
  const adsEnd = Math.max(organicEnd, Math.min(100, (share.organic + share.ads) * 100))
  const tooltip = trafficTooltip(share)
  return `<div class="traffic-export-result" title="${tooltip}">
    <div class="traffic-export-pie" style="background:conic-gradient(#159a69 0 ${organicEnd}%,#1687d2 ${organicEnd}% ${adsEnd}%,#d98927 ${adsEnd}% 100%)"></div>
    <div class="traffic-export-values">
      <span><i class="organic"></i>自然 <b>${formatTraffic(share.organic)}</b></span>
      <span><i class="ads"></i>广告 <b>${formatTraffic(share.ads)}</b></span>
    </div>
  </div>`
}

const trafficExportColumn: ProductColumn = {
  key: 'traffic_30d',
  label: '近30天流量占比',
  className: 'traffic-export-cell',
  group: 'performance',
  render: renderExportTraffic,
}

function exportHtml() {
  const sourceColumn = productColumns.find((column) => column.key === 'marketplace_code')
  const selectedExportColumns = sourceColumn && !visibleColumns.value.some((column) => column.key === sourceColumn.key)
    ? [sourceColumn, ...visibleColumns.value]
    : visibleColumns.value
  const exportColumns = selectedExportColumns.flatMap((column) =>
    column.key === 'amount' ? [column, trafficExportColumn] : [column],
  )
  exportCompetitorTableHtml(filteredProducts.value, exportColumns, props.marketplace, exportLanguage.value)
}

watch(() => props.products, () => loadTrafficQueue(), { immediate: true })
onUnmounted(() => { trafficGeneration += 1 })

</script>

<template>
  <section class="competitor-workspace" :data-density="density">
    <div class="table-commandbar">
      <div>
        <h2>核心竞手矩阵</h2>
        <p>{{ filteredProducts.length }} / {{ products.length }}</p>
      </div>

      <div class="table-tools">
        <input v-model="query" type="search" placeholder="搜索标题 / ASIN / 品牌 / 卖家" />
        <div class="export-language-control">
          <span>导出语言</span>
          <div class="export-language-toggle" role="group" aria-label="HTML 导出语言">
            <button :class="{ active: exportLanguage === 'zh' }" type="button" @click="exportLanguage = 'zh'">中文</button>
            <button :class="{ active: exportLanguage === 'en' }" type="button" @click="exportLanguage = 'en'">English</button>
          </div>
        </div>
        <button class="export-button" type="button" :disabled="!filteredProducts.length" @click="exportHtml">
          {{ exportLanguage === 'en' ? 'Export English HTML' : '导出中文 HTML' }}
        </button>
        <div class="density-toggle" role="group" aria-label="表格密度">
          <button :class="{ active: density === 'compact' }" type="button" @click="density = 'compact'">紧凑</button>
          <button :class="{ active: density === 'standard' }" type="button" @click="density = 'standard'">标准</button>
        </div>
      </div>
    </div>

    <div class="benchmark-bar">
      <div class="benchmark-modes">
        <span>对标维度</span>
        <button
          v-for="[key, label] in benchmarkOptions"
          :key="key"
          type="button"
          :class="{ active: activeMetric === key }"
          @click="activeMetric = key"
        >
          {{ label }}
        </button>
      </div>
      <label>
        基准竞手
        <select v-model="baselineAsin">
          <option value="">默认第一名</option>
            <option v-for="(profile, index) in profiles" :key="productKey(profile.product, index)" :value="productKey(profile.product, index)">
            {{ profile.product.asin }} · {{ profile.product.marketplace_station || profile.product.marketplace_code || '未知站点' }} · {{ profile.product.brand || profile.product.seller_name || '未知' }}
          </option>
        </select>
      </label>
    </div>

    <div class="column-manager">
      <span>列</span>
      <button
        v-for="group in columnGroups"
        :key="group.key"
        type="button"
        class="group-chip"
        :class="{ active: isGroupActive(group.key) }"
        @click="toggleGroup(group.key)"
      >
        {{ group.label }}
      </button>
      <i />
      <button
        v-for="column in productColumns"
        :key="column.key"
        type="button"
        :class="{ active: selectedKeys.has(column.key) }"
        @click="toggleColumn(column.key)"
      >
        {{ column.label }}
      </button>
    </div>

    <div class="competitor-stack">
      <div class="table-frame">
        <table class="product-table">
          <thead>
            <tr>
              <template v-for="column in visibleColumns" :key="column.key">
                <th :class="column.align ? `align-${column.align}` : ''">
                  <button
                    type="button"
                    class="sort-button"
                    :class="{ sortable: column.sortKey, active: sortKey === column.key }"
                    :disabled="!column.sortKey"
                    @click="setSort(column)"
                  >
                    <span>{{ column.label }}</span>
                    <b v-if="sortKey === column.key">{{ sortDirection === 'asc' ? '▲' : '▼' }}</b>
                  </button>
                </th>
                <th v-if="column.key === 'amount'" class="traffic-inline-header">近30天流量占比</th>
              </template>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredProducts.length">
              <td class="table-empty" :colspan="(visibleColumns.length || 1) + (visibleColumns.some((column) => column.key === 'amount') ? 1 : 0)">
                没有匹配竞手。调整搜索或重新抓取。
              </td>
            </tr>
            <tr
              v-for="(product, index) in filteredProducts"
              :key="rowKey(product, index)"
              :class="{ selected: selectedProduct === product }"
              @click="selectedProduct = product"
            >
              <template v-for="column in visibleColumns" :key="column.key">
                <td
                  :class="[column.className, column.align ? `align-${column.align}` : '']"
                  v-html="column.render(product)"
                />
                <td v-if="column.key === 'amount'" class="traffic-inline-cell">
                  <div v-if="!trafficIdentity(product)" class="traffic-inline-status">无有效 ASIN</div>
                  <div v-else-if="trafficQueuePaused && !trafficState(product)" class="traffic-inline-status error">队列已暂停</div>
                  <div v-else-if="!trafficState(product) || trafficState(product)?.status === 'loading'" class="traffic-inline-status loading">
                    <i />{{ trafficState(product) ? '读取中' : '等待读取' }}
                  </div>
                  <div v-else-if="trafficState(product)?.status === 'error'" class="traffic-inline-status error">
                    <span>读取失败</span>
                    <button type="button" :title="trafficErrorMessage(product)" @click.stop="retryTraffic(product)">重试</button>
                  </div>
                  <div v-else-if="trafficSnapshot(product)" class="traffic-inline-result">
                    <div
                      class="traffic-mini-pie"
                      :style="productTrafficPieStyle(product)"
                      :title="productTrafficTooltip(product)"
                      role="img"
                      :aria-label="productTrafficTooltip(product)"
                    />
                    <div class="traffic-inline-values">
                      <span><i class="organic" />自然 <b>{{ productTrafficPercent(product, 'organic') }}</b></span>
                      <span><i class="ads" />广告 <b>{{ productTrafficPercent(product, 'ads') }}</b></span>
                    </div>
                  </div>
                  <div v-else class="traffic-inline-status">暂无数据</div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>

      <CompetitorProfilePanel
        :profile="selectedProfile"
        :baseline="baselineProfile"
        :metric="activeMetric"
        :marketplace="selectedProfile ? marketplaceFor(selectedProfile.product) : marketplace"
      />
    </div>
  </section>
</template>
