<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <el-page-header class="page-header" :content="course?.name || '课程'" @back="$router.push('/prep')" />
    <el-row :gutter="16" style="margin-top: 16px">
      <!-- 校本资源 -->
      <el-col :span="10">
        <el-card>
          <template #header>
            <div class="card-head">
              <span><el-icon class="head-icon"><FolderOpened /></el-icon>校本资源（用于生成时引用）</span>
              <el-tag size="small" effect="plain">{{ resources.length }}</el-tag>
            </div>
          </template>
          <el-upload :show-file-list="false" :http-request="onUpload">
            <el-button class="block-btn">
              <el-icon class="btn-ico"><UploadFilled /></el-icon>上传资源文件（docx/pptx/xlsx/pdf）
            </el-button>
          </el-upload>
          <el-input v-model="searchQ" placeholder="检索资源，如：梯度下降" style="margin-top: 12px">
            <template #append><el-button :loading="searching" @click="onSearch">检索</el-button></template>
          </el-input>

          <div class="res-list">
            <div v-for="r in resources" :key="r.id" class="res-item">
              <div class="res-icon" :style="{ '--tint': tintOf(r.filename), '--tint-ink': inkOf(r.filename) }">
                <el-icon :size="15"><component :is="iconOf(r.filename)" /></el-icon>
              </div>
              <span class="res-name">{{ r.filename }}</span>
              <el-button text size="small" type="danger" @click="onDeleteResource(r)"><el-icon><Delete /></el-icon></el-button>
            </div>
            <div v-if="!resources.length" class="list-empty">暂无资源，上传讲义/课件后可在生成时引用</div>
          </div>

          <template v-if="searchHits.length">
            <div class="hit-title">检索结果</div>
            <div v-for="h in searchHits" :key="h.ref" class="hit-item">
              <div class="hit-head">
                <b>{{ h.ref }}</b>
                <el-tag size="small" effect="plain">相关度 {{ h.score }}</el-tag>
              </div>
              <div class="hit-excerpt">{{ h.excerpt }}</div>
            </div>
          </template>
        </el-card>
      </el-col>

      <!-- AI 生成 + 教案列表 -->
      <el-col :span="14">
        <el-card>
          <template #header>
            <div class="card-head"><span><el-icon class="head-icon"><MagicStick /></el-icon>AI 生成</span></div>
          </template>
          <el-form label-width="90px">
            <el-form-item label="生成类型">
              <el-radio-group v-model="genForm.type">
                <el-radio-button value="plan">教案</el-radio-button>
                <el-radio-button value="cw">课件大纲</el-radio-button>
                <el-radio-button value="exercises">习题</el-radio-button>
                <el-radio-button value="kb_exercises">知识库出题</el-radio-button>
                <el-radio-button value="case">案例</el-radio-button>
                <el-radio-button value="exam">月考试题</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="章节"><el-input v-model="genForm.chapter" placeholder="如：第3章 机器学习基础" /></el-form-item>
            <el-form-item label="教学目标"><el-input v-model="genForm.objectives" type="textarea" /></el-form-item>
            <el-form-item label="课时"><el-input v-model="genForm.hours" placeholder="2课时" /></el-form-item>
            <el-form-item v-if="genForm.type === 'exercises' || genForm.type === 'kb_exercises'" label="知识点">
              <el-input v-model="genForm.knowledgePoints" placeholder="用、分隔：线性表、栈与队列" />
            </el-form-item>
            <el-form-item v-if="genForm.type === 'kb_exercises'" label="难度">
              <el-select v-model="genForm.difficulty" style="width: 220px">
                <el-option label="易中难混合" value="" />
                <el-option label="易" value="易" />
                <el-option label="中" value="中" />
                <el-option label="难" value="难" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="genForm.type === 'kb_exercises'" label="题数">
              <el-input-number v-model="genForm.count" :min="1" :max="20" />
            </el-form-item>
            <el-form-item v-if="genForm.type === 'exam'" label="知识点分布">
              <el-input v-model="genForm.distribution" placeholder="梯度下降:30%、线性回归:30%（知识点:占比 换行分隔）" type="textarea" />
            </el-form-item>
            <el-form-item :label="genForm.type === 'kb_exercises' ? '检索知识库' : '引用资源'">
              <el-input v-model="genForm.query" :placeholder="genForm.type === 'kb_exercises'
                ? '检索知识库关键词，留空按知识点或课程名检索' : '留空不检索；填写关键词将检索校本资源并标注引用'" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="generating" @click="onGenerate">
            <el-icon class="btn-ico"><MagicStick /></el-icon>{{ genForm.type === 'kb_exercises' ? '生成并进入学习题库' : '生成初稿' }}
          </el-button>

          <div v-if="result" class="result-panel">
            <div class="result-head">
              <span class="result-title">生成结果（{{ result.type }}）</span>
              <el-button text size="small" type="primary" @click="onCopyResult">复制 JSON</el-button>
            </div>
            <pre class="result-pre">{{ JSON.stringify(result.content, null, 2) }}</pre>
            <div v-if="result.type !== 'kb_exercises'" class="result-save">
              <el-input v-model="lessonTitle" placeholder="保存为教案标题" style="width: 300px" />
              <el-button type="success" @click="onSave">保存为教案/课件</el-button>
            </div>
            <div v-if="result.citations?.length" class="result-cites">
              <el-tag v-for="c in result.citations" :key="c.ref_no" effect="plain" class="result-cite">
                [{{ c.ref_no }}] {{ c.source }}{{ c.page ? ` 第${c.page}页` : '' }}
              </el-tag>
            </div>
          </div>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>
            <div class="card-head">
              <span><el-icon class="head-icon"><Document /></el-icon>本课程教案/课件</span>
              <el-tag size="small" effect="plain">{{ lessons.length }}</el-tag>
            </div>
          </template>
          <el-table :data="lessons" @row-click="(row: any) => $router.push(`/prep/lesson/${row.id}`)" class="lesson-table">
            <el-table-column prop="title" label="标题" min-width="200" />
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                <el-tag size="small" effect="light">{{ LESSON_TYPE_LABELS[row.lesson_type] || row.lesson_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="版本" width="90">
              <template #default="{ row }">v{{ row.version }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!lessons.length" description="暂无教案/课件，生成后在此管理" :image-size="70" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete, Document, FolderOpened, MagicStick, Notebook, Picture, Tickets, UploadFilled } from '@element-plus/icons-vue'
import {
  createLesson, deleteCourseResource, generateContent, getCourse, LESSON_TYPE_LABELS,
  listCourseLessons, listCourseResources, searchResources, uploadResource,
  type Course, type CourseResource,
} from '@/api/prep'

const route = useRoute()
const courseId = Number(route.params.id)
const course = ref<Course | null>(null)
const searchQ = ref('')
const searchHits = ref<any[]>([])
const searching = ref(false)
const genForm = reactive({ type: 'plan', chapter: '', objectives: '', hours: '', knowledgePoints: '', distribution: '', query: '', difficulty: '', count: 10 })
const generating = ref(false)
const result = ref<any>(null)
const lessonTitle = ref('')
const lessons = ref<any[]>([])
const resources = ref<CourseResource[]>([])

/** 资源文件类型 → 图标与配色 */
function iconOf(name: string) {
  const ext = (name || '').toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return Document
  if (['doc', 'docx'].includes(ext)) return Notebook
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

async function load() {
  course.value = (await getCourse(courseId)) as Course
  lessons.value = (await listCourseLessons(courseId)) as any[]
  resources.value = (await listCourseResources(courseId)) as CourseResource[]
}

async function onUpload(opt: any) {
  await uploadResource(courseId, opt.file)
  ElMessage.success('资源已上传')
  await load()
}

async function onDeleteResource(r: CourseResource) {
  await deleteCourseResource(courseId, r.id)
  ElMessage.success('资源已删除')
  await load()
}

async function onSearch() {
  if (!searchQ.value) return
  searching.value = true
  try {
    const data = await searchResources(courseId, searchQ.value)
    searchHits.value = data.hits
  } finally {
    searching.value = false
  }
}

async function onGenerate() {
  generating.value = true
  try {
    const payload: any = {
      type: genForm.type, chapter: genForm.chapter, objectives: genForm.objectives,
      hours: genForm.hours, query: genForm.query,
    }
    if (genForm.type === 'exercises' || genForm.type === 'kb_exercises') {
      payload.knowledge_points = genForm.knowledgePoints.split(/[、,，]/).filter(Boolean)
    }
    if (genForm.type === 'exam' && genForm.distribution.trim()) {
      payload.distribution = genForm.distribution.split('\n').filter(Boolean).map((line) => {
        const [kp, pct] = line.split(/[:：]/)
        return { '知识点': kp.trim(), '占比': (pct || '').trim() }
      })
    }
    if (genForm.type === 'kb_exercises') {
      payload.difficulty = genForm.difficulty
      payload.count = genForm.count
    }
    result.value = await generateContent(courseId, payload)
    if (genForm.type === 'kb_exercises') {
      const saved = result.value.lesson
      ElMessage.success(`已生成并进入学习题库：新增 ${saved.added} 题，共 ${saved.total} 题`)
      await load()
    } else {
      lessonTitle.value = result.value.content['标题'] || result.value.content['试卷标题'] || '未命名'
    }
  } finally { generating.value = false }
}

async function onCopyResult() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value.content, null, 2))
    ElMessage.success('已复制到剪贴板')
  } catch { ElMessage.warning('复制失败，请手动选择复制') }
}

