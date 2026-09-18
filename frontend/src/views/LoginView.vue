<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <div class="login">
    <!-- ============ 统一面板：品牌 + 登录一体 ============ -->
    <div class="login-panel">
      <!-- 左：品牌与产品内容 -->
      <div class="panel-brand">
        <div class="brand-top">
          <div class="brand-mark"><el-icon :size="20"><School /></el-icon></div>
          <div class="brand-name-box">
            <span class="brand-name">教育智能体平台</span>
            <span class="brand-tag">EDUCATION AI PLATFORM</span>
          </div>
        </div>

        <div class="brand-eyebrow">为教学减负 · 为学习增效</div>
        <h1 class="hero-h1">让每一位师生，<br />都拥有专属的智能助手</h1>
        <p class="hero-p">备课 · 答疑 · 学习路径，一站式教育智能体平台，<br />让教师专注教学，让学生高效成长。</p>

        <!-- 产品内容展示 -->
        <div class="showcase">
          <!-- 教案卡 -->
          <div class="mock-card doc-card">
            <div class="doc-head">
              <span class="doc-tag">教案</span>
              <span class="doc-title">第3章 · 机器学习基础</span>
            </div>
            <div class="doc-line w90" />
            <div class="doc-line w70" />
            <div class="doc-line w82" />
            <div class="doc-list">
              <div class="doc-item"><i />掌握梯度下降原理</div>
              <div class="doc-item"><i />理解学习率的作用</div>
            </div>
            <div class="doc-ref"><el-icon :size="12"><Link /></el-icon>引用 [2] 人工智能导论.pdf · 第 3 页</div>
          </div>

          <!-- 助教回答卡 -->
          <div class="mock-card chat-card">
            <div class="chat-head">
              <span class="chat-ai"><el-icon :size="13"><MagicStick /></el-icon></span>
              <span class="chat-name">智能助教</span>
            </div>
            <div class="chat-text">学习率过大会导致训练发散，建议从 0.001 开始，配合学习率衰减逐步调整。</div>
            <div class="chat-ref"><el-icon :size="12"><Link /></el-icon> [2] 人工智能导论.pdf · 第 3 页　·　[5] 实验指导书.docx · 第 12 页</div>
          </div>

          <!-- 数据条 -->
          <div class="mock-card stat-card">
            <div class="stat-item">
              <div class="stat-num">12</div>
              <div class="stat-label">课程</div>
            </div>
            <div class="stat-sep" />
            <div class="stat-item">
              <div class="stat-num">48</div>
              <div class="stat-label">校本资源</div>
            </div>
            <div class="stat-sep" />
            <div class="stat-item">
              <div class="stat-num">96%</div>
              <div class="stat-label">回答引用率</div>
            </div>
          </div>
        </div>

        <!-- 能力列表 -->
        <div class="features">
          <div class="feature">
            <span class="feature-ico ico-indigo"><el-icon :size="15"><Document /></el-icon></span>
            <div class="feature-meta">
              <div class="feature-name">智能备课</div>
              <div class="feature-desc">AI 生成教案、课件大纲、习题与试卷，一键引用校本资源</div>
            </div>
          </div>
          <div class="feature">
            <span class="feature-ico ico-teal"><el-icon :size="15"><ChatDotRound /></el-icon></span>
            <div class="feature-meta">
              <div class="feature-name">智能助教</div>
              <div class="feature-desc">私有知识库问答，回答逐句引用原文，可溯源可复核</div>
            </div>
          </div>
          <div class="feature">
            <span class="feature-ico ico-amber"><el-icon :size="15"><DataAnalysis /></el-icon></span>
            <div class="feature-meta">
              <div class="feature-name">个性化学习</div>
              <div class="feature-desc">基于知识图谱与练习画像，推荐专属学习路径</div>
            </div>
          </div>
        </div>

        <div class="brand-foot">
          <span>服务对象：教师 · 学生 · 管理员 · 就业指导</span>
          <span class="foot-tag">实训工单 16 ~ 20</span>
        </div>
      </div>

      <!-- 右：登录表单 -->
      <div class="panel-form">
        <div class="form-wrap">
          <h2 class="login-title">欢迎回来</h2>
          <p class="login-sub">登录教育智能体平台</p>
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
            <el-button class="login-btn" size="large" :loading="loading" @click="onLogin">
              登 录
            </el-button>
          </el-form>

          <el-divider class="login-divider"><span>演示账号</span></el-divider>
          <div class="demo-accounts">
            <div class="demo-row" v-for="d in demos" :key="d.role">
              <span class="demo-role">{{ d.role }}</span>
              <span class="demo-cred">{{ d.cred }}</span>
              <el-button text size="small" type="primary" @click="fill(d)">填入</el-button>
            </div>
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
  ChatDotRound, DataAnalysis, Document, Link, Lock, MagicStick, School, User,
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
  min-height: 100vh;
  background:
    radial-gradient(760px 420px at 6% 0%, rgba(91, 91, 214, 0.06), transparent 60%),
    radial-gradient(600px 380px at 96% 100%, rgba(76, 136, 220, 0.05), transparent 60%),
    #f5f6f9;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 36px;
}

