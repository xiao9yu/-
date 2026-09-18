<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <div class="login">
    <!-- ============ 左侧品牌区：AI × 教育 ============ -->
    <div class="login-brand">
      <div class="brand-top">
        <div class="brand-mark"><el-icon :size="22"><School /></el-icon></div>
        <div class="brand-name-box">
          <span class="brand-name">教育智能体平台</span>
          <span class="brand-tag">AI × 教育</span>
        </div>
      </div>

      <div class="brand-hero">
        <h1>让 AI 走进<br />每一间教室</h1>
        <p>备课 · 助教 · 学习路径，一站式的教育智能体工作台，<br />让教师专注教学，让学生高效学习。</p>
      </div>

      <!-- 中心视觉：AI 课堂场景（纯 CSS 组合） -->
      <div class="scene">
        <div class="scene-dots" />
        <!-- 黑板 -->
        <div class="scene-board">
          <div class="board-head">第 3 章 · 机器学习基础</div>
          <div class="board-formula">∇J(θ) = − η · ∇θL(θ)</div>
          <div class="board-note">学习率 η：从 0.001 开始</div>
          <div class="board-note dim">过大会发散 · 过小收敛慢</div>
          <div class="board-chalk" />
        </div>
        <!-- 助教回答卡 -->
        <div class="scene-chat">
          <div class="chat-head">
            <span class="chat-ai"><el-icon :size="13"><MagicStick /></el-icon></span>
            <span class="chat-name">智能助教</span>
            <span class="chat-time">刚刚</span>
          </div>
          <div class="chat-text">学习率过大会导致训练发散，建议从 0.001 开始，配合学习率衰减……</div>
          <div class="chat-ref"><el-icon :size="12"><Link /></el-icon> [2] 人工智能导论.pdf · 第 3 页</div>
        </div>
        <!-- 漂浮小卡 -->
        <div class="scene-chip chip-1"><el-icon :size="13"><Tickets /></el-icon> 习题 · 已生成 12 题</div>
        <div class="scene-chip chip-2"><el-icon :size="13"><Trophy /></el-icon> 学生掌握度 86%</div>
        <div class="scene-badge badge-1"><el-icon :size="18"><Reading /></el-icon></div>
        <div class="scene-badge badge-2"><el-icon :size="16"><Notebook /></el-icon></div>
      </div>

      <!-- 特性列表 -->
      <ul class="brand-features">
        <li><el-icon><Document /></el-icon><span>AI 生成教案、课件大纲、习题与试卷，一键引用校本资源</span></li>
        <li><el-icon><ChatDotRound /></el-icon><span>私有知识库问答，回答逐句引用原文溯源</span></li>
        <li><el-icon><DataAnalysis /></el-icon><span>个性化学习路径，按掌握度推荐练习</span></li>
      </ul>

      <div class="brand-foot">
        <span>服务对象</span>
        <span class="dot">·</span>
        <span>教师</span><span class="dot">·</span>
        <span>学生</span><span class="dot">·</span>
        <span>管理员</span><span class="dot">·</span>
        <span>就业指导</span>
        <span class="foot-right">实训工单 16 ~ 20</span>
      </div>
    </div>

    <!-- ============ 右侧登录表单 ============ -->
    <div class="login-panel">
      <div class="login-form-wrap">
        <h2 class="login-title">欢迎登录</h2>
        <p class="login-sub">教师、学生与管理员统一入口</p>
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
import {
  ChatDotRound, DataAnalysis, Document, Link, Lock, MagicStick,
  Notebook, Reading, School, Tickets, Trophy, User,
} from '@element-plus/icons-vue'
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

