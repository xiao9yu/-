<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <div class="page-head">
      <div>
        <h2>智能备课 · 我的课程</h2>
        <div class="sub">上传校本资源，AI 生成教案 / 课件大纲 / 习题 / 试卷</div>
      </div>
      <el-button type="primary" @click="dialogVisible = true">
        <el-icon class="btn-ico"><Plus /></el-icon>新建课程
      </el-button>
    </div>

    <el-row :gutter="16">
      <el-col v-for="c in courses" :key="c.id" :xs="24" :sm="12" :md="8" style="margin-bottom: 16px">
        <el-card shadow="never" class="course-card liftable" @click="$router.push(`/prep/course/${c.id}`)">
          <div class="course-top">
            <div class="course-icon"><el-icon :size="20"><Notebook /></el-icon></div>
            <el-icon class="course-go"><ArrowRight /></el-icon>
          </div>
          <h3 class="course-name">{{ c.name }}</h3>
          <div class="course-meta">
            <el-tag size="small" effect="plain">{{ c.subject || '未分类' }}</el-tag>
          </div>
          <p class="course-desc">{{ c.description || '暂无描述，点击进入课程开始备课' }}</p>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!courses.length" description="还没有课程，点击右上角新建" />

    <el-dialog v-model="dialogVisible" title="新建课程" width="440px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="课程名"><el-input v-model="form.name" placeholder="如：人工智能导论" /></el-form-item>
        <el-form-item label="学科"><el-input v-model="form.subject" placeholder="人工智能" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowRight, Notebook, Plus } from '@element-plus/icons-vue'
import { createCourse, listCourses, type Course } from '@/api/prep'

const courses = ref<Course[]>([])
const dialogVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', subject: '人工智能', description: '' })

async function load() {
  courses.value = (await listCourses()) as Course[]
}

async function onCreate() {
  if (!form.name) { ElMessage.warning('请填写课程名'); return }
  creating.value = true
  try {
    await createCourse(form)
    dialogVisible.value = false
    form.name = ''; form.description = ''
    await load()
  } finally { creating.value = false }
}

onMounted(load)
</script>

<style scoped>
.btn-ico { margin-right: 5px; }

.course-card { cursor: pointer; height: 100%; }
.course-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.course-icon {
  width: 42px; height: 42px;
  border-radius: 11px;
  background: #eef0fb;
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
}
.course-go { color: var(--text-3); transition: all 0.15s ease; }
.course-card:hover .course-go { color: var(--accent); transform: translateX(3px); }

.course-name {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.course-desc {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--text-2);
  line-height: 1.7;
  min-height: 44px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
