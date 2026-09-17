<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <el-page-header :content="lesson?.title || '教案编辑'" @back="$router.push(`/prep/course/${lesson?.course_id}`)" />
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="17">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>内容编辑</span>
              <div>
                <!-- 导出按钮按教案类型显示（后端映射：docx←plan/case，pptx←cw，pdf←exercises/exam） -->
                <el-button v-if="['plan', 'case'].includes(lesson?.lesson_type || '')" @click="onExport('docx')">导出 Word</el-button>
                <el-button v-if="lesson?.lesson_type === 'cw'" @click="onExport('pptx')">导出 PPT</el-button>
                <el-button v-if="['exercises', 'exam'].includes(lesson?.lesson_type || '')" @click="onExport('pdf')">导出 PDF</el-button>
                <el-button type="primary" :loading="saving" @click="onSave">保存（新版本）</el-button>
              </div>
            </div>
          </template>
          <div style="border: 1px solid #ccc">
            <Toolbar style="border-bottom: 1px solid #ccc" :editor="editorRef" :default-config="toolbarConfig" />
            <Editor style="height: 480px; overflow-y: hidden" v-model="html" :default-config="editorConfig" @on-created="onCreated" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card>
          <template #header>资源引用（检索后一键插入）</template>
          <el-input v-model="refQuery" placeholder="检索课程资源">
            <template #append><el-button :loading="refSearching" @click="onRefSearch">检索</el-button></template>
          </el-input>
          <div v-for="h in refHits" :key="h.ref" style="margin-top: 10px; font-size: 13px">
            <div><b>{{ h.ref }}</b></div>
            <div style="color: #666">{{ h.excerpt }}</div>
            <el-button size="small" type="text" @click="onInsertRef(h)">插入正文</el-button>
          </div>
        </el-card>
        <el-card style="margin-top: 16px">
          <template #header>版本历史</template>
          <el-timeline>
            <el-timeline-item v-for="v in versions" :key="v.version" :timestamp="`v${v.version}`">
              <el-button size="small" @click="onRestore(v.version)">恢复此版本</el-button>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import '@wangeditor/editor/dist/css/style.css'
import {
  addLessonMedia, exportLesson, getLesson, listVersions, restoreLesson,
  searchResources, updateLesson, uploadFile, type Lesson,
} from '@/api/prep'

const route = useRoute()
const lessonId = Number(route.params.id)
const lesson = ref<Lesson | null>(null)
const html = ref('')
const saving = ref(false)
const versions = ref<any[]>([])
const refQuery = ref('')
const refHits = ref<any[]>([])
const refSearching = ref(false)

const editorRef = shallowRef()
const toolbarConfig = { excludeKeys: ['group-video'] }
const editorConfig = {
  placeholder: '在此编辑内容……',
  MENU_CONF: {
    // 插入多媒体：图片 base64 嵌入编辑器展示 + 底座 files 表落盘 + media_files 登记
    uploadImage: {
      async customUpload(file: File, insertFn: (url: string, alt: string, href: string) => void) {
        const reader = new FileReader()
        reader.onload = async () => {
          const base64 = reader.result as string
          insertFn(base64, file.name, base64)          // 编辑器内嵌展示（免鉴权加载）
          try {
            const record = await uploadFile(file)      // 底座文件服务落盘
            await addLessonMedia(lessonId, record.id)  // media_files 登记
            ElMessage.success('图片已上传并登记')
          } catch { ElMessage.warning('图片已插入编辑器，但服务器登记失败') }
        }
        reader.readAsDataURL(file)
      },
    },
  },
}

function onCreated(editor: any) { editorRef.value = editor }

async function load() {
  lesson.value = (await getLesson(lessonId)) as Lesson
  html.value = lesson.value.content_json?.html || jsonToHtml(lesson.value.content_json)
  versions.value = (await listVersions(lessonId)) as any[]
}

/** 结构化 JSON 初稿 → HTML（生成结果进入编辑器的展示渲染）。 */
function jsonToHtml(data: any): string {
  if (!data) return ''
  if (typeof data === 'string') return data
  const parts: string[] = []
  if (data['标题'] || data['试卷标题']) parts.push(`<h1>${data['标题'] || data['试卷标题']}</h1>`)
  for (const key of ['教学目标', '教学重点', '教学难点']) {
    if (Array.isArray(data[key])) parts.push(`<h3>${key}</h3><ul>${data[key].map((x: string) => `<li>${x}</li>`).join('')}</ul>`)
  }
  if (Array.isArray(data['教学过程'])) {
    parts.push('<h3>教学过程</h3><table border="1" cellpadding="4">' +
      data['教学过程'].map((s: any) => `<tr><td>${s['环节']}（${s['时长']}）</td><td>${s['内容']}</td></tr>`).join('') + '</table>')
  }
  if (data['作业']) parts.push(`<h3>作业</h3><p>${data['作业']}</p>`)
  if (data['板书设计']) parts.push(`<h3>板书设计</h3><p>${data['板书设计']}</p>`)
  for (const key of ['案例背景', '案例描述', '问题', '案例分析', '结论']) {
    if (data[key]) parts.push(`<h3>${key}</h3><p>${data[key]}</p>`)
  }
  if (Array.isArray(data['幻灯片'])) {
    parts.push(data['幻灯片'].map((s: any) => `<h3>${s['标题']}</h3><ul>${(s['要点'] || []).map((x: string) => `<li>${x}</li>`).join('')}</ul>`).join(''))
  }
  if (Array.isArray(data['习题'])) {
    parts.push('<h3>习题</h3>' + data['习题'].map((e: any, i: number) =>
      `<p>${i + 1}. ${e['题干']}</p><p>${(e['选项'] || []).join('<br>')}</p><p>答案：${e['答案']}　知识点：${e['知识点']}（${e['难度']}）</p>`).join(''))
  }
  if (Array.isArray(data['大题'])) {
    parts.push(data['大题'].map((s: any) =>
      `<h3>${s['题型']}（${s['知识点']}）</h3>` + (s['题目'] || []).map((q: any, i: number) =>
        `<p>${i + 1}. ${q['题干']}</p><p>答案：${q['答案']}</p>`).join('')).join(''))
  }
  return parts.join('')
}

async function onRefSearch() {
  if (!refQuery.value || !lesson.value) return
  refSearching.value = true
  try {
    const data = await searchResources(lesson.value.course_id, refQuery.value)
    refHits.value = data.hits
  } finally {
    refSearching.value = false
  }
}

function onInsertRef(h: any) {
  editorRef.value?.restoreSelection()
  editorRef.value?.insertText(h.ref)
  ElMessage.success('已插入正文')
}

async function onSave() {
  saving.value = true
  try {
    await updateLesson(lessonId, { ...(lesson.value?.content_json || {}), html: html.value })
    ElMessage.success('已保存新版本')
    await load()
  } finally { saving.value = false }
}

// 导出需带 Authorization 头（后端 HTTPBearer 认证），window.open 无法携带
// 请求头（会 401），故改用 axios 下载 blob 后触发浏览器保存（偏离 brief 原方案）。
async function onExport(format: string) {
  try {
    const blob = await exportLesson(lessonId, format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${lesson.value?.title || 'lesson'}.${format}`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已开始下载')
  } catch { /* 错误提示由 http 拦截器统一弹出 */ }
}

async function onRestore(version: number) {
  await restoreLesson(lessonId, version)
  ElMessage.success('已恢复')
  await load()
}

onMounted(load)
onBeforeUnmount(() => { editorRef.value?.destroy() })
</script>
