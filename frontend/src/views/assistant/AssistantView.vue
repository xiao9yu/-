<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) -->
<template>
  <el-row :gutter="16" class="assistant-row">
    <!-- 知识库 -->
    <el-col :span="6">
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

    <!-- 数字人智能问答：整块面板只出现数字人（无聊天消息面板） -->
    <el-col :span="18">
      <el-card class="assistant-card">
        <template #header>
          <div class="card-head">
            <span><el-icon class="head-icon"><ChatDotRound /></el-icon>朵娅 · 数字人助教</span>
            <div class="head-side">
              <el-tag v-if="turns > 0" size="small" type="warning" effect="light" class="turn-tag">
                第 {{ turns + 1 }} 轮 · 记得上文
              </el-tag>
              <el-tag v-else size="small" effect="plain" type="success">知识库 RAG</el-tag>
              <el-button size="small" text @click="openHistory" class="head-btn">
                <el-icon class="btn-ico"><Clock /></el-icon>历史对话
              </el-button>
              <el-button size="small" text :disabled="turns === 0 && !currentQ" @click="newChat" class="head-btn">
                <el-icon class="btn-ico"><Plus /></el-icon>新对话
              </el-button>
              <span class="voice-state">{{ displayStateText }}</span>
              <el-switch v-model="muted" size="small" inline-prompt active-text="静音" inactive-text="朗读" @change="onMute" />
            </div>
          </div>
        </template>

        <div class="assistant-body">
          <!-- 整块面板只有数字人：回答由朵娅说出口，文字以气泡从她身上发出（无下方文字窗口） -->
          <div class="avatar-stage">
            <Live2DAvatar ref="avatarRef" />

            <!-- 当前一轮问答气泡（从数字人发出） -->
            <div v-if="currentQ || partial" class="talk-bubble">
              <div class="bubble-q">
                <el-tag v-if="partial && !currentA?.text" size="small" type="info" effect="plain" class="live-tag">
                  正在听
                </el-tag>
                {{ currentA?.text ? currentQ : (partial || currentQ) }}
              </div>
              <div class="bubble-a">
                <span v-if="currentA?.text">{{ currentA.text }}</span>
                <span v-else-if="partial" class="bubble-hint">说完停一下，我会自动接话</span>
                <span v-else class="typing"><i /><i /><i /></span>
              </div>
              <div v-if="currentA?.citations?.length" class="bubble-cites">
                <el-button v-for="c in currentA.citations" :key="c.ref_no" size="small" text
                  class="cite-chip" @click="citeDialog = true">
                  [{{ c.ref_no }}] {{ c.source }}{{ c.page ? ` · 第${c.page}页` : '' }}
                </el-button>
              </div>
            </div>

            <!-- 欢迎引导（覆盖在舞台上） -->
            <div v-else class="stage-welcome">
              <span class="welcome-title">你好，我是朵娅</span>
              <span class="welcome-sub">基于知识库回答你的问题，我会把答案读给你听并引用原文。试着问：</span>
              <span class="suggest-chips">
                <span v-for="s in suggests" :key="s" class="suggest-chip" @click="askSuggestion(s)">{{ s }}</span>
              </span>
              <span v-if="turns > 0" class="welcome-sub resume-hint">
                正在继续上次对话（已 {{ turns }} 轮）——可以直接追问，我记着上文
              </span>
            </div>

            <div v-if="!currentQ && !partial" class="avatar-hint">
              {{ streamMode ? '自然对话中：直接说话，我听到停顿就回答' : '打字提问，或用自然对话模式直接开口' }}
            </div>
          </div>

          <!-- 控制区 -->
          <div class="control-row">
            <el-input v-model="question" placeholder="基于知识库提问，可追问，如：梯度下降的学习率怎么选？"
              @keyup.enter="onAsk" :disabled="answering || voiceBusy" size="large" class="chat-input-box" />
            <el-button type="primary" size="large" :loading="answering" :disabled="voiceBusy" @click="onAsk" class="send-btn">
              <el-icon class="btn-ico"><Promotion /></el-icon>发送
            </el-button>
            <el-button v-if="streamAvailable" class="stream-btn" size="large"
              :type="streamMode ? 'success' : 'default'" :plain="streamMode"
              :disabled="!voiceReady || answering || talking" @click="toggleStreamMode">
              <el-icon class="btn-ico"><Microphone /></el-icon>{{ streamMode ? '结束对话' : '自然对话' }}
            </el-button>
            <el-button v-else class="talk-btn" size="large" :loading="voiceState === 'transcribing' || voiceState === 'thinking'"
              :disabled="!voiceReady || answering" @pointerdown="startTalk" @pointerup="stopTalk"
              @pointerleave="stopTalk" @pointercancel="stopTalk">
              <el-icon class="btn-ico"><Microphone /></el-icon>{{ talking ? '松开结束' : '按住说话' }}
            </el-button>
            <el-button v-if="playerBusy" class="stop-btn" type="danger" plain size="large" @click="interrupt">
              <el-icon class="btn-ico"><VideoPause /></el-icon>打断
            </el-button>
          </div>
          <div class="voice-row">
            <span class="mic-hint">
              需允许麦克风权限；语音识别与端点检测均在本机完成，录音不出本机。
              <template v-if="streamAvailable">「自然对话」由本地 VAD 自动断句，无需按键。</template>
            </span>
          </div>
        </div>
      </el-card>
    </el-col>
  </el-row>

  <!-- 引用原文弹窗 -->
  <el-dialog v-model="citeDialog" title="引用原文" width="640px">
    <el-card v-for="c in currentA?.citations || []" :key="c.ref_no" shadow="never" class="cite-card">
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
  </el-dialog>

  <!-- 历史对话：会话列表 + 消息回放（带引用），选中即续接该会话上下文 -->
  <el-drawer v-model="historyOpen" title="历史对话" size="440px" direction="rtl">
    <div v-if="!sessions.length" class="drawer-empty">
      <el-empty description="还没有对话记录" :image-size="70" />
    </div>
    <div v-for="s in sessions" :key="s.id" class="session-item"
      :class="{ active: s.id === sessionId }" @click="resumeSession(s)">
      <div class="session-main">
        <div class="session-title">{{ s.title || '新对话' }}</div>
        <div class="session-meta">{{ s.turns }} 轮 · {{ shortTime(s.updated_at) }}</div>
      </div>
      <el-button text size="small" type="danger" class="session-del"
        @click.stop="removeSession(s)"><el-icon><Delete /></el-icon></el-button>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound, Clock, Collection, Delete, Document, Microphone, Notebook, Picture,
  Plus, Promotion, Tickets, UploadFilled, VideoPause,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import {
  askStream, deleteKbDocument, listKbDocuments, loadChunkImage,
  uploadKbDocument, type KbCitation, type KbDocument,
} from '@/api/kb'
import {
  deleteChatSession, listChatMessages, listChatSessions,
  type ChatSessionInfo,
} from '@/api/chat'
import {
  speakTextTimed, voiceCapabilities, VoiceClient, type VoiceEvent,
} from '@/api/voice'
import { decodeTo16k, PcmStreamer, PlaybackManager, toBase64, wavEncode } from '@/utils/audio'
import Live2DAvatar from '@/components/live2d/Live2DAvatar.vue'

