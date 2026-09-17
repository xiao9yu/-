<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>智能备课 · 我的课程</h2>
      <el-button type="primary" @click="dialogVisible = true">新建课程</el-button>
    </div>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col v-for="c in courses" :key="c.id" :span="8">
        <el-card @click="$router.push(`/prep/course/${c.id}`)" style="cursor: pointer; margin-bottom: 16px">
          <h3>{{ c.name }}</h3>
          <p style="color: #666">{{ c.subject }} · {{ c.description || '暂无描述' }}</p>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!courses.length" description="还没有课程，点击右上角新建" />

    <el-dialog v-model="dialogVisible" title="新建课程" width="420px">
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
