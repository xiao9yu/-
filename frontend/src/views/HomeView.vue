<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <el-container class="shell">
    <el-aside width="232px" class="sidebar">
      <div class="brand">
        <div class="brand-mark"><el-icon :size="20"><School /></el-icon></div>
        <div class="brand-text">
          <div class="brand-name">教育智能体</div>
          <div class="brand-sub">AI × 教育 · EduAgent</div>
        </div>
      </div>

      <div class="menu-label">工作台</div>
      <el-menu :default-active="activeMenu" router class="side-menu">
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon><span>首页</span>
        </el-menu-item>
        <el-menu-item index="/prep">
          <el-icon><Notebook /></el-icon><span>智能备课</span>
        </el-menu-item>
        <el-menu-item index="/module/assistant">
          <el-icon><ChatDotRound /></el-icon><span>智能助教</span>
        </el-menu-item>
        <el-menu-item index="/module/learn">
          <el-icon><DataAnalysis /></el-icon><span>个性化学习</span>
          <el-tag size="small" class="soon-tag" effect="plain">规划</el-tag>
        </el-menu-item>
      </el-menu>

      <div class="side-foot">
        <div class="side-foot-line" />
        <div class="side-motto">因材施教 · 教学相长</div>
        <div class="side-version">实训工单 16 ~ 20 · v0.2</div>
      </div>
    </el-aside>

    <el-container class="body">
      <el-header class="topbar">
        <div class="topbar-left">
          <span class="topbar-title">{{ pageTitle }}</span>
        </div>
        <div class="topbar-right">
          <div class="user-chip" @click="onLogout" title="退出登录">
            <el-avatar :size="32" class="user-avatar">{{ avatarText }}</el-avatar>
            <div class="user-meta">
              <div class="user-name">{{ auth.user?.real_name || auth.user?.username }}</div>
              <div class="user-role">{{ roleLabel }}</div>
            </div>
            <el-icon class="logout-ico"><SwitchButton /></el-icon>
          </div>
        </div>
      </el-header>
      <el-main class="content"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound, DataAnalysis, HomeFilled, Notebook, School, SwitchButton,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员', teacher: '教师', student: '学生', counselor: '就业指导',
}
const roleLabel = computed(() => ROLE_LABELS[auth.user?.role || ''] || auth.user?.role || '用户')

const avatarText = computed(() =>
  (auth.user?.real_name || auth.user?.username || '?').slice(0, 1).toUpperCase())

const PAGE_TITLES: Record<string, string> = {
  '/': '首页',
  '/prep': '智能备课',
  '/module/assistant': '智能助教',
  '/module/learn': '个性化学习',
}
const pageTitle = computed(() => {
  if (route.path.startsWith('/prep/course')) return '智能备课 · 课程详情'
  if (route.path.startsWith('/prep/lesson')) return '智能备课 · 内容编辑'
  return PAGE_TITLES[route.path] || '教育智能体平台'
})

/** 侧边栏高亮：嵌套路径（/prep/course/3）归属最近的一级菜单项。 */
const activeMenu = computed(() => {
  if (route.path === '/') return '/'
  if (route.path.startsWith('/prep')) return '/prep'
  if (route.path.startsWith('/module')) return route.path.includes('assistant') ? '/module/assistant' : '/module/learn'
  return route.path
})

function onLogout() { auth.logout(); router.push('/login') }
</script>

<style scoped>
.shell { height: 100vh; }

/* ---------- 侧边栏 ---------- */
.sidebar {
  background: var(--ink);
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}
.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 20px 20px 18px;
}
.brand-mark {
  width: 38px; height: 38px;
  flex: none;
  border-radius: 11px;
  background: linear-gradient(135deg, #6a6ae0 0%, #4a4ac8 100%);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 12px rgba(91, 91, 214, 0.45);
}
.brand-name { color: #fff; font-size: 15px; font-weight: 700; letter-spacing: 0.5px; }
.brand-sub { color: rgba(255, 255, 255, 0.38); font-size: 11px; margin-top: 2px; letter-spacing: 0.3px; }

.menu-label {
  padding: 6px 22px 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.32);
  letter-spacing: 1px;
}
.side-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: 0 12px;
}
.side-menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.62);
  height: 42px;
  border-radius: 9px;
  margin-bottom: 3px;
  font-size: 13.5px;
  transition: all 0.15s ease;
}
.side-menu :deep(.el-menu-item .el-icon) { font-size: 16px; }
.side-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.9);
}
.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(91, 91, 214, 0.32), rgba(91, 91, 214, 0.14));
  color: #fff;
  font-weight: 600;
  box-shadow: inset 3px 0 0 var(--accent);
}
.soon-tag {
  margin-left: auto;
  --el-tag-bg-color: rgba(255, 255, 255, 0.08);
  --el-tag-border-color: rgba(255, 255, 255, 0.15);
  --el-tag-text-color: rgba(255, 255, 255, 0.45);
  font-size: 10px;
}

.side-foot {
  padding: 14px 22px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
}
.side-foot-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.07);
  margin-bottom: 12px;
}
.side-motto {
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.side-version { color: rgba(255, 255, 255, 0.3); }

/* ---------- 顶栏 ---------- */
.body { background: var(--bg); }
.topbar {
  background: var(--surface);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
}
.topbar-title { font-size: 15px; font-weight: 600; color: var(--text-1); }
.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px 6px 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.user-chip:hover { background: var(--bg); }
.user-chip:hover .logout-ico { opacity: 1; }
.user-avatar {
  background: linear-gradient(135deg, #6a6ae0, #4a4ac8);
  font-weight: 600;
  font-size: 14px;
}
.user-meta { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.25; }
.user-name { font-size: 13px; font-weight: 600; }
.user-role { font-size: 11px; color: var(--text-3); }
.logout-ico { color: var(--text-3); font-size: 14px; opacity: 0; transition: opacity 0.15s ease; }

/* ---------- 内容区 ---------- */
.content { padding: 24px 26px; overflow-y: auto; }
</style>
