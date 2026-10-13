<script setup lang="ts">
import { marketplaces } from '../utils/marketplaces'

const logoUrl = `${import.meta.env.BASE_URL}oceanwing-logo.jpg`

defineEmits<{
  analyze: []
  dashboard: []
}>()
</script>

<template>
  <main class="landing-page">
    <header class="landing-nav">
      <div class="landing-brand">
        <img :src="logoUrl" alt="Oceanwing" />
        <strong>SellerSprite</strong>
        <span>竞手分析</span>
      </div>
      <button class="landing-workspace-button" type="button" @click="$emit('dashboard')">进入工作台</button>
    </header>

    <section class="landing-hero">
      <div class="landing-copy">
        <h1>SellerSprite 竞手分析</h1>
        <p>批量输入 ASIN，快速获取多站点竞品数据、市场指标与 Listing 洞察，让选品判断建立在更完整的数据上。</p>
        <button class="landing-primary" type="button" @click="$emit('analyze')">开始分析</button>
        <div class="landing-trust">
          <span>支持多个国家站点</span><i />
          <span>摘要与五点信息按需抓取</span><i />
          <span>一键导出 HTML 报告</span>
        </div>
      </div>

      <div class="landing-product-preview" aria-hidden="true">
        <div class="preview-header">
          <div><img :src="logoUrl" alt="" /><b>竞手分析工作台</b></div>
          <span>● 就绪 · 3 ASIN</span>
        </div>
        <div class="preview-body">
          <aside>
            <h2>分析设置</h2>
            <small>ASIN 列表</small>
            <div class="preview-asins">B0BHV5TTL6<br />B0FQFPZW9G<br />B0FQFZDF9Z</div>
            <small>目标站点</small>
            <div class="preview-markets">
              <span v-for="item in marketplaces" :key="item.code" :class="{ active: item.code === 'jp' }">
                {{ item.flag }} {{ item.label }}
              </span>
            </div>
          </aside>
          <section>
            <div class="preview-title"><h2>核心竞手矩阵</h2><span>导出 HTML</span></div>
            <div class="preview-metrics">
              <article><small>已分析商品</small><b>24</b></article>
              <article><small>均价</small><b>¥3,260</b></article>
              <article><small>月销量</small><b>8,492</b></article>
              <article><small>总销售额</small><b>¥18.4M</b></article>
            </div>
            <div class="preview-table">
              <div class="preview-row head"><span>商品 / ASIN</span><span>价格</span><span>月销量</span><span>BSR</span></div>
              <div class="preview-row"><span>大型刀头毛球修剪器</span><b>¥3,580</b><span>2,418</span><b>#1,284</b></div>
              <div class="preview-row"><span>衣物护理便携去球器</span><b>¥2,980</b><span>1,906</span><b>#2,106</b></div>
              <div class="preview-row"><span>家用高效毛衣清理器</span><b>¥3,220</b><span>1,472</span><b>#3,040</b></div>
            </div>
          </section>
        </div>
      </div>
    </section>

    <section class="landing-coverage">
      <div><span>多站点覆盖</span><h2>一套工作流，覆盖主流 Amazon 站点</h2></div>
      <ul>
        <li v-for="item in marketplaces" :key="item.code"><span>{{ item.flag }}</span><b>{{ item.label }}</b></li>
      </ul>
    </section>
  </main>
</template>
