<script setup lang="ts">
import { computed } from 'vue'
import type { CompetitorProfile, BenchmarkMetric } from '../utils/competitorAnalysis'
import { delta, numeric, pct, text } from '../utils/competitorAnalysis'
import { fmt, money, parseList, safe } from '../utils/formatters'

const props = defineProps<{
  profile: CompetitorProfile | null
  baseline: CompetitorProfile | null
  metric: BenchmarkMetric
  marketplace: string
}>()

const metricFields: Record<BenchmarkMetric, { label: string; key: string }> = {
  sales: { label: '销量差', key: 'units' },
  price: { label: '价格差', key: 'price' },
  rating: { label: '评分差', key: 'rating' },
  bsr: { label: 'BSR差', key: 'bsr_list__main_rank' },
  reviews: { label: '评论差', key: 'reviews' },
}

const summaryItems = computed(() => {
  const product = props.profile?.product
  return [
    { label: '产品定位', value: text(product?.product_identity) },
    { label: '目标用户', value: text(product?.target_user) },
    { label: '主要场景', value: text(product?.primary_scene) },
    { label: '整体总结', value: text(product?.overall_summary) },
  ]
})

const hasSummary = computed(() => summaryItems.value.some((item) => item.value !== '-'))

function compareText() {
  if (!props.profile || !props.baseline) return '-'
  const field = metricFields[props.metric]
  return pct(delta(props.profile.product[field.key], props.baseline.product[field.key]))
}
</script>

<template>
  <aside class="competitor-profile">
    <div v-if="!profile" class="profile-empty">
      <span>Competitor profile</span>
      <p>点击表格中的竞手查看画像。</p>
    </div>

    <template v-else>
      <header class="profile-head">
        <img v-if="profile.product.image_large || profile.product.image" :src="String(profile.product.image_large || profile.product.image)" alt="" />
        <div>
          <span>{{ profile.isNew ? '新品 · 上架 365 天内' : '竞手画像' }}</span>
          <h2>{{ profile.product.asin }}</h2>
          <p>{{ profile.product.brand || profile.product.seller_name || '未知品牌 / 卖家' }}</p>
        </div>
      </header>

      <section class="profile-title">
        <h3>{{ profile.product.title || '(无标题)' }}</h3>
        <a v-if="profile.product.url" :href="String(profile.product.url)" target="_blank" rel="noreferrer">打开 Amazon 页面</a>
      </section>

      <section v-if="hasSummary" class="profile-summary">
        <div class="profile-section-heading">
          <h4>商品信息摘要</h4>
          <span>Listing 速览</span>
        </div>
        <dl class="summary-grid">
          <div v-for="item in summaryItems" :key="item.label" class="summary-item">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="profile-scoreboard">
        <article>
          <span>销量</span>
          <strong v-html="fmt(profile.product.units)" />
        </article>
        <article>
          <span>销售额</span>
          <strong>{{ money(profile.product.amount, marketplace) }}</strong>
        </article>
        <article>
          <span>价格</span>
          <strong>{{ money(profile.product.price, marketplace) }}</strong>
        </article>
        <article>
          <span>主 BSR</span>
          <strong v-html="fmt(profile.product.bsr_list__main_rank || profile.product.bsr)" />
        </article>
      </section>

      <section class="profile-compare">
        <div>
          <span>{{ metricFields[metric].label }}</span>
          <strong>{{ compareText() }}</strong>
        </div>
        <p v-if="baseline">对比基准：{{ baseline.product.asin }}</p>
        <p v-else>未选择基准竞手</p>
      </section>

      <section v-if="profile.signals.length" class="profile-section">
        <h4>竞争信号</h4>
        <div class="signal-list">
          <span v-for="signal in profile.signals" :key="signal">{{ signal }}</span>
        </div>
      </section>

      <section class="profile-section">
        <h4>竞手资产</h4>
        <dl class="profile-facts">
          <dt>评分 / 评论</dt><dd>{{ text(profile.product.rating) }} / {{ text(profile.product.reviews) }}</dd>
          <dt>变体数</dt><dd>{{ text(profile.product.variations) }}</dd>
          <dt>上架天数</dt><dd>{{ text(profile.product.available_days) }}</dd>
          <dt>卖家国家</dt><dd>{{ text(profile.product.seller_dto__nation_name) }}</dd>
          <dt>子体月销</dt><dd>{{ text(profile.product.month_units) }}</dd>
        </dl>
      </section>

      <section v-if="parseList(profile.product.about).length" class="profile-section">
        <h4>About this item</h4>
        <ul class="about-list">
          <li v-for="item in parseList(profile.product.about).slice(0, 5)" :key="item" v-html="safe(item)" />
        </ul>
      </section>
    </template>
  </aside>
</template>
