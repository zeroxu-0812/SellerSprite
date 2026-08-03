<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { createJob, getJob } from './api'
import FailurePanel from './components/FailurePanel.vue'
import MarketMetrics from './components/MarketMetrics.vue'
import ProductTable from './components/ProductTable.vue'
import RunControlPanel from './components/RunControlPanel.vue'
import type { MarketplaceCode, RunProgress, RunResponse } from './types'

const rawInput = ref('')
const marketplace = ref<MarketplaceCode>('com')
const includeSummary = ref(false)
const includeDetails = ref(false)
const workers = ref(2)
const loading = ref(false)
const error = ref('')
const result = ref<RunResponse | null>(null)
const progress = ref<RunProgress | null>(null)
let pollTimer: number | undefined

const asins = computed(() => {
  const seen = new Set<string>()
  const matches = rawInput.value.toUpperCase().match(/[A-Z0-9]{10}/g) ?? []
  return matches.filter((asin) => {
    if (seen.has(asin)) return false
    seen.add(asin)
    return true
  })
})

async function run() {
  if (!asins.value.length) {
    error.value = '未识别到 ASIN，请检查输入。'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  progress.value = null
  stopPolling()
  try {
    progress.value = await createJob({
      asins: asins.value,
      marketplace: marketplace.value,
      includeSummary: includeSummary.value,
      includeDetails: includeDetails.value,
      workers: workers.value,
    })
    pollProgress(progress.value.job_id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    loading.value = false
    progress.value = null
  }
}

async function pollProgress(jobId: string) {
  try {
    const next = await getJob(jobId)
    progress.value = next
    if (next.status === 'done' && next.result) {
      result.value = next.result
      loading.value = false
      stopPolling()
      return
    }
    if (next.status === 'error') {
      error.value = next.error || '运行失败'
      loading.value = false
      stopPolling()
      return
    }
    pollTimer = window.setTimeout(() => pollProgress(jobId), 1000)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    loading.value = false
    stopPolling()
  }
}

function stopPolling() {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = undefined
  }
}

const progressPercent = computed(() => {
  if (!progress.value?.total) return 0
  return Math.round((progress.value.completed / progress.value.total) * 100)
})

const progressText = computed(() => {
  if (!progress.value) return ''
  const total = progress.value.total || asins.value.length
  const current = Math.min(progress.value.completed, total)
  const asin = progress.value.current_asin ? ` · ${progress.value.current_asin}` : ''
  return `${progress.value.stage} ${current}/${total}${asin}`
})

const resultMarketplace = computed(() => {
  const station = result.value?.products.find((product) => product.marketplace_station)?.marketplace_station
  return String(station || marketplace.value)
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <div class="brand-block">
        <span class="brand-mark">SS</span>
        <div>
          <h1>竞手分析</h1>
        </div>
      </div>
      <div class="run-status" :class="{ busy: loading }">
        <span>{{ loading ? '抓取中' : '就绪' }}</span>
        <b>{{ asins.length }}</b>
      </div>
    </header>

    <div v-if="progress" class="progress-strip">
      <div class="progress-meta">
        <span>{{ progressText }}</span>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="progress-track">
        <i :style="{ width: `${progressPercent}%` }" />
      </div>
    </div>

    <div class="page-content">
      <RunControlPanel
        v-model:raw-input="rawInput"
        v-model:marketplace="marketplace"
        v-model:include-summary="includeSummary"
        v-model:include-details="includeDetails"
        v-model:workers="workers"
        :asin-count="asins.length"
        :loading="loading"
        :error="error"
        @run="run"
      />

      <section class="workbench">
        <div v-if="!result" class="empty-state">
          <h2>输入 ASIN 后开始分析</h2>
        </div>

        <template v-else>
          <MarketMetrics :overview="result.overview" :marketplace="resultMarketplace" />
          <FailurePanel v-if="result.failures.length" :failures="result.failures" />
          <ProductTable :products="result.products" :marketplace="resultMarketplace" />
        </template>
      </section>
    </div>
  </main>
</template>
