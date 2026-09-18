<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) -->
<template>
  <el-row :gutter="16" class="assistant-row">
    <!-- 知识库 -->
    <el-col :span="8">
      <el-card class="kb-card">
        <template #header>
          <div class="card-head">
            <span><el-icon class="head-icon"><Collection /></el-icon>知识库管理</span>
            <el-tag size="small" effect="plain">{{ docs.length }} 份文档</el-tag>
          </div>
        </template>
        <el-tabs v-model="scope" @tab-change="loadDocs" class="kb-tabs">
          <el-tab-pane label="我的私有库" name="private" />
          <el-tab-pane v-if="isAdmin" label="公共库（管理员）" name="public" />
        </el-tabs>
        <el-upload :show-file-list="false" :http-request="onUpload" class="kb-upload">
          <el-button type="primary" :loading="uploading" class="kb-upload-btn">
            <el-icon class="btn-ico"><UploadFilled /></el-icon>
            {{ scope === 'public' ? '上传到公共库' : '上传到私有库' }}
          </el-button>
        </el-upload>
        <el-alert type="info" :closable="false" class="kb-alert"
          title="支持 PDF/DOCX/PPTX/XLSX/TXT/MD/图片；.doc/.ppt/.xls 请先转换为新版格式" />

        <div class="kb-list">
          <div v-for="d in docs" :key="d.id" class="kb-item">
            <div class="kb-item-icon" :style="{ '--tint': tintOf(d.title), '--tint-ink': inkOf(d.title) }">
              <el-icon :size="17"><component :is="iconOf(d.title)" /></el-icon>
            </div>
            <div class="kb-item-main">
              <div class="kb-item-title">{{ d.title }}</div>
              <div class="kb-item-tags">
                <el-tag size="small" :type="d.scope === 'public' ? 'warning' : 'info'" effect="light">
                  {{ d.scope === 'public' ? '公共库' : '私有库' }}
                </el-tag>
                <el-tag v-if="d.status === 'ready'" size="small" type="success" effect="light">{{ d.chunk_count }} 块</el-tag>
                <el-tooltip v-else :content="d.error || '入库失败'">
                  <el-tag size="small" type="danger" effect="light">失败</el-tag>
                </el-tooltip>
              </div>
            </div>
            <el-button v-if="isAdmin || d.owner_id === auth.user?.id" text size="small" type="danger"
              class="kb-item-del" @click="onDelete(d)"><el-icon><Delete /></el-icon></el-button>
          </div>
          <el-empty v-if="!docs.length" description="暂无文档，上传教材即可提问" :image-size="80" />
        </div>
      </el-card>
    </el-col>

    <!-- 对话区 -->
    <el-col :span="16">
      <el-card class="chat-card">
        <template #header>
          <div class="card-head">
            <span><el-icon class="head-icon"><ChatDotRound /></el-icon>智能助教问答（引用溯源）</span>
            <el-tag size="small" effect="plain" type="success">知识库 RAG</el-tag>
          </div>
        </template>
        <div ref="chatBox" class="chat-box">
          <div v-for="(m, i) in messages" :key="i" class="chat-row" :class="m.role">
            <el-avatar :size="34" class="chat-avatar" :class="m.role">
              <el-icon v-if="m.role === 'assistant'" :size="18"><MagicStick /></el-icon>
              <span v-else>{{ avatarText }}</span>
            </el-avatar>
            <div class="chat-content">
              <div class="chat-meta" :class="m.role">
                <span class="chat-name">{{ m.role === 'assistant' ? '智能助教' : auth.user?.real_name || auth.user?.username }}</span>
                <span class="chat-time">{{ timeOf(i) }}</span>
              </div>
              <div class="chat-bubble" :class="m.role">
                <span v-if="m.text">{{ m.text }}</span>
                <span v-else class="typing"><i /><i /><i /></span>
              </div>
              <div v-if="m.citations?.length" class="cite-list">
                <el-card v-for="c in m.citations" :key="c.ref_no" shadow="never" class="cite-card">
                  <template #header>
                    <div class="cite-head">
                      <span class="cite-ref">[{{ c.ref_no }}]</span>
                      <el-icon class="cite-ico" :size="14"><component :is="iconOf(c.source)" /></el-icon>
                      <span class="cite-src">{{ c.source }}{{ c.page ? ` · 第${c.page}页` : '' }}</span>
                      <el-tag size="small" effect="plain">{{ c.kind }}</el-tag>
                    </div>
                  </template>
                  <el-image v-if="c.kind === 'image'" :src="images[c.chunk_id] || ''" fit="contain"
                    class="cite-img" :preview-src-list="[images[c.chunk_id] || '']" />
                  <el-skeleton v-if="c.kind === 'image' && images[c.chunk_id] === undefined" :rows="2" animated />
                  <pre v-if="c.kind === 'table'" class="cite-table">{{ c.text }}</pre>
                  <el-collapse class="cite-collapse">
                    <el-collapse-item title="查看原文摘录">
                      <div class="cite-excerpt">{{ c.text }}</div>
                    </el-collapse-item>
                  </el-collapse>
                </el-card>
              </div>
            </div>
          </div>
          <div v-if="!messages.length" class="chat-welcome">
            <div class="welcome-mark"><el-icon :size="26"><MagicStick /></el-icon></div>
            <div class="welcome-title">你好，我是智能助教</div>
            <div class="welcome-sub">基于知识库回答你的问题，答案将逐句引用原文。试着问：</div>
            <div class="welcome-suggests">
              <span v-for="s in suggests" :key="s" class="suggest-chip" @click="askSuggestion(s)">{{ s }}</span>
            </div>
          </div>
        </div>
        <div class="chat-input">
          <el-input v-model="question" placeholder="基于知识库提问，如：梯度下降的学习率怎么选？"
            @keyup.enter="onAsk" :disabled="answering" size="large" class="chat-input-box" />
          <el-button type="primary" size="large" :loading="answering" @click="onAsk" class="send-btn">
            <el-icon class="btn-ico"><Promotion /></el-icon>发送
          </el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Collection, DataAnalysis, Delete, Document, MagicStick,
  Notebook, Picture, Promotion, Tickets, UploadFilled,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import {
  askStream, deleteKbDocument, listKbDocuments, loadChunkImage,
  uploadKbDocument, type KbCitation, type KbDocument,
} from '@/api/kb'

