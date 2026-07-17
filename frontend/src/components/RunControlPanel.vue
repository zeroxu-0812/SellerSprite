<script setup lang="ts">
import type { RunMode } from '../types'

defineProps<{
  rawInput: string
  mode: RunMode
  workers: number
  asinCount: number
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  'update:rawInput': [value: string]
  'update:mode': [value: RunMode]
  'update:workers': [value: number]
  run: []
}>()
</script>

<template>
  <aside class="control-drawer" aria-label="运行控制">
    <div class="drawer-tab">
      <span>INPUT</span>
      <b>{{ asinCount }}</b>
    </div>

    <div class="control-rail">
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
        <div class="section-label">Run mode</div>
        <div class="segmented">
          <button :class="{ active: mode === 'fast' }" type="button" @click="emit('update:mode', 'fast')">
            <b>快速</b><span>仅卖家精灵</span>
          </button>
          <button :class="{ active: mode === 'full' }" type="button" @click="emit('update:mode', 'full')">
            <b>完整</b><span>补详情页</span>
          </button>
        </div>
      </div>

      <div class="panel-section">
        <label class="field">
          <span>详情页并发：{{ workers }}</span>
          <input
            :value="workers"
            min="1"
            max="8"
            type="range"
            @input="emit('update:workers', Number(($event.target as HTMLInputElement).value))"
          />
        </label>
        <div class="run-summary">
          <span>已识别</span>
          <b>{{ asinCount }}</b>
          <span>个 ASIN</span>
        </div>
      </div>

      <button class="primary-action" type="button" :disabled="loading" @click="emit('run')">
        {{ loading ? '正在抓取…' : '开始抓取' }}
      </button>

      <p v-if="error" class="error-banner">{{ error }}</p>
    </div>
  </aside>
</template>
