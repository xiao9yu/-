<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <el-page-header :content="course?.name || '课程'" @back="$router.push('/prep')" />
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="10">
        <el-card>
          <template #header>校本资源（用于生成时引用）</template>
          <el-upload :show-file-list="false" :http-request="onUpload">
            <el-button>上传资源文件（docx/pptx/xlsx/pdf）</el-button>
          </el-upload>
          <el-input v-model="searchQ" placeholder="检索资源，如：梯度下降" style="margin-top: 12px">
            <template #append><el-button :loading="searching" @click="onSearch">检索</el-button></template>
          </el-input>
          <div style="margin-top: 12px; font-size: 13px">
            <div v-for="r in resources" :key="r.id" style="display: flex; justify-content: space-between; margin-top: 6px">
              <span>📄 {{ r.filename }}</span>
              <el-button size="small" type="text" @click="onDeleteResource(r)">删除</el-button>
            </div>
          </div>
          <div v-for="h in searchHits" :key="h.ref" style="margin-top: 10px; font-size: 13px">
            <div><b>{{ h.ref }}</b> <el-tag size="small">{{ h.score }}</el-tag></div>
            <div style="color: #666">{{ h.excerpt }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card>
          <template #header>AI 生成</template>
          <el-form label-width="90px">
            <el-form-item label="生成类型">
              <el-radio-group v-model="genForm.type">
                <el-radio-button value="plan">教案</el-radio-button>
                <el-radio-button value="cw">课件大纲</el-radio-button>
                <el-radio-button value="exercises">习题</el-radio-button>
                <el-radio-button value="case">案例</el-radio-button>
                <el-radio-button value="exam">月考试题</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="章节"><el-input v-model="genForm.chapter" placeholder="如：第3章 机器学习基础" /></el-form-item>
            <el-form-item label="教学目标"><el-input v-model="genForm.objectives" type="textarea" /></el-form-item>
            <el-form-item label="课时"><el-input v-model="genForm.hours" placeholder="2课时" /></el-form-item>
            <el-form-item v-if="genForm.type === 'exercises'" label="知识点">
              <el-input v-model="genForm.knowledgePoints" placeholder="用、分隔：梯度下降、线性回归" />
            </el-form-item>
            <el-form-item v-if="genForm.type === 'exam'" label="知识点分布">
              <el-input v-model="genForm.distribution" placeholder="梯度下降:30%、线性回归:30%（知识点:占比 换行分隔）" type="textarea" />
            </el-form-item>
            <el-form-item label="引用资源">
              <el-input v-model="genForm.query" placeholder="留空不检索；填写关键词将检索校本资源并标注引用" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="generating" @click="onGenerate">生成初稿</el-button>
          <div v-if="result" style="margin-top: 16px">
            <h4>生成结果（{{ result.type }}）</h4>
            <pre style="background: #f5f7fa; padding: 12px; max-height: 300px; overflow: auto">{{ JSON.stringify(result.content, null, 2) }}</pre>
            <el-input v-model="lessonTitle" placeholder="保存为教案标题" style="margin-top: 8px; width: 300px" />
            <el-button type="success" @click="onSave">保存为教案/课件</el-button>
            <div v-if="result.citations?.length" style="margin-top: 8px">
              <el-tag v-for="c in result.citations" :key="c.ref_no" style="margin-right: 6px">
                [{{ c.ref_no }}] 来源：{{ c.source }}{{ c.page ? ` 第${c.page}页` : '' }}
              </el-tag>
            </div>
          </div>
        </el-card>
        <el-card style="margin-top: 16px">
          <template #header>本课程教案/课件</template>
          <el-table :data="lessons" @row-click="(row: any) => $router.push(`/prep/lesson/${row.id}`)">
            <el-table-column prop="title" label="标题" />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">{{ LESSON_TYPE_LABELS[row.lesson_type] || row.lesson_type }}</template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="80" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
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
const genForm = reactive({ type: 'plan', chapter: '', objectives: '', hours: '', knowledgePoints: '', distribution: '', query: '' })
const generating = ref(false)
const result = ref<any>(null)
const lessonTitle = ref('')
const lessons = ref<any[]>([])
const resources = ref<CourseResource[]>([])

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
    if (genForm.type === 'exercises') {
      payload.knowledge_points = genForm.knowledgePoints.split(/[、,，]/).filter(Boolean)
    }
    if (genForm.type === 'exam' && genForm.distribution.trim()) {
      payload.distribution = genForm.distribution.split('\n').filter(Boolean).map((line) => {
        const [kp, pct] = line.split(/[:：]/)
        return { '知识点': kp.trim(), '占比': (pct || '').trim() }
      })
    }
    result.value = await generateContent(courseId, payload)
    lessonTitle.value = result.value.content['标题'] || result.value.content['试卷标题'] || '未命名'
  } finally { generating.value = false }
}

async function onSave() {
  if (!lessonTitle.value) { ElMessage.warning('请填写标题'); return }
  await createLesson(courseId, { title: lessonTitle.value, lesson_type: genForm.type, content_json: result.value.content })
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>
