<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-card class="soon-card" shadow="never">
    <div class="soon-icon">🚧</div>
    <h3 class="soon-title">{{ title }}</h3>
    <p class="soon-desc">模块建设中，后续工单将在此交付，敬请期待。</p>
    <el-button type="primary" plain @click="$router.push('/')">返回首页</el-button>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const names: Record<string, string> = {
  prep: '智能备课（工单17）',
  learn: '个性化学习（工单19）'
}
const route = useRoute()
const title = computed(() => names[String(route.params.name)] || '模块')
</script>

<style scoped>
.soon-card {
  text-align: center;
  padding: 70px 20px;
  border: 1px dashed var(--border-strong);
  background: var(--surface);
}
.soon-icon { font-size: 46px; }
.soon-title { margin: 18px 0 8px; font-size: 17px; font-weight: 700; }
.soon-desc { color: var(--text-3); font-size: 13px; margin: 0 0 22px; }
</style>
