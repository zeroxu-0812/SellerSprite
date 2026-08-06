<script setup lang="ts">
import type { Failure } from '../types'
import { marketplaceByCode } from '../utils/marketplaces'

defineProps<{ failures: Failure[] }>()

function failureLabel(failure: Failure) {
  const info = failure.marketplace
    ? marketplaceByCode[String(failure.marketplace) as keyof typeof marketplaceByCode]
    : null
  return info ? `${info.flag} ${info.label}站 · ${failure.stage}` : failure.stage
}
</script>

<template>
  <section class="failure-panel">
    <div class="panel-title">
      <span>失败</span>
      <b>{{ failures.length }}</b>
    </div>
    <ul>
      <li v-for="failure in failures" :key="`${failure.marketplace || 'unknown'}-${failure.asin}-${failure.stage}-${failure.message}`">
        <strong>{{ failure.asin }}</strong>
        <span>{{ failureLabel(failure) }}</span>
        <p>{{ failure.message }}</p>
      </li>
    </ul>
  </section>
</template>
