<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ApiError, createJob, getJob, getUsage, loginAdmin } from './api'
import AdminLogin from './components/AdminLogin.vue'
import DeveloperDashboard from './components/DeveloperDashboard.vue'
import FailurePanel from './components/FailurePanel.vue'
import LandingPage from './components/LandingPage.vue'
import MarketMetrics from './components/MarketMetrics.vue'
import ProductTable from './components/ProductTable.vue'
import RunControlPanel from './components/RunControlPanel.vue'
import type { MarketplaceCode, RunProgress, RunResponse, UsageResponse } from './types'
import { marketplaceByCode } from './utils/marketplaces'

const logoUrl = `${import.meta.env.BASE_URL}oceanwing-logo.jpg`

type AppPage = 'landing' | 'analyze' | 'results' | 'dashboard'

const page = ref<AppPage>(pageFromHash())
const rawInput = ref('')
const selectedMarketplaces = ref<MarketplaceCode[]>(['com'])
const includeSummary = ref(false)
const includeDetails = ref(false)
const workers = ref(2)
const loading = ref(false)
const error = ref('')
const result = ref<RunResponse | null>(null)
const progress = ref<RunProgress | null>(null)
const usage = ref<UsageResponse | null>(null)
const usageLoading = ref(false)
const usageError = ref('')
const adminToken = ref(readAdminToken())
const adminLoginLoading = ref(false)
const adminLoginError = ref('')
let pollTimer: number | undefined

const ADMIN_SESSION_KEY = 'sellersprite_admin_session'

const asins = computed(() => {
  const seen = new Set<string>()
  const matches = rawInput.value.toUpperCase().match(/[A-Z0-9]{10}/g) ?? []
  return matches.filter((asin) => {
    if (seen.has(asin)) return false
    seen.add(asin)
    return true
  })
})

const recentSearches = computed(() => (usage.value?.recent ?? []).slice(0, 5).map((item) => ({
  ...item,
  marketplaceInfo: marketplaceByCode[item.marketplace] ?? marketplaceByCode.com,
})))

function pageFromHash(): AppPage {
  const route = window.location.hash.replace(/^#\/?/, '')
  const pageName = route.split('/')[0]
  if (pageName === 'analyze' || pageName === 'results' || pageName === 'dashboard') return pageName
  return 'landing'
}

function readAdminToken() {
  try {
    return window.sessionStorage.getItem('sellersprite_admin_session') || ''
  } catch {
    return ''
  }
}

function clearAdminSession() {
  adminToken.value = ''
  usage.value = null
  try {
    window.sessionStorage.removeItem(ADMIN_SESSION_KEY)
  } catch {
    // Session storage may be unavailable in privacy-restricted browsers.
  }
}

function navigate(next: AppPage) {
  const hash = next === 'landing' ? '#/' : `#/${next}`
  if (window.location.hash === hash) {
    page.value = next
    handlePageEntry(next)
    return
  }
  window.location.hash = hash
}

function syncRoute() {
  const next = pageFromHash()
  page.value = next
  handlePageEntry(next)
}

function handlePageEntry(next: AppPage) {
  if (next === 'analyze' || next === 'dashboard') {
    if (adminToken.value) {
      void refreshUsage()
    } else {
      usage.value = null
      usageError.value = ''
    }
  }
}

async function refreshUsage() {
  if (!adminToken.value) return
  usageLoading.value = true
  usageError.value = ''
  try {
    usage.value = await getUsage(adminToken.value)
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      clearAdminSession()
      adminLoginError.value = '登录已过期，请重新验证管理员账号。'
    }
    usageError.value = err instanceof Error ? err.message : String(err)
  } finally {
    usageLoading.value = false
  }
}

async function loginAdminUser(username: string, password: string) {
  adminLoginLoading.value = true
  adminLoginError.value = ''
  try {
    const session = await loginAdmin(username, password)
    adminToken.value = session.token
    try {
      window.sessionStorage.setItem(ADMIN_SESSION_KEY, session.token)
    } catch {
      // The current tab can still use the in-memory token.
    }
    await refreshUsage()
  } catch (err) {
    adminLoginError.value = err instanceof Error ? err.message : String(err)
  } finally {
    adminLoginLoading.value = false
  }
}

function logoutAdmin() {
  clearAdminSession()
  adminLoginError.value = ''
  navigate('landing')
}

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
  navigate('results')
  try {
    progress.value = await createJob({
      asins: asins.value,
      marketplaces: selectedMarketplaces.value,
      marketplace: selectedMarketplaces.value[0] || 'com',
      includeSummary: includeSummary.value,
      includeDetails: includeDetails.value,
      workers: workers.value,
    })
    if (adminToken.value) void refreshUsage()
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
  if (!progress.value) return '正在创建抓取任务'
  const total = progress.value.total || asins.value.length
  const current = Math.min(progress.value.completed, total)
  const asin = progress.value.current_asin ? ` · ${progress.value.current_asin}` : ''
  return `${progress.value.stage} ${current}/${total}${asin}`
})