/* ---------- 统一面板 ---------- */
.login-panel {
  width: min(1140px, 100%);
  display: flex;
  background: #fff;
  border: 1px solid #e9eaf0;
  border-radius: 24px;
  box-shadow: 0 24px 64px rgba(23, 25, 36, 0.08);
  overflow: hidden;
}

/* 左半：极淡的暖调渐变，与右半同面板、无硬边界 */
.panel-brand {
  flex: 1.15;
  padding: 44px 52px 38px;
  background: linear-gradient(150deg, #fbfbfe 0%, #f6f7fb 70%, #f4f6fa 100%);
}

.brand-top { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 42px; height: 42px;
  border-radius: 12px;
  background: var(--ink);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 16px rgba(15, 20, 32, 0.25);
}
.brand-name-box { display: flex; flex-direction: column; line-height: 1.3; }
.brand-name { font-size: 16px; font-weight: 700; color: var(--text-1); letter-spacing: 0.5px; }
.brand-tag {
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 1.8px;
  margin-top: 2px;
}

.brand-eyebrow {
  margin-top: 34px;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 2px;
}
.hero-h1 {
  margin: 12px 0 0;
  font-size: 36px;
  line-height: 1.4;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: 1px;
}
.hero-p {
  margin: 14px 0 0;
  font-size: 13.5px;
  color: var(--text-2);
  line-height: 1.9;
}

/* ---------- 产品内容展示 ---------- */
.showcase {
  position: relative;
  height: 252px;
  margin-top: 28px;
}
.mock-card {
  position: absolute;
  background: #fff;
  border: 1px solid #e9eaf0;
  border-radius: 14px;
  box-shadow: 0 10px 28px rgba(23, 25, 36, 0.07);
  animation: drift 8s ease-in-out infinite;
}
@keyframes drift {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

/* 教案卡 */
.doc-card { left: 0; top: 4px; width: 48%; padding: 16px 18px; }
.doc-head { display: flex; align-items: center; gap: 9px; }
.doc-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: #eef0fb;
  border-radius: 6px;
  padding: 3px 9px;
  letter-spacing: 1px;
}
.doc-title { font-size: 13.5px; font-weight: 700; color: var(--text-1); }
.doc-line {
  height: 7px;
  border-radius: 4px;
  background: #eef0f6;
  margin-top: 12px;
}
.w90 { width: 90%; }
.w70 { width: 70%; }
.w82 { width: 82%; }
.doc-list { margin-top: 13px; }
.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.9;
}
.doc-item i {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--accent);
  flex: none;
}
.doc-ref {
  display: inline-flex; align-items: center; gap: 5px;
  margin-top: 12px;
  font-size: 11px;
  color: var(--accent);
  background: #f5f6fb;
  border-radius: 6px;
  padding: 4px 8px;
}