/* ============ 品牌区 ============ */
.login-brand {
  flex: 0 0 55%;
  background:
    radial-gradient(900px 500px at -10% -20%, rgba(106, 106, 224, 0.28), transparent 60%),
    radial-gradient(700px 500px at 110% 120%, rgba(45, 140, 160, 0.2), transparent 55%),
    var(--ink);
  color: #fff;
  padding: 36px 52px 30px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.brand-top { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 42px; height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6a6ae0, #4a4ac8);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 18px rgba(91, 91, 214, 0.5);
}
.brand-name-box { display: flex; flex-direction: column; line-height: 1.3; }
.brand-name { font-size: 16px; font-weight: 700; letter-spacing: 0.5px; }
.brand-tag {
  font-size: 11px;
  color: #8b8bf0;
  letter-spacing: 1.5px;
  margin-top: 2px;
}

.brand-hero { margin-top: 40px; position: relative; z-index: 2; }
.brand-hero h1 {
  font-size: 32px;
  line-height: 1.45;
  font-weight: 700;
  letter-spacing: 1px;
  margin: 0;
}
.brand-hero p {
  margin-top: 14px;
  font-size: 13.5px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.9;
}

/* ---------- 中心视觉：AI 课堂场景 ---------- */
.scene {
  position: relative;
  height: 250px;
  margin-top: 26px;
  z-index: 1;
}
.scene-dots {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(rgba(255, 255, 255, 0.09) 1.2px, transparent 1.2px);
  background-size: 22px 22px;
  mask-image: radial-gradient(ellipse 70% 80% at 50% 50%, #000 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse 70% 80% at 50% 50%, #000 30%, transparent 75%);
}

/* 黑板 */
.scene-board {
  position: absolute;
  left: 6%;
  top: 6px;
  width: 52%;
  height: 172px;
  background: linear-gradient(160deg, #2e4f45 0%, #24403a 100%);
  border: 6px solid #6b4f32;
  border-radius: 8px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  padding: 16px 18px;
  animation: float 7s ease-in-out infinite;
}
.board-head { font-size: 12.5px; color: #ffe9b8; letter-spacing: 1px; }
.board-formula {
  font-family: Consolas, "Courier New", monospace;
  font-size: 17px;
  color: #f7f3e8;
  margin-top: 16px;
  letter-spacing: 0.5px;
}
.board-note { font-size: 12.5px; color: #d8e4dc; margin-top: 12px; }
.board-note.dim { color: #9db8ac; margin-top: 5px; }
.board-chalk {
  position: absolute;
  right: 14px; bottom: 12px;
  width: 34px; height: 3px;
  border-radius: 2px;
  background: #fff;
  opacity: 0.85;
  transform: rotate(-8deg);
  box-shadow: 12px -6px 0 -0.5px #fff, -4px -10px 0 -0.5px #ffe9b8;
}

/* 助教回答卡 */
.scene-chat {
  position: absolute;
  right: 2%;
  top: 52px;
  width: 44%;
  background: rgba(255, 255, 255, 0.98);
  border-radius: 12px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.35);
  padding: 12px 14px;
  color: var(--text-1);
  animation: float 7s ease-in-out 1.2s infinite;
}
.chat-head { display: flex; align-items: center; gap: 7px; }
.chat-ai {
  width: 20px; height: 20px;
  border-radius: 6px;
  background: linear-gradient(135deg, #6a6ae0, #4a4ac8);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
}
.chat-name { font-size: 12px; font-weight: 700; }
.chat-time { margin-left: auto; font-size: 10.5px; color: var(--text-3); }
.chat-text { font-size: 12px; color: var(--text-2); line-height: 1.75; margin-top: 8px; }
.chat-ref {
  display: flex; align-items: center; gap: 5px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--accent);
  background: #f0f0fb;
  border-radius: 6px;
  padding: 5px 8px;
}

/* 漂浮小卡与徽标 */
.scene-chip {
  position: absolute;
  display: flex; align-items: center; gap: 6px;
  font-size: 11.5px;
  color: var(--text-1);
  background: rgba(255, 255, 255, 0.97);
  border-radius: 20px;
  padding: 6px 12px;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3);
  white-space: nowrap;
}
.chip-1 { left: 0; bottom: 10px; color: #16a34a; animation: float 6s ease-in-out 0.5s infinite; }
.chip-2 { right: 8%; bottom: -2px; color: #d97706; animation: float 6s ease-in-out 1.8s infinite; }
.scene-badge {
  position: absolute;
  width: 38px; height: 38px;
  border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.35);
}
.badge-1 {
  left: 58%; top: 0;
  background: linear-gradient(135deg, #f59e0b, #d97706);
  animation: float 6.5s ease-in-out 0.8s infinite;
}
.badge-2 {
  left: 44%; bottom: 34px;
  background: linear-gradient(135deg, #10b981, #0d9488);
  animation: float 6.5s ease-in-out 2.2s infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

/* 特性列表 */
.brand-features {
  list-style: none;
  padding: 0;
  margin: 20px 0 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
  z-index: 2;
}
.brand-features li {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.6;
}
.brand-features .el-icon {
  color: #8b8bf0;
  font-size: 16px;
  margin-top: 2px;
  flex: none;
}

.brand-foot {
  margin-top: auto;
  padding-top: 18px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.brand-foot .dot { opacity: 0.5; }
.foot-right { margin-left: auto; letter-spacing: 1px; }

/* ============ 表单区 ============ */
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