const resultMarketplace = computed(() => {
  const code = result.value?.products.find((product) => product.marketplace_code)?.marketplace_code
  return String(code || selectedMarketplaces.value[0] || 'com')
})

function formatUsageTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

onMounted(() => {
  window.addEventListener('hashchange', syncRoute)
  handlePageEntry(page.value)
})

onUnmounted(() => {
  stopPolling()
  window.removeEventListener('hashchange', syncRoute)
})
</script>

<template>
  <LandingPage v-if="page === 'landing'" @analyze="navigate('analyze')" @dashboard="navigate('dashboard')" />

  <AdminLogin
    v-else-if="page === 'dashboard' && !adminToken"
    :loading="adminLoginLoading"
    :error="adminLoginError"
    @login="loginAdminUser"
    @home="navigate('landing')"
  />

  <DeveloperDashboard
    v-else-if="page === 'dashboard'"
    :usage="usage"
    :loading="usageLoading"
    :error="usageError"
    @home="navigate('landing')"
    @analyze="navigate('analyze')"
    @refresh="refreshUsage"
    @logout="logoutAdmin"
  />

  <main v-else class="app-shell">
    <header class="app-header">
      <button class="brand-block brand-button" type="button" @click="navigate('landing')">
        <img class="app-logo" :src="logoUrl" alt="Oceanwing" />
        <div><strong>SellerSprite</strong><span>竞手分析</span></div>
      </button>
      <div class="app-header-actions">
        <span class="service-status">● 服务正常</span>
        <button type="button" @click="navigate('dashboard')">使用统计</button>
        <button type="button" @click="navigate('landing')">返回首页</button>
      </div>
    </header>

    <div v-if="page === 'results' && (loading || progress)" class="progress-strip">
      <div class="progress-meta">
        <span>{{ progressText }}</span>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="progress-track"><i :style="{ width: `${progressPercent}%` }" /></div>
    </div>

    <div class="page-content app-page-content">
      <template v-if="page === 'analyze'">
        <header class="app-page-heading">
          <h1>竞手分析工作台</h1>
          <div><span>已识别 ASIN</span><b>{{ asins.length }}</b></div>
        </header>

        <RunControlPanel
          v-model:raw-input="rawInput"
          v-model:selected-marketplaces="selectedMarketplaces"
          v-model:include-summary="includeSummary"
          v-model:include-details="includeDetails"
          v-model:workers="workers"
          :asin-count="asins.length"
          :loading="loading"
          :error="error"
          @run="run"
        />

        <section v-if="adminToken" class="recent-search-panel">
          <header><h2>最近搜索任务</h2><button type="button" @click="navigate('dashboard')">查看使用统计</button></header>
          <div class="recent-search-row head"><span>站点</span><span>ASIN 数量</span><span>搜索时间</span><span>状态</span></div>
          <div v-for="item in recentSearches" :key="`${item.searched_at}-${item.marketplace}`" class="recent-search-row">
            <b>{{ item.marketplaceInfo.flag }} {{ item.marketplaceInfo.label }}</b>
            <span>{{ item.asin_count }}</span>
            <span>{{ formatUsageTime(item.searched_at) }}</span>
            <strong>已创建</strong>
          </div>
          <div v-if="!recentSearches.length" class="recent-search-empty">暂无搜索任务</div>
        </section>
        <section v-else class="recent-search-locked">
          <div><strong>查询历史已受保护</strong><span>进入工作台并完成管理员验证后，可查看最近搜索任务。</span></div>
          <button type="button" @click="navigate('dashboard')">管理员登录</button>
        </section>
      </template>

      <template v-else>
        <header class="app-page-heading result-heading">
          <h1>抓取数据结果</h1>
          <button type="button" @click="navigate('analyze')">重新分析</button>
        </header>

        <p v-if="error" class="error-banner result-error">{{ error }}</p>

        <section v-if="loading && !result" class="result-loading">
          <span>{{ progressPercent }}%</span>
          <h2>{{ progressText }}</h2>
        </section>

        <section v-else-if="!result" class="empty-state result-empty">
          <h2>暂无抓取数据</h2>
          <button type="button" @click="navigate('analyze')">开始分析</button>
        </section>

        <section v-else class="workbench result-workbench">
          <MarketMetrics
            :overview="result.overview"
            :marketplace-overviews="result.marketplace_overviews"
            :marketplace="resultMarketplace"
          />
          <FailurePanel v-if="result.failures.length" :failures="result.failures" />
          <ProductTable :products="result.products" :marketplace="resultMarketplace" />
        </section>
      </template>
    </div>
  </main>
</template>
