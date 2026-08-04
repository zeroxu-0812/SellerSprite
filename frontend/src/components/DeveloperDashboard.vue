<script setup lang="ts">
import { computed } from 'vue'
import type { MarketplaceCode, UsageResponse } from '../types'
import { marketplaceByCode, marketplaces } from '../utils/marketplaces'

const props = defineProps<{
  usage: UsageResponse | null
  loading: boolean
  error: string
}>()

defineEmits<{
  home: []
  analyze: []
  refresh: []
  logout: []
}>()

const rows = computed(() => {
  return marketplaces
    .map((marketplace) => ({
      ...marketplace,
      count: props.usage?.marketplaces[marketplace.code]?.count ?? 0,
      lastSearchedAt: props.usage?.marketplaces[marketplace.code]?.last_searched_at ?? null,
    }))
    .sort((a, b) => b.count - a.count)
})

const total = computed(() => props.usage?.total ?? 0)
const maximum = computed(() => Math.max(1, ...rows.value.map((row) => row.count)))
const activeSites = computed(() => rows.value.filter((row) => row.count > 0).length)
const topSite = computed(() => rows.value[0])
const todaySearches = computed(() => {
  const today = new Date().toDateString()
  return props.usage?.recent.filter((item) => new Date(item.searched_at).toDateString() === today).length ?? 0
})

const recent = computed(() => (props.usage?.recent ?? []).slice(0, 6).map((event) => ({
  ...event,
  marketplaceInfo: marketplaceByCode[event.marketplace] ?? marketplaceByCode.com,
})))

function share(count: number) {
  return total.value ? (count / total.value) * 100 : 0
}

function formatTime(value: string | null) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

<template>
  <main class="developer-shell">
    <aside class="developer-sidebar">
      <div class="developer-brand">
        <img src="/oceanwing-logo.jpg" alt="Oceanwing" />
        <div><strong>SellerSprite</strong><span>开发者工作台</span></div>
      </div>
      <div class="developer-nav-label">数据管理</div>
      <nav>
        <button class="active" type="button"><span>▦</span>使用概览</button>
        <button type="button" @click="$emit('analyze')"><span>⌕</span>竞手分析</button>
        <button type="button" @click="$emit('home')"><span>⌂</span>返回首页</button>
      </nav>
      <div class="developer-environment"><span>当前环境</span><b>Production · 正常</b></div>
    </aside>

    <section class="developer-main">
      <header class="developer-topbar">
        <h1>开发者工作台</h1>
        <div>
          <span>统计范围：累计</span>
          <button type="button" :disabled="loading" @click="$emit('refresh')">刷新</button>
          <button class="developer-logout" type="button" @click="$emit('logout')">退出登录</button>
        </div>
      </header>

      <div class="developer-content">
        <header class="developer-heading">
          <div><h2>搜索使用概览</h2><p>各国家站点累计搜索调用情况</p></div>
          <span>数据实时累计</span>
        </header>

        <p v-if="error" class="error-banner">{{ error }}</p>

        <section class="usage-metrics">
          <article><span>累计搜索次数</span><b>{{ total.toLocaleString('zh-CN') }}</b><em>全部站点</em></article>
          <article><span>今日搜索</span><b>{{ todaySearches.toLocaleString('zh-CN') }}</b><em>按任务累计</em></article>
          <article><span>活跃站点</span><b>{{ activeSites }}</b><em>共 7 个站点</em></article>
          <article><span>使用最多</span><b>{{ topSite.flag }} {{ topSite.label }}</b><em>{{ topSite.count.toLocaleString('zh-CN') }} 次</em></article>
        </section>

        <section class="usage-grid">
          <div class="usage-panel">
            <header><h3>国家站点累计搜索量</h3><span>按使用次数排序</span></header>
            <div class="usage-bars">
              <div v-for="row in rows" :key="row.code" class="usage-bar-row">
                <b>{{ row.flag }} {{ row.label }}</b>
                <div><i :style="{ width: `${(row.count / maximum) * 100}%` }" /></div>
                <span>{{ row.count.toLocaleString('zh-CN') }}</span>
              </div>
            </div>
          </div>

          <div class="usage-panel">
            <header><h3>最近搜索</h3><span>最新 6 条</span></header>
            <div v-if="recent.length" class="usage-recent-list">
              <div v-for="item in recent" :key="`${item.searched_at}-${item.marketplace}`">
                <i>{{ item.marketplaceInfo.flag }}</i>
                <p><b>{{ item.marketplaceInfo.label }}站搜索</b><span>{{ formatTime(item.searched_at) }} · {{ item.asin_count }} ASIN</span></p>
              </div>
            </div>
            <div v-else class="usage-empty">暂无搜索记录</div>
          </div>
        </section>

        <section class="usage-panel usage-detail-panel">
          <header><h3>站点使用明细</h3><span>每次创建搜索任务自动累计 +1</span></header>
          <div class="usage-detail-table">
            <div class="usage-detail-row head"><span>国家站点</span><span>累计搜索</span><span>使用占比</span><span>最近搜索</span></div>
            <div v-for="row in rows" :key="row.code" class="usage-detail-row">
              <b>{{ row.flag }} {{ row.label }}</b>
              <strong>{{ row.count.toLocaleString('zh-CN') }}</strong>
              <div class="usage-share"><i><b :style="{ width: `${share(row.count)}%` }" /></i><span>{{ share(row.count).toFixed(1) }}%</span></div>
              <span>{{ formatTime(row.lastSearchedAt) }}</span>
            </div>
          </div>
        </section>
      </div>
    </section>
  </main>
</template>