/** 当前一轮的助教回答（字幕区只展示这一条；引用点开弹窗看原文） */
interface Answer { text: string; citations?: KbCitation[] }

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const scope = ref('private')
const docs = ref<KbDocument[]>([])
const uploading = ref(false)
const question = ref('')
const answering = ref(false)
const currentQ = ref('')                    // 当前一轮的用户提问
const currentA = ref<Answer | null>(null)   // 当前一轮的助教回答
const citeDialog = ref(false)
const images = ref<Record<string, string>>({})   // chunk_id → objectURL（接口需 Bearer，img 标签无法带头，故 fetch blob）

// ---------- 多轮会话 ----------
const sessionId = ref<number | null>(null)  // 服务端会话 id：多轮上下文与引用延续的凭据
const turns = ref(0)                        // 已完成轮数（头部展示"第 N 轮"）
const historyOpen = ref(false)
const sessions = ref<ChatSessionInfo[]>([])

// ---------- 数字人 ----------
const muted = ref(false)
const voiceReady = ref(false)
const talking = ref(false)
const voiceState = ref<'idle' | 'recording' | 'transcribing' | 'thinking' | 'playing' | 'listening'>('idle')
const streamAvailable = ref(false)          // 服务端流式语音（VAD + 流式 ASR）是否就绪
const streamMode = ref(false)               // 自然对话开关
const partial = ref('')                     // 流式识别中间结果（边说边上屏）
const playing = ref(false)                  // 是否正在播报（用于显示打断与暂停送帧）
const avatarRef = ref<InstanceType<typeof Live2DAvatar>>()
const player = new PlaybackManager()
const voice = new VoiceClient()
let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let micStream: MediaStream | null = null
let talkTimer: number | undefined
let streamer: PcmStreamer | null = null
let voiceMsg: Answer | null = null   // 语音模式的当前回答对象

