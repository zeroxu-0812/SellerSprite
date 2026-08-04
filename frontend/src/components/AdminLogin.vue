<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  login: [username: string, password: string]
  home: []
}>()

const username = ref('')
const password = ref('')

function submit() {
  emit('login', username.value.trim(), password.value)
}
</script>

<template>
  <main class="admin-login-shell">
    <header class="admin-login-nav">
      <button class="brand-block brand-button" type="button" @click="$emit('home')">
        <img class="app-logo" src="/oceanwing-logo.jpg" alt="Oceanwing" />
        <div><strong>SellerSprite</strong><span>开发者工作台</span></div>
      </button>
      <button class="admin-login-home" type="button" @click="$emit('home')">返回首页</button>
    </header>

    <section class="admin-login-card" aria-labelledby="admin-login-title">
      <div class="admin-login-mark">SS</div>
      <span class="admin-login-eyebrow">ADMIN ACCESS</span>
      <h1 id="admin-login-title">进入开发者工作台</h1>
      <p>请输入管理员账号和密码，查看站点搜索统计与查询详情。</p>

      <form @submit.prevent="submit">
        <label>
          <span>管理员账号</span>
          <input v-model="username" autocomplete="username" placeholder="请输入管理员账号" required />
        </label>
        <label>
          <span>管理员密码</span>
          <input v-model="password" autocomplete="current-password" type="password" placeholder="请输入管理员密码" required />
        </label>
        <p v-if="error" class="admin-login-error" role="alert">{{ error }}</p>
        <button class="admin-login-submit" type="submit" :disabled="loading">
          {{ loading ? '正在验证…' : '验证并进入工作台' }}
        </button>
      </form>

      <div class="admin-login-note"><span>●</span> 仅管理员可以查看累计搜索和查询记录</div>
    </section>
  </main>
</template>
