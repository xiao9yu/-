<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18) -->
<template>
  <el-row :gutter="16" style="height: calc(100vh - 120px)">
    <el-col :span="8">
      <el-card style="height: 100%">
        <template #header>知识库管理</template>
        <el-tabs v-model="scope" @tab-change="loadDocs">
          <el-tab-pane label="我的私有库" name="private" />
          <el-tab-pane v-if="isAdmin" label="公共库（管理员）" name="public" />
        </el-tabs>
        <el-upload :show-file-list="false" :http-request="onUpload">
          <el-button type="primary" :loading="uploading">
            {{ scope === 'public' ? '上传到公共库' : '上传到私有库' }}
          </el-button>
        </el-upload>
        <el-alert type="info" :closable="false" style="margin-top: 8px"
          title="支持 PDF/DOCX/PPTX/XLSX/图片；.doc/.ppt/.xls 请先转换为新版格式" />
        <div v-for="d in docs" :key="d.id" style="margin-top: 10px; font-size: 13px">
          <div style="display: flex; justify-content: space-between; align-items: center">
            <span>
              <b>{{ d.title }}</b>
              <el-tag size="small" :type="d.scope === 'public' ? 'warning' : 'info'" style="margin-left: 4px">
                {{ d.scope === 'public' ? '公共库' : '私有库' }}
              </el-tag>
              <el-tag v-if="d.status === 'ready'" size="small" type="success">{{ d.chunk_count }} 块</el-tag>
              <el-tooltip v-else :content="d.error || '入库失败'">
                <el-tag size="small" type="danger">失败</el-tag>
              </el-tooltip>
            </span>
            <el-button v-if="isAdmin || d.owner_id === auth.user?.id" size="small" type="text" @click="onDelete(d)">删除</el-button>
          </div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card style="height: 100%">
        <template #header>智能助教问答（引用溯源）</template>
        <div ref="chatBox" style="height: calc(100% - 130px); overflow-y: auto; padding: 8px">
          <div v-for="(m, i) in messages" :key="i" :style="{ textAlign: m.role === 'user' ? 'right' : 'left' }">
            <div :style="bubbleStyle(m.role)">{{ m.text || '思考中……' }}</div>
            <div v-if="m.citations?.length" style="text-align: left">
              <el-card v-for="c in m.citations" :key="c.ref_no" shadow="never" style="margin-top: 8px">
                <template #header>
                  <b>[{{ c.ref_no }}] 来源：{{ c.source }}{{ c.page ? ` 第${c.page}页` : '' }}</b>
                  <el-tag size="small" style="margin-left: 6px">{{ c.kind }}</el-tag>
                </template>
                <el-image v-if="c.kind === 'image'" :src="images[c.chunk_id] || ''" fit="contain"
                  style="max-height: 160px; margin-bottom: 6px" :preview-src-list="[images[c.chunk_id] || '']" />
                <el-skeleton v-if="c.kind === 'image' && !images[c.chunk_id]" :rows="1" animated />
                <pre v-if="c.kind === 'table'" style="white-space: pre-wrap; font-size: 12px; color: #666">{{ c.text }}</pre>
                <el-collapse>
                  <el-collapse-item title="原文摘录">{{ c.text }}</el-collapse-item>
                </el-collapse>
              </el-card>
            </div>
          </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 10px">
          <el-input v-model="question" placeholder="基于知识库提问，如：梯度下降的学习率怎么选？"
            @keyup.enter="onAsk" :disabled="answering" />
          <el-button type="primary" :loading="answering" @click="onAsk">发送</el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  askStream, deleteKbDocument, listKbDocuments, loadChunkImage,
  uploadKbDocument, type KbCitation, type KbDocument,
} from '@/api/kb'

interface Msg { role: 'user' | 'assistant'; text: string; citations?: KbCitation[] }

const auth = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const scope = ref('private')
const docs = ref<KbDocument[]>([])
const uploading = ref(false)
const question = ref('')
const messages = ref<Msg[]>([])
const answering = ref(false)
const chatBox = ref<HTMLElement>()
const images = ref<Record<string, string>>({})   // chunk_id → objectURL（接口需 Bearer，img 标签无法带头，故 fetch blob）

function bubbleStyle(role: string) {
  return {
    display: 'inline-block', maxWidth: '80%', padding: '8px 12px', borderRadius: '8px',
    background: role === 'user' ? '#ecf5ff' : '#f5f7fa', marginTop: '8px', whiteSpace: 'pre-wrap',
    textAlign: 'left', fontSize: '14px',
  }
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

async function onAsk() {
  const q = question.value.trim()
  if (!q || answering.value) return
  question.value = ''
  messages.value.push({ role: 'user', text: q })
  const msg: Msg = { role: 'assistant', text: '' }
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
