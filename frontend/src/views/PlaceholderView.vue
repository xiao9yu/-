<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-card>
    <h3>{{ title }}</h3>
    <el-empty :description="`${title} 建设中，后续工单将在此交付`" />
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
