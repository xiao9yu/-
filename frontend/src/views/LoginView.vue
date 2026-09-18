<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <div class="login">
    <!-- 左侧品牌区 -->
    <div class="login-brand">
      <div class="brand-top">
        <div class="brand-mark"><el-icon :size="22"><School /></el-icon></div>
        <span class="brand-name">教育智能体平台</span>
      </div>
      <div class="brand-hero">
        <h1>让 AI 成为每位老师的<br />教学搭档</h1>
        <p>智能备课 · 知识库助教 · 个性化学习，一站式教学智能体工作台</p>
      </div>
      <ul class="brand-features">
        <li><el-icon><Document /></el-icon><span>AI 生成教案、课件大纲、习题与试卷，支持引用校本资源</span></li>
        <li><el-icon><ChatDotRound /></el-icon><span>私有知识库问答，答案逐句引用溯源</span></li>
        <li><el-icon><DataAnalysis /></el-icon><span>面向学生的个性化学习路径推荐</span></li>
      </ul>
      <div class="brand-foot">实训项目 · 工单 16~20</div>
    </div>

    <!-- 右侧登录表单 -->
    <div class="login-panel">
      <div class="login-form-wrap">
        <h2 class="login-title">欢迎回来</h2>
        <p class="login-sub">登录以继续使用教育智能体平台</p>
        <el-form :model="form" size="large" @keyup.enter="onLogin">
          <el-form-item>
            <el-input v-model="form.username" placeholder="用户名">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input v-model="form.password" type="password" placeholder="密码" show-password>
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button class="login-btn" type="primary" size="large" :loading="loading" @click="onLogin">
            登 录
          </el-button>
        </el-form>

        <el-divider class="login-divider"><span>演示账号</span></el-divider>
        <div class="demo-accounts">
          <div class="demo-row" v-for="d in demos" :key="d.role">
            <el-tag size="small" effect="plain" class="demo-role">{{ d.role }}</el-tag>
            <span class="demo-cred">{{ d.cred }}</span>
            <el-button text size="small" type="primary" @click="fill(d)">填入</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, DataAnalysis, Document, Lock, School, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const form = reactive({ username: '', password: '' })
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

const demos = [
  { role: '管理员', cred: 'admin / admin123', u: 'admin', p: 'admin123' },
  { role: '教师', cred: 'teacher / teacher123', u: 'teacher', p: 'teacher123' },
  { role: '学生', cred: 'student / student123', u: 'student', p: 'student123' },
  { role: '就业指导', cred: 'counselor / counselor123', u: 'counselor', p: 'counselor123' },
]

function fill(d: { u: string; p: string }) {
  form.username = d.u
  form.password = d.p
}

async function onLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } catch {
    // 错误提示由 http 拦截器统一弹出，这里只兜住未处理 rejection（台账 A-9）
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login {
  height: 100vh;
  display: flex;
  background: var(--surface);
}

/* ---------- 品牌区 ---------- */
.login-brand {
  flex: 0 0 52%;
  background:
    radial-gradient(1000px 500px at -10% -20%, rgba(106, 106, 224, 0.35), transparent 60%),
    radial-gradient(800px 500px at 110% 120%, rgba(76, 136, 220, 0.25), transparent 55%),
    var(--ink);
  color: #fff;
  padding: 40px 56px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.brand-top { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6a6ae0, #4a4ac8);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 18px rgba(91, 91, 214, 0.5);
}
.brand-name { font-size: 17px; font-weight: 700; letter-spacing: 0.5px; }

.brand-hero { margin-top: 72px; }
.brand-hero h1 {
  font-size: 34px;
  line-height: 1.4;
  font-weight: 700;
  letter-spacing: 0.5px;
  margin: 0;
}
.brand-hero p {
  margin-top: 18px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.8;
  max-width: 400px;
}

.brand-features { list-style: none; padding: 0; margin: 48px 0 0; }
.brand-features li {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 18px;
  font-size: 13.5px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.7;
}
.brand-features .el-icon {
  color: #8b8bf0;
  font-size: 17px;
  margin-top: 3px;
  flex: none;
}

.brand-foot {
  margin-top: auto;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 0.5px;
}

/* ---------- 表单区 ---------- */
.login-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface);
}
.login-form-wrap { width: 360px; }
.login-title { font-size: 24px; font-weight: 700; margin: 0; }
.login-sub { margin: 10px 0 30px; font-size: 13px; color: var(--text-3); }

.login-btn { width: 100%; letter-spacing: 6px; font-weight: 600; margin-top: 4px; }

.login-divider { margin: 26px 0 14px; }
.login-divider :deep(.el-divider__text) { color: var(--text-3); font-size: 12px; }

.demo-accounts {
  border: 1px dashed var(--border-strong);
  border-radius: 12px;
  padding: 6px 14px;
  background: var(--bg);
}
.demo-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12.5px;
}
.demo-row:last-child { border-bottom: none; }
.demo-role { width: 64px; flex: none; }
.demo-cred { flex: 1; color: var(--text-2); font-family: Consolas, Monaco, monospace; font-size: 12px; }

@media (max-width: 900px) {
  .login-brand { display: none; }
}
</style>
