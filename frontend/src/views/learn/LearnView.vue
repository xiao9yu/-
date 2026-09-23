<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19) -->
<template>
  <div>
    <!-- 学习方向切换（Plan G：三方向联动全部面板） -->
    <div v-if="learnCourses.length" class="direction-bar">
      <span class="direction-label">学习方向</span>
      <el-select v-model="currentCourseId" style="width: 240px" @change="onSwitchDirection">
        <el-option v-for="c in learnCourses" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
    </div>
    <el-card v-if="!learnCourses.length">
      <el-empty description="暂无学习方向（需教师先在备课模块创建含习题的课程）" />
    </el-card>

    <!-- 未初始化画像：引导 -->
    <el-card v-if="learnCourses.length && profile && !profile.initialized">
      <el-empty description="还没有该方向的学习画像，先完成诊断测试或导入历史成绩">
        <el-button type="primary" @click="startDiagnostic">开始诊断测试</el-button>
        <el-button @click="openImport">导入历史成绩</el-button>
      </el-empty>
    </el-card>

    <!-- 诊断测试进行中 -->
    <el-card v-if="diagnosing">
      <template #header>
        <span>诊断测试（共 {{ diagQuestions.length }} 题）</span>
      </template>
      <el-empty v-if="!diagQuestions.length" description="暂无可用试题，请先由教师在智能备课模块生成习题" />
      <div v-for="(q, i) in diagQuestions" :key="q.stem" style="margin-bottom: 18px">
        <p><b>{{ i + 1 }}. {{ q.stem }}</b>
          <el-tag size="small" style="margin-left: 6px">{{ q.knowledge_point }}</el-tag>
          <el-tag size="small" type="info" style="margin-left: 4px">{{ q.difficulty }}</el-tag>
        </p>
        <el-radio-group v-model="diagAnswers[q.stem]">
          <el-radio v-for="opt in q.options" :key="opt" :value="opt">{{ opt }}</el-radio>
        </el-radio-group>
      </div>
      <div v-if="diagQuestions.length" style="margin-top: 16px">
        <el-button type="primary" :loading="submittingDiag" @click="onSubmitDiagnostic">提交诊断</el-button>
        <el-button @click="diagnosing = false">取消</el-button>
      </div>
    </el-card>

    <!-- 已初始化画像：三个 tab -->
    <el-tabs v-else-if="profile?.initialized" v-model="activeTab">
      <el-tab-pane label="画像仪表盘" name="dash">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card>
              <template #header>画像雷达图（知识点掌握度）</template>
              <div ref="radarEl" style="height: 340px"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card>
              <template #header>推荐学习路径（为什么推荐学这个）</template>
              <el-empty v-if="!path.length" description="全部知识点已掌握，继续保持！" />
              <el-timeline v-else style="padding-left: 4px">
                <el-timeline-item v-for="p in path" :key="p.kp_id" :timestamp="`第 ${p.order} 步 · 掌握度 ${p.mastery}`">
                  <b>{{ p.name }}</b>
                  <p style="color: #666; font-size: 13px; margin: 4px 0">{{ p.why }}</p>
                </el-timeline-item>
              </el-timeline>
            </el-card>
          </el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 16px">
          <el-col :span="12">
            <el-card>
              <template #header>今日任务</template>
              <el-empty v-if="!tasks.length" description="今日暂无任务" />
              <div v-for="t in tasks" :key="t.kp_id" style="margin-bottom: 10px">
                <div style="display: flex; justify-content: space-between; align-items: center">
                  <b>{{ t.name }}</b>
                  <el-button size="small" type="primary" @click="startTaskPractice(t)">开始练习</el-button>
                </div>
                <p style="color: #666; font-size: 13px; margin: 4px 0">{{ t.why }}</p>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card>
              <template #header>相似学生（协同过滤）</template>
              <el-empty v-if="!similar.length" description="暂无相似学生数据" />
              <div v-for="s in similar" :key="s.user_id" style="margin-bottom: 10px">
                <div style="display: flex; justify-content: space-between; align-items: center">
                  <span><b>{{ s.real_name }}</b> 相似度 {{ Math.round(s.similarity * 100) }}%</span>
                  <span v-if="s.strengths.length">
                    <el-tag v-for="kp in s.strengths" :key="kp" size="small" style="margin-left: 4px">{{ kp }}</el-tag>
                  </span>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="自适应练习" name="practice">
        <el-card>
          <template #header>自适应练习（正确率 &gt;80% 升难度、&lt;50% 降难度）</template>
          <div style="display: flex; gap: 8px; align-items: center">
            <el-select v-model="practiceKp" placeholder="选择知识点" style="width: 240px">
              <el-option v-for="k in kpOptions" :key="k" :label="k" :value="k" />
            </el-select>
            <el-button type="primary" :loading="loadingQuestion" @click="onNextQuestion">开始/下一题</el-button>
          </div>
          <el-empty v-if="!currentQuestion && !result" description="选择知识点后点击开始练习" />
          <div v-if="currentQuestion" style="margin-top: 16px">
            <p><b>{{ currentQuestion.stem }}</b>
              <el-tag size="small" style="margin-left: 6px">{{ currentQuestion.knowledge_point }}</el-tag>
              <el-tag size="small" type="info" style="margin-left: 4px">{{ currentQuestion.difficulty }}</el-tag>
            </p>
            <el-radio-group v-model="selectedAnswer" :disabled="!!result">
              <el-radio v-for="opt in currentQuestion.options" :key="opt" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <div style="margin-top: 12px">
              <el-button type="primary" :loading="submitting" :disabled="!selectedAnswer || !!result"
                @click="onSubmitAnswer">提交</el-button>
            </div>
          </div>
          <el-alert v-if="result" :type="result.correct ? 'success' : 'error'" :closable="false"
            style="margin-top: 16px"
            :title="result.correct ? `回答正确！正确答案：${result.answer}` : `回答错误，正确答案：${result.answer}`">
            <p style="margin: 6px 0"><b>解析：</b>{{ result.analysis }}</p>
            <p v-if="result.wrong_question" style="margin: 6px 0">
              <b>错题本：</b>
              <span v-if="result.wrong_question.status === 'generated'">已入册并生成 AI 解析（解析+错误原因+变式题），可在错题本查看</span>
              <span v-else>已入册，AI 解析生成失败，可在错题本点击"重新生成"</span>
            </p>
            <p style="margin: 6px 0; color: #666">当前练习难度：{{ result.difficulty_new }}</p>
          </el-alert>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="错题本" name="wrongbook">
        <el-card>
          <template #header>AIGC 错题本（答错自动入册：解析 + 错误原因 + 2~3 道变式题）</template>
          <el-empty v-if="!wrongbook.length" description="还没有错题，继续加油！" />
          <el-collapse v-else>
            <el-collapse-item v-for="w in wrongbook" :key="w.id">
              <template #title>
                <span style="display: inline-flex; align-items: center; gap: 6px">
                  <b>{{ w.stem.length > 40 ? w.stem.slice(0, 40) + '…' : w.stem }}</b>
                  <el-tag size="small">{{ w.knowledge_point }}</el-tag>
                  <el-tag size="small" type="info">{{ w.difficulty }}</el-tag>
                  <el-tag size="small" :type="w.status === 'generated' ? 'success' : 'warning'">
                    {{ w.status === 'generated' ? 'AI 解析已生成' : '解析待生成' }}
                  </el-tag>
                </span>
              </template>
              <p><b>我的答案：</b>{{ w.user_answer }}　<b>正确答案：</b>{{ w.correct_answer }}</p>
              <div v-if="w.status === 'generated'">
                <p><b>AI 解析：</b>{{ w.analysis }}</p>
                <p><b>错误原因：</b>{{ w.error_reason }}</p>
                <div v-if="w.variants?.length">
                  <b>变式题：</b>
                  <div v-for="(v, i) in w.variants" :key="i" style="margin: 6px 0 6px 12px">
                    <p>{{ i + 1 }}. {{ v.题干 }}</p>
                    <p style="color: #666; font-size: 13px">
                      答案：{{ v.答案 }}　解析：{{ v.解析 }}
                    </p>
                  </div>
                </div>
              </div>
              <el-button v-if="w.status !== 'generated'" size="small" type="primary"
                :loading="regeneratingId === w.id" @click="onRegenerate(w)">重新生成</el-button>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 导入历史成绩 -->
    <el-dialog v-model="importVisible" title="导入历史成绩" width="420px">
      <el-form label-width="80px">
        <el-form-item label="课程">
          <el-select v-model="importForm.course_id" placeholder="选择课程（试题来源）" style="width: 100%">
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="成绩">
          <el-input-number v-model="importForm.score" :min="0" :max="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="onImport">导入并初始化画像</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import {
  getDiagnostic, getPath, getPractice, getProfile, getSimilar, getTasks,
  importScore, listLearnCourses, listWrongbook, regenerateWrong, submitDiagnostic,
  submitPractice,
  type PathItem, type ProfileData, type Question, type PracticeResult,
  type SimilarStudent, type TaskItem, type WrongQuestionItem,
} from '@/api/learn'