const voiceBusy = computed(() => ['recording', 'transcribing', 'thinking'].includes(voiceState.value))
const playerBusy = computed(() => playing.value || voiceState.value === 'transcribing' || voiceState.value === 'thinking')
const displayStateText = computed(() => (playing.value ? '播报中' : ({
  idle: streamMode.value ? '聆听中' : '待机中',
  recording: '正在聆听…', transcribing: '识别中…', thinking: '思考中…',
  playing: '播报中', listening: '聆听中',
} as const)[voiceState.value]))

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
function shortTime(iso: string) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('zh-CN', { hour12: false }).slice(5, 16)
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
    // 图片获取失败：标记空串隐藏骨架占位，避免未处理 rejection 与永久转圈
    images.value[chunkId] = ''
  }
}

function askSuggestion(s: string) {
  question.value = s
  void onAsk()
}

/** 朗读文本清洗：去引用编号 [n]、markdown 强调符与"参考答案："式前缀（字幕显示保留原样）。
 *  按句拆分后逐句清洗（与后端 spoken_text 同语义）："参考答案一："常出现在句中而非整段开头。 */
function stripForSpeech(text: string): string {
  const cleanOne = (s: string): string => {
    let t = s.replace(/[*#`]+/g, '')
    t = t.replace(/[\[【]\s*\d+(?:\s*[,，、]\s*\d+)*\s*[\]】]/g, '')
    while (true) {
      const next = t.replace(/^\s*(?:参考答案|参考思路|回答思路|答案)(?:\s*[一二三四五六七八九十\d]+)?\s*[:：]\s*/, '')
      if (next === t) return t
      t = next
    }
  }
  return text.split(/((?<=[。！？；])\s*|\n+)/).map(cleanOne).join('')
}

/** 统一播报：优先要口型时间轴（marks），拿不到就退回纯音频（音量驱动口型）。 */
async function speak(text: string) {
  if (muted.value || !text) return
  const cleaned = stripForSpeech(text).slice(0, 2000)
  if (!cleaned.trim()) return
  if (player.isPlaying) player.stop()
  const timed = await speakTextTimed(cleaned)
  if (!timed) return
  voiceState.value = 'playing'
  playing.value = true
  await player.enqueue(timed.blob, timed.marks)
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || answering.value) return
  // 在点击手势内同步创建/恢复 AudioContext：Chrome 自动播放策略只允许
  // 手势激活窗口内创建的上下文出声；等到 LLM 流式回答结束再创建必然被静音
  // （表现为"数字人不讲话"且口型不动）。
  player.ensureContext()
  question.value = ''
  currentQ.value = q
  partial.value = ''
  const msg: Answer = { text: '' }
  currentA.value = msg
  answering.value = true
  try {
    await askStream(q,
      (citations) => {
        msg.citations = citations
        citations.filter((c) => c.kind === 'image').forEach((c) => { void loadImg(c.chunk_id) })
      },
      (text) => { msg.text += text },
      {
        sessionId: sessionId.value,
        onSession: (id) => {
          // 服务端首次落地的会话 id：写回状态并同步给 WS，语音/文字共用同一条会话
          sessionId.value = id
          voice.setSession(id)
        },
      })
    if (!msg.text) msg.text = '（无内容）'
    turns.value += 1
  } catch (err: any) {
    msg.text = `生成失败：${err?.message || '未知错误'}`
    ElMessage.error(err?.message || '问答失败')
  } finally { answering.value = false }
  if (msg.text && !msg.text.startsWith('生成失败') && msg.text !== '（无内容）') {
    await speak(msg.text)
  }
}

function onVoiceEvent(e: VoiceEvent) {
  if (e.type === 'status') {
    if (e.state === 'cancelled') {
      voiceState.value = 'idle'
      streamMode.value = false
      stopStreamer()
    } else if (e.state === 'ready') {
      voiceReady.value = true
      if (!streamMode.value) voiceState.value = 'idle'
    } else if (e.state === 'listening') {
      voiceReady.value = true
      voiceState.value = 'listening'
    } else if (e.state === 'transcribing') voiceState.value = 'transcribing'
    else if (e.state === 'thinking') voiceState.value = 'thinking'
  } else if (e.type === 'partial') {
    partial.value = e.text
  } else if (e.type === 'transcript') {
    partial.value = ''
    currentQ.value = e.text
    voiceMsg = { text: '' }
    currentA.value = voiceMsg
  } else if (e.type === 'session') {
    // 语音链路也会建/复用会话：与文字链路共享同一条，混用不丢上文
    sessionId.value = e.id
    turns.value = e.turns
  } else if (e.type === 'citations') {
    if (voiceMsg) {
      voiceMsg.citations = e.items
      e.items.filter((c) => c.kind === 'image').forEach((c) => { void loadImg(c.chunk_id) })
    }
  } else if (e.type === 'delta') {
    if (voiceMsg) voiceMsg.text += e.text
  } else if (e.type === 'audio') {
    const bytes = atob(e.data)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    playing.value = true
    void player.enqueue(new Blob([arr], { type: 'audio/mpeg' }), e.marks)
  } else if (e.type === 'done' || e.type === 'segment_done') {
    if (voiceMsg && !voiceMsg.text) voiceMsg.text = '（无内容）'
    voiceMsg = null
    if (e.audio_total > 0) voiceState.value = 'playing'
    else if (!streamMode.value) voiceState.value = 'idle'
    if (e.type === 'segment_done') turns.value += 1
  } else if (e.type === 'error') {
    voiceMsg = null
    voiceState.value = streamMode.value ? 'listening' : 'idle'
    ElMessage.error(e.message)
  }
}

function onVoiceClose(reason: string) {
  voiceReady.value = false
  streamMode.value = false
  stopStreamer()
  if (reason !== 'closed') ElMessage.warning(reason)
}

async function startTalk() {
  if (!voiceReady.value || answering.value || talking.value) return
  if (player.isPlaying) interrupt()
  // 按住说话也是手势：此处创建 AudioContext 使后续 WS 音频分片可出声（自动播放策略）
  player.ensureContext()
  if (!(await ensureMic())) return
  chunks = []
  recorder = new MediaRecorder(micStream!)
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
  recorder.onstop = onRecordEnd
  recorder.start()
  talking.value = true
  voiceState.value = 'recording'
  talkTimer = window.setTimeout(stopTalk, 60000)  // 最长 60s 自动松开
}

function stopTalk() {
  if (!talking.value) return
  talking.value = false
  if (talkTimer) { clearTimeout(talkTimer); talkTimer = undefined }
  try { recorder?.stop() } catch { /* 已停止 */ }
}

async function onRecordEnd() {
  const blob = new Blob(chunks, { type: recorder?.mimeType || 'audio/webm' })
  if (blob.size < 1000) { voiceState.value = 'idle'; return }  // 过短视为误触
  try {
    const buf16k = await decodeTo16k(blob)
    voice.sendAudio(toBase64(wavEncode(buf16k)))
  } catch {
    voiceState.value = 'idle'
    ElMessage.error('录音处理失败，请重试')
  }
}

// ---------- 自然对话（服务端 VAD 端点检测 + 流式转写） ----------
async function ensureMic(): Promise<boolean> {
  if (micStream) return true
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    return true
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
    return false
  }
}

