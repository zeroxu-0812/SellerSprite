<script setup lang="ts">
import type { Failure } from '../types'

defineProps<{ failures: Failure[] }>()
</script>

<template>
  <section class="failure-panel">
    <div class="panel-title">
      <span>失败</span>
      <b>{{ failures.length }}</b>
    </div>
    <ul>
      <li v-for="failure in failures" :key="`${failure.asin}-${failure.stage}-${failure.message}`">
        <strong>{{ failure.asin }}</strong>
        <span>{{ failure.stage }}</span>
        <p>{{ failure.message }}</p>
      </li>
    </ul>
  </section>
</template>