const profile = ref<ProfileData | null>(null)
const path = ref<PathItem[]>([])
const tasks = ref<TaskItem[]>([])
const similar = ref<SimilarStudent[]>([])
const wrongbook = ref<WrongQuestionItem[]>([])
const activeTab = ref('dash')

// 学习方向（Plan G：三方向联动全部面板）
const learnCourses = ref<{ id: number; name: string }[]>([])
const currentCourseId = ref<number | null>(null)
const lastStem = ref('')

// 诊断测试
const diagnosing = ref(false)
const diagQuestions = ref<Question[]>([])
const diagAnswers = reactive<Record<string, string>>({})
const submittingDiag = ref(false)

// 导入
const importVisible = ref(false)
const courses = ref<{ id: number; name: string }[]>([])
const importForm = reactive({ course_id: undefined as number | undefined, score: 60 })
const importing = ref(false)

// 练习
const practiceKp = ref('')
const kpOptions = ref<string[]>([])
const currentQuestion = ref<Question | null>(null)
const selectedAnswer = ref('')
const result = ref<PracticeResult | null>(null)
const loadingQuestion = ref(false)
const submitting = ref(false)
const regeneratingId = ref(0)

// 雷达图（dataviz 参考盘：单系列蓝 #2a78d6、无图例、轴名二级墨色、tooltip 保留）
const radarEl = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null