interface Msg { role: 'user' | 'assistant'; text: string; citations?: KbCitation[]; at: string }

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const avatarText = computed(() => (auth.user?.real_name || auth.user?.username || '?').slice(0, 1).toUpperCase())
const scope = ref('private')
const docs = ref<KbDocument[]>([])
const uploading = ref(false)
const question = ref('')
const messages = ref<Msg[]>([])
const answering = ref(false)
const chatBox = ref<HTMLElement>()
const images = ref<Record<string, string>>({})   // chunk_id → objectURL（接口需 Bearer，img 标签无法带头，故 fetch blob）

const suggests = ['梯度下降的学习率怎么选？', '什么是反向传播？', '过拟合如何解决？']

/** 文件类型 → 图标与配色（PDF 红 / Office 蓝 / 表格绿 / 图片紫 / 文本灰） */
function iconOf(name: string) {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return Document
  if (['doc', 'docx', 'ppt', 'pptx'].includes(ext)) return Notebook
  if (['xls', 'xlsx', 'csv'].includes(ext)) return Tickets
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp'].includes(ext)) return Picture
  return Document
}
function tintOf(name: string) {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return '#fdeeee'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '#e9f6ef'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp'].includes(ext)) return '#f3eefd'
  return '#eef0fb'
}
function inkOf(name: string) {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return '#dc2626'
  if (['xls', 'xlsx', 'csv'].includes(ext)) return '#16a34a'
  if (['png', 'jpg', 'jpeg', 'gif', 'bmp'].includes(ext)) return '#7c3aed'
  return '#5b5bd6'
}

