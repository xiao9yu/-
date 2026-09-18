<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20) -->
<template>
  <div>
    <!-- 欢迎横幅 -->
    <div class="hero">
      <div class="hero-left">
        <div class="hero-hello">{{ greeting }}，{{ auth.user?.real_name || auth.user?.username }}</div>
        <div class="hero-sub">
          {{ today }} · 今天想准备哪门课？还是和学生聊一聊知识点？
        </div>
      </div>
      <div class="hero-right">
        <div class="hero-chip"><el-icon><Calendar /></el-icon>{{ weekday }}</div>
      </div>
    </div>

    <!-- 数据统计 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="stat-card liftable" @click="$router.push('/prep')">
          <div class="stat-icon" style="--tint: #eef0fb; --tint-ink: #5b5bd6"><el-icon><Notebook /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.courses ?? '—' }}</div>
            <div class="stat-label">我的课程</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="stat-card liftable" @click="$router.push('/module/assistant')">
          <div class="stat-icon" style="--tint: #e9f6ef; --tint-ink: #16a34a"><el-icon><Collection /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.docs ?? '—' }}</div>
            <div class="stat-label">知识库文档</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="stat-card liftable" @click="$router.push('/module/learn')">
          <div class="stat-icon" style="--tint: #fdf3e7; --tint-ink: #d97706"><el-icon><DataAnalysis /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ modules.length }}</div>
            <div class="stat-label">智能模块</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 功能模块 -->
    <div class="section-head">
      <h3>功能模块</h3>
      <span class="section-sub">平台核心能力一览</span>
    </div>
    <el-row :gutter="16">
      <el-col v-for="m in modules" :key="m.path" :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card shadow="never" class="mod-card liftable" @click="$router.push(m.path)">
          <div class="mod-top">
            <div class="mod-icon" :style="{ '--tint': m.tint, '--tint-ink': m.ink }"><el-icon :size="20"><component :is="m.icon" /></el-icon></div>
            <el-tag size="small" :type="m.status === '已上线' ? 'success' : 'info'" effect="light">{{ m.status }}</el-tag>
          </div>
          <div class="mod-name">{{ m.name }}</div>
          <div class="mod-desc">{{ m.desc }}</div>
          <div class="mod-go">进入模块<el-icon class="mod-arrow"><ArrowRight /></el-icon></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 快速开始 -->
    <div class="section-head">
      <h3>快速开始</h3>
      <span class="section-sub">三步上手平台</span>
    </div>
    <el-row :gutter="16">
      <el-col v-for="(t, i) in tips" :key="t.title" :xs="24" :sm="8">
        <el-card shadow="never" class="tip-card">
          <div class="tip-top">
            <div class="tip-step">{{ String(i + 1).padStart(2, '0') }}</div>
            <div class="tip-role">{{ t.role }}</div>
          </div>
          <div class="tip-title">{{ t.title }}</div>
          <div class="tip-desc">{{ t.desc }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 教育理念 -->
    <div class="motto">
      <el-icon><Sunny /></el-icon>
      <span>因材施教，教学相长 —— 让每位教师都拥有 AI 助教，让每位学生都拥有 AI 学伴。</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { ArrowRight, Calendar, ChatDotRound, Collection, DataAnalysis, Notebook, Sunny } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { listCourses } from '@/api/prep'
import { listKbDocuments } from '@/api/kb'

const auth = useAuthStore()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const today = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
const weekday = new Date().toLocaleDateString('zh-CN', { weekday: 'long' })

const stats = reactive<{ courses?: number; docs?: number }>({})

onMounted(async () => {
  // 统计来自真实接口；任一失败不影响页面展示（并行会话数据不同步时保持友好降级）
  try { stats.courses = (await listCourses()).length } catch { /* 忽略 */ }
  try { stats.docs = (await listKbDocuments()).length } catch { /* 忽略 */ }
})

const modules = [
  {
    path: '/prep', name: '智能备课', icon: Notebook, tint: '#eef0fb', ink: '#5b5bd6', status: '已上线',
    desc: '上传校本资源，AI 生成教案、课件大纲、习题与试卷；支持引用检索、多版本管理与 Word/PPT/PDF 导出。',
  },
  {
    path: '/module/assistant', name: '智能助教', icon: ChatDotRound, tint: '#e7f3fb', ink: '#0e7490', status: '已上线',
    desc: '私有/公共知识库混合检索问答，回答逐句引用溯源；支持 PDF、Office 与图片文档入库。',
  },
  {
    path: '/module/learn', name: '个性化学习', icon: DataAnalysis, tint: '#fdf3e7', ink: '#d97706', status: '规划中',
    desc: '面向学生的个性化学习路径推荐，工单 19 规划交付中。',
  },
]

const tips = [
  {
    role: '教师', title: '上传校本资源',
    desc: '在「智能备课」中为课程上传讲义与课件，AI 生成时可检索引用并标注来源。',
  },
  {
    role: '教师', title: '构建知识库',
    desc: '在「智能助教」中把教材 PDF、文档上传至私有库，学生提问即得带引用的回答。',
  },
  {
    role: '学生', title: '向助教提问',
    desc: '就知识点向智能助教提问，回答附带知识库原文引用，支持图片与表格溯源展示。',
  },
]
</script>

<style scoped>
/* ---------- 欢迎横幅 ---------- */
.hero {
  background:
    radial-gradient(600px 200px at 0% 0%, rgba(91, 91, 214, 0.1), transparent 70%),
    radial-gradient(500px 200px at 100% 100%, rgba(76, 136, 220, 0.08), transparent 70%),
    var(--surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 26px 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.hero-hello { font-size: 21px; font-weight: 700; letter-spacing: 0.3px; }
.hero-sub { margin-top: 8px; font-size: 13px; color: var(--text-3); }
.hero-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-2);
  font-size: 13px;
}

/* ---------- 统计卡片 ---------- */
.stat-row { margin-bottom: 4px; }
.stat-card {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 4px 6px;
  margin-bottom: 16px;
}
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 14px; width: 100%; }
.stat-icon {
  width: 46px; height: 46px;
  flex: none;
  border-radius: 12px;
  background: var(--tint);
  color: var(--tint-ink);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
}
.stat-num { font-size: 24px; font-weight: 700; line-height: 1.1; }
.stat-label { font-size: 12.5px; color: var(--text-3); margin-top: 3px; }