function renderRadar() {
  if (!radarEl.value || !profile.value?.kps.length) return
  if (!radarChart) radarChart = echarts.init(radarEl.value)
  const kps = profile.value.kps
  radarChart.setOption({
    title: { text: '知识点掌握度', left: 'center', textStyle: { color: '#0b0b0b', fontSize: 14 } },
    tooltip: { trigger: 'item' },
    radar: {
      indicator: kps.map(k => ({ name: k.name, max: 100 })),
      radius: '65%',
      axisName: { color: '#52514e', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e1e0d9' } },
      splitArea: { areaStyle: { color: ['#fcfcfb', '#f4f3f0'] } },
      axisLine: { lineStyle: { color: '#e1e0d9' } },
    },
    series: [{
      type: 'radar',
      data: [{ value: kps.map(k => k.mastery), name: '掌握度' }],
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2, color: '#2a78d6' },
      itemStyle: { color: '#2a78d6' },
      areaStyle: { color: 'rgba(42, 120, 214, 0.15)' },
    }],
  })
}

async function loadDashboard() {
  profile.value = await getProfile(currentCourseId.value ?? undefined)
  if (!profile.value.initialized) return
  const [p, t, s] = await Promise.all([
    getPath(currentCourseId.value ?? undefined),
    getTasks(currentCourseId.value ?? undefined),
    getSimilar(),
  ])
  path.value = p.path
  tasks.value = t
  similar.value = s
  kpOptions.value = p.path.map(x => x.name).concat(
    profile.value.kps.filter(k => !p.path.some(x => x.name === k.name)).map(k => k.name),
  )
  if (!practiceKp.value) practiceKp.value = kpOptions.value[0] || ''
  renderRadar()
}

