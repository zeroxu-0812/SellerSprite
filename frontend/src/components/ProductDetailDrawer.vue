<script setup lang="ts">
import type { ProductRow } from '../types'
import { fmt, parseList, safe } from '../utils/formatters'

defineProps<{
  product: ProductRow | null
}>()

const emit = defineEmits<{ close: [] }>()

const fieldGroups = [
  {
    title: '身份',
    fields: ['asin', 'parent', 'brand', 'seller_name', 'seller_dto__nation_name'],
  },
  {
    title: '价格与口碑',
    fields: ['price', 'list_price', 'discount_off_list_pct', 'rating', 'reviews'],
  },
  {
    title: '销量与排名',
    fields: ['units', 'month_units', 'amount', 'sub_total_amount', 'bsr_list__main_rank', 'bsr_list__sub_rank'],
  },
]

function entries(product: ProductRow) {
  return Object.entries(product)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .sort(([a], [b]) => a.localeCompare(b))
}
</script>

<template>
  <div v-if="product" class="drawer-backdrop" @click.self="emit('close')">
    <aside class="detail-drawer">
      <header>
        <div>
          <span>Product detail</span>
          <h2>{{ product.asin || '未知 ASIN' }}</h2>
        </div>
        <button type="button" @click="emit('close')">关闭</button>
      </header>

      <div class="drawer-main">
        <img v-if="product.image_large || product.image" :src="String(product.image_large || product.image)" alt="" />
        <div>
          <h3>{{ product.title || '(无标题)' }}</h3>
          <a v-if="product.url" :href="String(product.url)" target="_blank" rel="noreferrer">打开 Amazon 页面</a>
        </div>
      </div>

      <section class="drawer-kpis">
        <article>
          <span>价格</span>
          <strong v-html="fmt(product.price)" />
        </article>
        <article>
          <span>父体销量</span>
          <strong v-html="fmt(product.units)" />
        </article>
        <article>
          <span>评分</span>
          <strong v-html="fmt(product.rating)" />
        </article>
        <article>
          <span>主 BSR</span>
          <strong v-html="fmt(product.bsr_list__main_rank)" />
        </article>
      </section>

      <section v-if="parseList(product.about).length" class="drawer-section">
        <h4>About this item</h4>
        <ul class="about-list">
          <li v-for="item in parseList(product.about)" :key="item">{{ item }}</li>
        </ul>
      </section>

      <section class="drawer-section">
        <h4>关键字段</h4>
        <div class="field-groups">
          <dl v-for="group in fieldGroups" :key="group.title" class="field-grid">
            <dt class="group-title">{{ group.title }}</dt>
            <dd class="group-title"></dd>
            <template v-for="field in group.fields" :key="field">
              <dt>{{ field }}</dt>
              <dd v-html="safe(product[field] ?? '—')" />
            </template>
          </dl>
        </div>
      </section>

      <section class="drawer-section">
        <h4>全部非空字段</h4>
        <dl class="field-grid all-fields">
          <template v-for="[field, value] in entries(product)" :key="field">
            <dt>{{ field }}</dt>
            <dd v-html="safe(typeof value === 'object' ? JSON.stringify(value) : value)" />
          </template>
        </dl>
      </section>
    </aside>
  </div>
</template>