function stopStreamer() {
  streamer?.stop()
  streamer = null
  partial.value = ''
}

async function toggleStreamMode() {
  if (streamMode.value) {
    streamMode.value = false
    stopStreamer()
    voice.streamEnd()
    voiceState.value = 'idle'
    return
  }
  player.ensureContext()
  if (!(await ensureMic())) return
  streamer = new PcmStreamer(micStream!)
  streamer.onFrame = (pcm) => {
    // 播报期间不送帧：扬声器声音会被麦克风收回，造成"她回答自己"（后端同样会丢弃，
    // 前端先掐断是不浪费带宽与 CPU）
    if (!playing.value && !answering.value) voice.streamChunk(pcm)
  }
  streamer.start()
  voice.setSession(sessionId.value)
  voice.streamStart()
  streamMode.value = true
  partial.value = ''
}

function interrupt() {
  player.stop()
  playing.value = false
  // 自然对话：只掐掉本轮播报，监听继续（可以随时抢话）；按住说话：整轮取消
  if (streamMode.value) voice.interrupt()
  else { voice.cancel(); voiceState.value = 'idle' }
}

function onMute(v: string | number | boolean) {
  if (v) interrupt()  // 静音即打断当前播报
}

// ---------- 会话 ----------
function newChat() {
  sessionId.value = null
  turns.value = 0
  currentQ.value = ''
  currentA.value = null
  partial.value = ''
  voice.setSession(null)
  ElMessage.success('已开启新对话')
}