async function onSave() {
  if (!lessonTitle.value) { ElMessage.warning('请填写标题'); return }
  await createLesson(courseId, { title: lessonTitle.value, lesson_type: genForm.type, content_json: result.value.content })
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>

<style scoped>
.page-header { margin-bottom: 2px; }

.card-head { display: flex; align-items: center; justify-content: space-between; }
.head-icon { margin-right: 7px; color: var(--accent); }
.btn-ico { margin-right: 5px; }
.block-btn { width: 100%; }

.res-list { margin-top: 12px; }
.res-item {
  display: flex; align-items: center; gap: 9px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  margin-bottom: 6px;
  font-size: 13px;
  background: var(--surface);
}
.res-icon {
  width: 26px; height: 26px; flex: none;
  border-radius: 7px;
  background: var(--tint);
  color: var(--tint-ink);
  display: flex; align-items: center; justify-content: center;
}
.res-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.list-empty { font-size: 12px; color: var(--text-3); text-align: center; padding: 14px 0; }

.hit-title { font-size: 13px; font-weight: 600; margin-top: 16px; color: var(--text-1); }
.hit-item {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 9px;
  font-size: 13px;
}
.hit-head { display: flex; align-items: center; justify-content: space-between; }
.hit-excerpt { color: var(--text-2); margin-top: 6px; line-height: 1.65; }

.result-panel {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid #dcdcf7;
  border-radius: 12px;
  background: #fafaff;
}
.result-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.result-title { font-size: 14px; font-weight: 600; }
.result-pre {
  background: var(--ink);
  color: #d5d8e4;
  padding: 14px;
  border-radius: 10px;
  max-height: 300px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  font-family: Consolas, Monaco, "Courier New", monospace;
}
.result-save { display: flex; gap: 8px; margin-top: 12px; }
.result-cites { margin-top: 10px; }
.result-cite { margin: 0 6px 4px 0; }

.lesson-table { cursor: pointer; }
</style>