function timeOf(i: number) {
  const m = messages.value[i]
  if (!m?.at) return ''
  return new Date(m.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadDocs() {
  // 列表含本人私有库与全部公共库（公共库只读展示，非 admin 无删除按钮）
  docs.value = await listKbDocuments()
}

async function onUpload(opt: any) {
  uploading.value = true
  try {
    await uploadKbDocument(opt.file, scope.value)
    ElMessage.success('已入库')
    await loadDocs()
  } finally { uploading.value = false }
}

async function onDelete(d: KbDocument) {
  await deleteKbDocument(d.id)
  ElMessage.success('已删除')
  await loadDocs()
}

async function loadImg(chunkId: string) {
  if (images.value[chunkId]) return
  try {
    const blob = await loadChunkImage(chunkId)
    images.value[chunkId] = URL.createObjectURL(blob)
  } catch {
    // 图片获取失败：标记空串隐藏骨架占位，避免未处理 rejection 与永久转圈（复审 Important 修复）
    images.value[chunkId] = ''
  }
}

function askSuggestion(s: string) {
  question.value = s
  void onAsk()
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || answering.value) return
  question.value = ''
  messages.value.push({ role: 'user', text: q, at: new Date().toISOString() })
  const msg: Msg = { role: 'assistant', text: '', at: new Date().toISOString() }
  messages.value.push(msg)
  answering.value = true
  try {
    await askStream(q,
      (citations) => {
        msg.citations = citations
        citations.filter((c) => c.kind === 'image').forEach((c) => { void loadImg(c.chunk_id) })
        scrollBottom()
      },
      (text) => { msg.text += text; scrollBottom() })
    if (!msg.text) msg.text = '（无内容）'
  } catch (err: any) {
    msg.text = `生成失败：${err?.message || '未知错误'}`
    ElMessage.error(err?.message || '问答失败')
  } finally { answering.value = false }
}

async function scrollBottom() {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

onMounted(loadDocs)
</script>

<style scoped>
.assistant-row { height: calc(100vh - 172px); }

.card-head { display: flex; align-items: center; justify-content: space-between; }
.head-icon { margin-right: 7px; color: var(--accent); vertical-align: -2px; }
.btn-ico { margin-right: 5px; }

/* ---------- 知识库 ---------- */
.kb-card { height: 100%; display: flex; flex-direction: column; }
.kb-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.kb-tabs :deep(.el-tabs__header) { margin-bottom: 4px; }
.kb-upload :deep(.el-upload) { width: 100%; }
.kb-upload-btn { width: 100%; }
.kb-alert { margin-top: 10px; }
.kb-alert :deep(.el-alert__title) { font-size: 12px; }

.kb-list { margin-top: 12px; overflow-y: auto; flex: 1; padding-right: 2px; }
.kb-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 8px;
  transition: all 0.15s ease;
  background: var(--surface);
}
.kb-item:hover { border-color: var(--border-strong); box-shadow: var(--shadow-sm); }
.kb-item-icon {
  width: 34px; height: 34px; flex: none;
  border-radius: 9px;
  background: var(--tint);
  color: var(--tint-ink);
  display: flex; align-items: center; justify-content: center;
}
.kb-item-main { flex: 1; min-width: 0; }
.kb-item-title {
  font-size: 13px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.kb-item-tags { margin-top: 5px; display: flex; gap: 4px; }
.kb-item-del { flex: none; }

/* ---------- 对话 ---------- */
.chat-card { height: 100%; display: flex; flex-direction: column; }
.chat-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.chat-box { flex: 1; overflow-y: auto; padding: 6px 8px 4px; }

.chat-row { display: flex; gap: 10px; margin-bottom: 22px; }
.chat-row.user { flex-direction: row-reverse; }
.chat-avatar {
  flex: none;
  font-size: 13px; font-weight: 600;
}
.chat-avatar.user { background: linear-gradient(135deg, #34d399, #10b981); color: #fff; }
.chat-avatar.assistant { background: linear-gradient(135deg, #6a6ae0, #4a4ac8); color: #fff; }
.chat-content { max-width: 80%; }
.chat-row.user .chat-content { display: flex; flex-direction: column; align-items: flex-end; }
.chat-meta { display: flex; gap: 8px; align-items: baseline; margin-bottom: 6px; }
.chat-meta.user { flex-direction: row-reverse; }
.chat-name { font-size: 12px; font-weight: 600; color: var(--text-2); }
.chat-time { font-size: 11px; color: var(--text-3); }

.chat-bubble {
  display: inline-block;
  padding: 11px 15px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
}
.chat-bubble.user {
  background: linear-gradient(135deg, #6a6ae0, #5b5bd6);
  color: #fff;
  border-top-right-radius: 4px;
  box-shadow: 0 3px 10px rgba(91, 91, 214, 0.25);
}
.chat-bubble.assistant {
  background: var(--surface);
  border: 1px solid var(--border);
  border-top-left-radius: 4px;
  box-shadow: var(--shadow-sm);
}

/* 输入中动画 */
.typing { display: inline-flex; gap: 4px; align-items: center; padding: 4px 2px; }
.typing i {
  width: 6px; height: 6px; border-radius: 50%;
  background: #9e9ee9;
  animation: blink 1.2s infinite ease-in-out;
}
.typing i:nth-child(2) { animation-delay: 0.2s; }
.typing i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 70%, 100% { opacity: 0.25; transform: translateY(0); }
  35% { opacity: 1; transform: translateY(-3px); }
}

/* 欢迎引导 */
.chat-welcome {
  text-align: center;
  padding: 60px 20px 30px;
}
.welcome-mark {
  width: 60px; height: 60px;
  margin: 0 auto 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, #6a6ae0, #4a4ac8);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 8px 22px rgba(91, 91, 214, 0.35);
}
.welcome-title { font-size: 16px; font-weight: 700; }
.welcome-sub { font-size: 13px; color: var(--text-3); margin-top: 8px; }
.welcome-suggests { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.suggest-chip {
  font-size: 12.5px;
  color: var(--text-2);
  border: 1px solid var(--border-strong);
  border-radius: 20px;
  padding: 6px 14px;
  cursor: pointer;
  transition: all 0.15s ease;
  background: var(--surface);
}
.suggest-chip:hover { border-color: var(--accent); color: var(--accent); }

/* 引用卡片 */
.cite-list { margin-top: 8px; text-align: left; }
.cite-card { border-radius: 10px; margin-top: 6px; }
.cite-card :deep(.el-card__header) { padding: 10px 14px; }
.cite-card :deep(.el-card__body) { padding: 0 14px 8px; }
.cite-head { display: flex; align-items: center; gap: 7px; }
.cite-ref { color: var(--accent); font-size: 13px; font-weight: 700; }
.cite-ico { color: var(--text-3); }
.cite-src { flex: 1; font-size: 12.5px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cite-img { max-height: 160px; margin-bottom: 6px; }
.cite-table { white-space: pre-wrap; font-size: 12px; color: var(--text-2); margin: 0; }
.cite-collapse :deep(.el-collapse-item__header) { font-size: 12px; color: var(--text-3); height: 32px; border: none; }
.cite-collapse :deep(.el-collapse-item__wrap) { border: none; }
.cite-excerpt { font-size: 12px; color: var(--text-2); line-height: 1.7; white-space: pre-wrap; }

/* 输入区 */
.chat-input { display: flex; gap: 10px; margin-top: 14px; }
.chat-input-box :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--border) inset; }
.send-btn { letter-spacing: 2px; min-width: 96px; }
</style>