async function openHistory() {
  sessions.value = await listChatSessions()
  historyOpen.value = true
}

async function resumeSession(s: ChatSessionInfo) {
  const detail = await listChatMessages(s.id)
  const msgs = detail.messages
  const lastUser = [...msgs].reverse().find((m) => m.role === 'user')
  const lastAssistant = [...msgs].reverse().find((m) => m.role === 'assistant')
  sessionId.value = s.id
  voice.setSession(s.id)
  turns.value = Math.max(0, msgs.filter((m) => m.role === 'user').length - (lastAssistant ? 0 : 1))
  currentQ.value = lastUser?.content || ''
  currentA.value = lastAssistant
    ? { text: lastAssistant.content, citations: lastAssistant.citations }
    : null
  currentA.value?.citations?.filter((c) => c.kind === 'image')
    .forEach((c) => { void loadImg(c.chunk_id) })
  historyOpen.value = false
  ElMessage.success('已续接该对话，可直接追问')
}

async function removeSession(s: ChatSessionInfo) {
  await deleteChatSession(s.id)
  if (sessionId.value === s.id) newChat()
  sessions.value = await listChatSessions()
}

onMounted(() => {
  player.onMouth = (v) => avatarRef.value?.setMouth(v)
  player.onEnd = () => { playing.value = false; if (!streamMode.value) voiceState.value = 'idle' }
  voice.connect({ onEvent: onVoiceEvent, onClose: onVoiceClose })
  void loadDocs()
  void voiceCapabilities()
    .then((c) => { streamAvailable.value = c.stream })
    .catch(() => { streamAvailable.value = false })
})

onBeforeUnmount(() => {
  streamer?.stop()
  voice.close()
  player.stop()
  micStream?.getTracks().forEach((t) => t.stop())
})
</script>

<style scoped>
.assistant-row { height: calc(100vh - 172px); }
/* 列与卡片的高度用 flex 拉伸传递（el-col 拉伸后的高度对百分比解析不总是确定值，
   height:100% 链条会失效导致画布被撑出巨大尺寸）：列高 100% 于行，卡 flex:1 于列 */
.assistant-row .el-col { height: 100%; display: flex; }

