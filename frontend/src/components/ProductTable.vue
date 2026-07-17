<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ProductRow } from '../types'
import { type ProductColumn, productColumns } from '../utils/columns'
import { exportCompetitorTableHtml } from '../utils/exportHtml'
import {
  benchmarkLabels,
  buildCompetitorProfiles,
  type BenchmarkMetric,
} from '../utils/competitorAnalysis'
import CompetitorProfilePanel from './CompetitorProfilePanel.vue'

const props = defineProps<{
  products: ProductRow[]
}>()

const query = ref('')
const density = ref<'compact' | 'standard'>('compact')
const selectedKeys = ref(new Set(productColumns.map((column) => column.key)))
const selectedProduct = ref<ProductRow | null>(null)
const sortKey = ref<string>('amount')
const sortDirection = ref<'asc' | 'desc'>('desc')
const activeMetric = ref<BenchmarkMetric>('sales')
const baselineAsin = ref('')

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
  return profiles.value.find((profile) => profile.product.asin === baselineAsin.value) || profiles.value[0] || null
})

const filteredProducts = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  const products = profiles.value.map((profile) => profile.product)
  const filtered = keyword
    ? products.filter((product) =>
    ['asin', 'title', 'brand', 'seller_name'].some((key) =>
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

function rowKey(product: ProductRow, index: number): string {
  return String(product.asin || product.title || index)
}

function exportHtml() {
  exportCompetitorTableHtml(filteredProducts.value, visibleColumns.value)
}

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
        <button class="export-button" type="button" :disabled="!filteredProducts.length" @click="exportHtml">
          导出 HTML
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
          <option v-for="profile in profiles" :key="String(profile.product.asin)" :value="String(profile.product.asin)">
            {{ profile.product.asin }} · {{ profile.product.brand || profile.product.seller_name || '未知' }}
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
              <th v-for="column in visibleColumns" :key="column.key" :class="column.align ? `align-${column.align}` : ''">
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
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredProducts.length">
              <td class="table-empty" :colspan="visibleColumns.length || 1">
                没有匹配竞手。调整搜索或重新抓取。
              </td>
            </tr>
            <tr
              v-for="(product, index) in filteredProducts"
              :key="rowKey(product, index)"
              :class="{ selected: selectedProduct === product }"
              @click="selectedProduct = product"
            >
              <td
                v-for="column in visibleColumns"
                :key="column.key"
                :class="[column.className, column.align ? `align-${column.align}` : '']"
                v-html="column.render(product)"
              />
            </tr>
          </tbody>
        </table>
      </div>

      <CompetitorProfilePanel :profile="selectedProfile" :baseline="baselineProfile" :metric="activeMetric" />
    </div>
  </section>
</template>
