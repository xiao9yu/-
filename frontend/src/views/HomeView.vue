<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-container style="height: 100vh">
    <el-aside width="220px">
      <el-menu :default-active="$route.path" router background-color="#001529" text-color="#ccc" active-text-color="#fff">
        <el-menu-item index="/">首页</el-menu-item>
        <el-menu-item index="/module/prep">智能备课</el-menu-item>
        <el-menu-item index="/module/assistant">智能助教</el-menu-item>
        <el-menu-item index="/module/learn">个性化学习</el-menu-item>
        <el-menu-item index="/module/interview">面试AI复盘</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="display: flex; align-items: center; justify-content: space-between">
        <span>欢迎，{{ auth.user?.real_name || auth.user?.username }}</span>
        <el-button @click="onLogout">退出登录</el-button>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
function onLogout() { auth.logout(); router.push('/login') }
</script>