.card-head { display: flex; align-items: center; justify-content: space-between; }
.head-icon { margin-right: 7px; color: var(--accent); vertical-align: -2px; }
.btn-ico { margin-right: 5px; }
.head-side { display: flex; align-items: center; gap: 10px; }
.head-btn { padding: 0 6px; }
.turn-tag { font-variant-numeric: tabular-nums; }
.voice-state { font-size: 12.5px; color: var(--text-3); }

/* ---------- 知识库 ---------- */
.kb-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
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

/* ---------- 数字人 ---------- */
.assistant-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.assistant-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.assistant-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }

/* 数字人形象区：占满整个回答面板 */
.avatar-stage {
  flex: 1;
  min-height: 0;
  position: relative;
  background: radial-gradient(ellipse at 50% 38%, #eef0fb 0%, #f7f8fc 58%, #f2f3f9 100%);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.avatar-hint {
  position: absolute; left: 0; right: 0; bottom: 8px;
  text-align: center; font-size: 12px; color: var(--text-3);
  pointer-events: none;
}

/* 问答气泡：覆盖在舞台下半部（人物脸部在舞台上半部，不被遮挡），尾巴朝上指向人物 */
.talk-bubble {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  width: min(62%, 540px);
  max-height: 42%;
  display: flex; flex-direction: column; gap: 7px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  box-shadow: var(--shadow-sm);
  overflow-y: auto;
  z-index: 2;
}
.talk-bubble::before {  /* 气泡尾巴：顶端朝上，指向上方人物 */
  content: ''; position: absolute; left: 50%; top: -9px; transform: translateX(-50%);
  border: 9px solid transparent; border-bottom-color: #fff;
}
.bubble-q { font-size: 12px; color: var(--text-3); word-break: break-word; }
.live-tag { margin-right: 6px; }
.bubble-a {
  font-size: 13.5px; line-height: 1.7; color: var(--text-1);
  white-space: pre-wrap; word-break: break-word;
}
.bubble-hint { font-size: 12.5px; color: var(--text-3); }
.bubble-cites { display: flex; flex-wrap: wrap; gap: 2px 6px; }
.cite-chip { font-size: 12px; color: var(--accent); padding: 0 6px; height: 24px; }

/* 欢迎引导（覆盖在舞台下部，避免挡住人物脸部） */
.stage-welcome {
  position: absolute; bottom: 34px; left: 50%; transform: translateX(-50%);
  width: min(76%, 640px);
  display: flex; flex-direction: column; gap: 6px; align-items: center;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 18px;
  box-shadow: var(--shadow-sm);
  z-index: 2;
}
.welcome-title { font-size: 15px; font-weight: 700; }
.welcome-sub { font-size: 12.5px; color: var(--text-3); }
.resume-hint { color: var(--accent); }
.suggest-chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 2px; }
.suggest-chip {
  font-size: 12.5px;
  color: var(--text-2);
  border: 1px solid var(--border-strong);
  border-radius: 20px;
  padding: 5px 13px;
  cursor: pointer;
  transition: all 0.15s ease;
  background: var(--surface);
}
.suggest-chip:hover { border-color: var(--accent); color: var(--accent); }

/* 输入中动画 */
.typing { display: inline-flex; gap: 4px; align-items: center; padding: 5px 2px; }
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

/* 控制区 */
.control-row { display: flex; gap: 10px; margin-top: 12px; }
.chat-input-box :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--border) inset; }
.send-btn { letter-spacing: 2px; min-width: 96px; }
.talk-btn { min-width: 132px; }
.stream-btn { min-width: 132px; }
.stop-btn { min-width: 96px; }
.voice-row { margin-top: 8px; }
.mic-hint { font-size: 12px; color: var(--text-3); }

/* 引用弹窗卡片 */
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

/* 历史对话抽屉 */
.drawer-empty { padding-top: 24px; }
.session-item {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  background: var(--surface);
}
.session-item:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }
.session-item.active { border-color: var(--accent); background: #f4f4ff; }
.session-main { flex: 1; min-width: 0; }
.session-title {
  font-size: 13px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.session-meta { font-size: 11.5px; color: var(--text-3); margin-top: 3px; }
.session-del { flex: none; }
</style>