async function loadWrongbook() {
  wrongbook.value = await listWrongbook(currentCourseId.value ?? undefined)
}

async function startDiagnostic() {
  try {
    const data = await getDiagnostic(currentCourseId.value ?? undefined)
    diagQuestions.value = data.questions
    diagnosing.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '暂无可用试题，请先由教师在智能备课模块生成习题')
  }
}

async function onSwitchDirection() {
  // 切换方向重置全部面板状态（诊断/练习/结果/作答/雷达图），避免跨方向残留
  diagnosing.value = false
  diagQuestions.value = []
  Object.keys(diagAnswers).forEach(k => delete diagAnswers[k])
  currentQuestion.value = null
  result.value = null
  selectedAnswer.value = ''
  practiceKp.value = ''
  lastStem.value = ''
  // 销毁旧雷达图实例：切换后 tabs 重挂载会换新 div，旧实例绑在已卸载节点上，不销毁则新方向画像渲染空白
  radarChart?.dispose()
  radarChart = null
  await loadDashboard()
  await loadWrongbook()
}

function openImport() {
  importForm.course_id = currentCourseId.value ?? undefined
  importVisible.value = true
}

async function onSubmitDiagnostic() {
  const unanswered = diagQuestions.value.find(q => !diagAnswers[q.stem])
  if (unanswered) { ElMessage.warning('还有题目未作答'); return }
  submittingDiag.value = true
  try {
    const answers = diagQuestions.value.map(q => ({
      lesson_id: q.lesson_id, stem: q.stem, answer: diagAnswers[q.stem],
    }))
    await submitDiagnostic(answers)
    ElMessage.success('画像初始化完成')
    diagnosing.value = false
    diagQuestions.value = []
    await loadDashboard()
  } finally {
    submittingDiag.value = false
  }
}

async function onImport() {
  if (!importForm.course_id) { ElMessage.warning('请选择课程'); return }
  importing.value = true
  try {
    await importScore(importForm.course_id, importForm.score)
    ElMessage.success('画像初始化完成')
    importVisible.value = false
    await loadDashboard()
  } finally {
    importing.value = false
  }
}

function startTaskPractice(t: TaskItem) {
  practiceKp.value = t.name
  activeTab.value = 'practice'
  onNextQuestion()
}

async function onNextQuestion() {
  if (!practiceKp.value) { ElMessage.warning('请先选择知识点'); return }
  loadingQuestion.value = true
  result.value = null
  selectedAnswer.value = ''
  try {
    currentQuestion.value = await getPractice(
      practiceKp.value, currentCourseId.value ?? undefined, lastStem.value || undefined)
    if (currentQuestion.value) lastStem.value = currentQuestion.value.stem
  } catch (e) {
    currentQuestion.value = null
  } finally {
    loadingQuestion.value = false
  }
}

async function onSubmitAnswer() {
  if (!currentQuestion.value || !selectedAnswer.value) return
  submitting.value = true
  try {
    result.value = await submitPractice(
      currentQuestion.value.lesson_id, currentQuestion.value.stem, selectedAnswer.value)
    if (!result.value.correct) loadWrongbook()
  } finally {
    submitting.value = false
  }
}

async function onRegenerate(w: WrongQuestionItem) {
  regeneratingId.value = w.id
  try {
    const updated = await regenerateWrong(w.id)
    const idx = wrongbook.value.findIndex(x => x.id === w.id)
    if (idx >= 0) wrongbook.value[idx] = { ...wrongbook.value[idx], ...updated }
    ElMessage.success('AI 解析已重新生成')
  } finally {
    regeneratingId.value = 0
  }
}

onMounted(async () => {
  learnCourses.value = await listLearnCourses()
  courses.value = learnCourses.value
  if (learnCourses.value.length) {
    currentCourseId.value = learnCourses.value[0].id
    await loadDashboard()
    await loadWrongbook()
  }
})
watch(profile, renderRadar)
onBeforeUnmount(() => { radarChart?.dispose(); radarChart = null })
</script>

<style scoped>
.direction-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.direction-label { font-size: 14px; font-weight: 600; color: var(--text-1); }
</style>
