<script setup lang="ts">
import { computed } from 'vue'
import type { MarketplaceCode } from '../types'

const props = defineProps<{
  rawInput: string
  marketplace: MarketplaceCode
  includeSummary: boolean
  includeDetails: boolean
  workers: number
  asinCount: number
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'update:rawInput': [value: string]
  'update:marketplace': [value: MarketplaceCode]
  'update:includeSummary': [value: boolean]
  'update:includeDetails': [value: boolean]
  'update:workers': [value: number]
  run: []
}>()

const marketplaces: Array<{
  code: MarketplaceCode
  label: string
  domain: string
}> = [
  { code: 'com', label: '美国', domain: 'amazon.com' },
  { code: 'de', label: '德国', domain: 'amazon.de' },
  { code: 'uk', label: '英国', domain: 'amazon.co.uk' },
  { code: 'jp', label: '日本', domain: 'amazon.co.jp' },
  { code: 'fr', label: '法国', domain: 'amazon.fr' },
  { code: 'es', label: '西班牙', domain: 'amazon.es' },
  { code: 'it', label: '意大利', domain: 'amazon.it' },
]

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
</script>

<template>
  <section class="control-panel" aria-label="运行控制">
    <header class="control-panel-header">
      <div>
        <div class="eyebrow">Run control</div>
        <h2>分析设置</h2>
        <p>输入 ASIN，选择目标站点与抓取模式后开始分析。</p>
      </div>
      <div class="run-summary">
        <span>已识别</span>
        <b>{{ asinCount }}</b>
        <span>个 ASIN</span>
      </div>
    </header>

    <div class="control-panel-grid">
      <div class="panel-section">
        <div class="section-label">Input</div>
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
        <div class="section-label">Marketplace</div>
        <div class="marketplace-grid">
          <button
            v-for="item in marketplaces"
            :key="item.code"
            type="button"
            class="marketplace-button"
            :class="{ active: marketplace === item.code }"
            :aria-pressed="marketplace === item.code"
            @click="emit('update:marketplace', item.code)"
          >
            <b>{{ item.label }}</b>
            <span>{{ item.domain }}</span>
          </button>
        </div>
      </div>

      <div class="panel-section run-settings">
        <div class="mode-heading">
          <div class="section-label">Data options</div>
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
