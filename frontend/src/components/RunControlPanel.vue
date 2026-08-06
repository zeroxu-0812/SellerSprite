<script setup lang="ts">
import { computed } from 'vue'
import type { MarketplaceCode } from '../types'
import { marketplaces } from '../utils/marketplaces'

const props = defineProps<{
  rawInput: string
  selectedMarketplaces: MarketplaceCode[]
  includeSummary: boolean
  includeDetails: boolean
  workers: number
  asinCount: number
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'update:rawInput': [value: string]
  'update:selectedMarketplaces': [value: MarketplaceCode[]]
  'update:includeSummary': [value: boolean]
  'update:includeDetails': [value: boolean]
  'update:workers': [value: number]
  run: []
}>()

const modeLabel = computed(() => {
  if (props.includeSummary && props.includeDetails) return '完整抓取'
  if (props.includeDetails) return '五点增强'
  if (props.includeSummary) return '摘要增强'
  return '快速抓取'
})

function toggleSummary(checked: boolean) {
  emit('update:includeSummary', checked)
}

function toggleDetails(checked: boolean) {
  emit('update:includeDetails', checked)
}

function isMarketplaceSelected(code: MarketplaceCode) {
  return props.selectedMarketplaces.includes(code)
}

function toggleMarketplace(code: MarketplaceCode) {
  const selected = new Set(props.selectedMarketplaces)
  if (selected.has(code)) {
    if (selected.size === 1) return
    selected.delete(code)
  } else {
    selected.add(code)
  }
  emit('update:selectedMarketplaces', Array.from(selected))
}
</script>

<template>
  <section class="control-panel" aria-label="运行控制">
    <header class="control-panel-header">
      <div>
        <h2>分析设置</h2>
      </div>
      <div class="run-summary">
        <span>已识别</span>
        <b>{{ asinCount }}</b>
        <span>个 ASIN</span>
      </div>
    </header>

    <div class="control-panel-grid">
      <div class="panel-section">
        <div class="section-label">ASIN 列表</div>
        <label class="field">
          <span>ASIN 列表</span>
          <textarea
            :value="rawInput"
            placeholder="B0F1QHNFJP B09PVMTM9W&#10;支持空格、逗号、换行粘贴"
            @input="emit('update:rawInput', ($event.target as HTMLTextAreaElement).value)"
          />
        </label>
      </div>

      <div class="panel-section">
        <div class="section-label marketplace-section-heading">
          <span>目标站点</span>
          <b>{{ selectedMarketplaces.length }} 个已选</b>
        </div>
        <div class="marketplace-grid">
          <button
            v-for="item in marketplaces"
            :key="item.code"
            type="button"
            class="marketplace-button"
            :class="{ active: isMarketplaceSelected(item.code) }"
            :aria-pressed="isMarketplaceSelected(item.code)"
            @click="toggleMarketplace(item.code)"
          >
            <b><span>{{ item.flag }}</span>{{ item.label }}</b>
            <small>{{ isMarketplaceSelected(item.code) ? '已选择' : '未选择' }}</small>
          </button>
        </div>
      </div>

      <div class="panel-section run-settings">
        <div class="mode-heading">
          <div class="section-label">数据选项</div>
          <strong>{{ modeLabel }}</strong>
        </div>

        <div class="extraction-options">
          <label class="extraction-option" :class="{ active: includeSummary }">
            <input
              type="checkbox"
              :checked="includeSummary"
              @change="toggleSummary(($event.target as HTMLInputElement).checked)"
            />
            <span>
              <b>商品信息摘要</b>
              <small>产品定位、目标用户、主要场景、整体总结</small>
            </span>
          </label>

          <label class="extraction-option" :class="{ active: includeDetails }">
            <input
              type="checkbox"
              :checked="includeDetails"
              @change="toggleDetails(($event.target as HTMLInputElement).checked)"
            />
            <span>
              <b>五点详情</b>
              <small>补充 Amazon Listing 五点描述</small>
            </span>
          </label>
        </div>

        <label v-if="includeDetails" class="field detail-workers">
          <span>详情页并发：{{ workers }}</span>
          <input
            :value="workers"
            min="1"
            max="8"
            type="range"
            @input="emit('update:workers', Number(($event.target as HTMLInputElement).value))"
          />
        </label>
      </div>
    </div>

    <footer class="control-panel-footer">
      <p v-if="error" class="error-banner">{{ error }}</p>
      <button class="primary-action" type="button" :disabled="loading" @click="emit('run')">
        {{ loading ? '正在抓取…' : '开始抓取' }}
      </button>
    </footer>
  </section>
</template>