/* ---------- 模块卡片 ---------- */
.section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 22px 0 14px;
}
.section-head h3 { margin: 0; font-size: 16px; font-weight: 700; }
.section-sub { font-size: 12px; color: var(--text-3); }

.mod-card { cursor: pointer; height: 100%; }
.mod-top { display: flex; align-items: center; justify-content: space-between; }
.mod-icon {
  width: 44px; height: 44px;
  border-radius: 12px;
  background: var(--tint);
  color: var(--tint-ink);
  display: flex; align-items: center; justify-content: center;
}
.mod-name { font-size: 15.5px; font-weight: 700; margin-top: 14px; }
.mod-desc {
  font-size: 13px;
  color: var(--text-2);
  margin-top: 8px;
  line-height: 1.7;
  min-height: 44px;
}
.mod-go {
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--accent);
  display: flex; align-items: center; gap: 5px;
  font-weight: 500;
}
.mod-arrow { font-size: 12px; transition: transform 0.15s ease; }
.mod-card:hover .mod-arrow { transform: translateX(3px); }

/* ---------- 快速开始 ---------- */
.tip-card { height: 100%; }
.tip-top { display: flex; align-items: center; justify-content: space-between; }
.tip-step {
  font-size: 13px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: 1px;
  font-family: Consolas, Monaco, monospace;
}
.tip-role {
  font-size: 11px;
  color: var(--text-3);
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 3px 10px;
  border-radius: 20px;
}
.tip-title { font-size: 14.5px; font-weight: 700; margin-top: 12px; }
.tip-desc { font-size: 13px; color: var(--text-2); margin-top: 8px; line-height: 1.75; }

/* ---------- 教育理念 ---------- */
.motto {
  margin-top: 22px;
  padding: 15px 20px;
  border-radius: 14px;
  border: 1px dashed var(--border-strong);
  background: linear-gradient(90deg, rgba(91, 91, 214, 0.06), rgba(76, 136, 220, 0.04));
  display: flex;
  align-items: center;
  gap: 11px;
  font-size: 13px;
  color: var(--text-2);
  letter-spacing: 0.5px;
}
.motto .el-icon { color: var(--accent); font-size: 17px; flex: none; }
</style>