/* 助教回答卡 */
.chat-card {
  right: 0; top: 36px;
  width: 46%;
  padding: 14px 16px;
  animation-delay: 1.6s;
}
.chat-head { display: flex; align-items: center; gap: 8px; }
.chat-ai {
  width: 22px; height: 22px;
  border-radius: 7px;
  background: var(--ink);
  color: #fff;
  display: inline-flex; align-items: center; justify-content: center;
}
.chat-name { font-size: 12.5px; font-weight: 700; color: var(--text-1); }
.chat-text { font-size: 12.5px; color: var(--text-2); line-height: 1.8; margin-top: 9px; }
.chat-ref {
  display: flex; align-items: center; gap: 5px;
  margin-top: 10px;
  font-size: 10.5px;
  color: var(--accent);
  background: #f5f6fb;
  border-radius: 6px;
  padding: 4px 8px;
}

/* 数据条 */
.stat-card {
  left: 10%; bottom: 0;
  display: flex;
  align-items: center;
  padding: 14px 26px;
  animation-delay: 3.2s;
}
.stat-item { text-align: center; min-width: 72px; }
.stat-num { font-size: 19px; font-weight: 800; color: var(--ink); font-family: Consolas, Monaco, monospace; }
.stat-label { font-size: 11px; color: var(--text-3); margin-top: 3px; }
.stat-sep { width: 1px; height: 28px; background: #eceef4; margin: 0 14px; }

/* ---------- 能力列表 ---------- */
.features { margin-top: 30px; display: flex; flex-direction: column; gap: 13px; }
.feature { display: flex; align-items: flex-start; gap: 12px; }
.feature-ico {
  width: 30px; height: 30px; flex: none;
  border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
}
.ico-indigo { background: #eef0fb; color: #5b5bd6; }
.ico-teal { background: #e7f3f1; color: #0d9488; }
.ico-amber { background: #fdf3e7; color: #d97706; }
.feature-name { font-size: 13.5px; font-weight: 700; color: var(--text-1); }
.feature-desc { font-size: 12px; color: var(--text-3); margin-top: 3px; line-height: 1.6; }

.brand-foot {
  margin-top: 26px;
  padding-top: 18px;
  border-top: 1px solid #eceef4;
  font-size: 12px;
  color: var(--text-3);
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.foot-tag {
  background: #fff;
  border: 1px solid #e5e8f0;
  color: var(--text-3);
  border-radius: 20px;
  padding: 3px 10px;
  font-size: 11px;
}

/* ---------- 右半：登录表单 ---------- */
.panel-form {
  flex: 0.85;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 44px 48px 36px;
}
.form-wrap { width: 100%; max-width: 330px; }
.login-title { margin: 0; font-size: 22px; font-weight: 700; color: var(--text-1); }
.login-sub { margin: 8px 0 26px; font-size: 13px; color: var(--text-3); }

.panel-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 3px 14px;
  background: #f8f9fc;
  box-shadow: 0 0 0 1px #e5e8f0 inset;
}
.panel-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1.5px var(--accent) inset; }

.login-btn {
  width: 100%;
  height: 46px;
  border: none;
  border-radius: 10px;
  background: var(--ink);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 8px;
  margin-top: 4px;
  box-shadow: 0 10px 22px rgba(15, 20, 32, 0.22);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 28px rgba(15, 20, 32, 0.28);
  background: var(--ink-2);
}

.login-divider { margin: 24px 0 14px; }
.login-divider :deep(.el-divider__text) { color: var(--text-3); font-size: 12px; }

.demo-accounts { display: flex; flex-direction: column; gap: 6px; }
.demo-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 12px;
  background: #f8f9fc;
  border: 1px solid #eef0f6;
  border-radius: 10px;
  font-size: 12.5px;
}
.demo-role { width: 60px; flex: none; color: var(--text-2); font-weight: 600; }
.demo-cred { flex: 1; color: var(--text-3); font-family: Consolas, Monaco, monospace; font-size: 12px; }

@media (max-width: 960px) {
  .login-panel { flex-direction: column; }
  .panel-brand { display: none; }
  .panel-form { padding: 36px 28px; }
}
</style>
