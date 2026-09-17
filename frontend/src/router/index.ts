// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    { path: '/', component: () => import('@/views/HomeView.vue') },
    { path: '/prep', component: () => import('@/views/prep/PrepListView.vue') },
    { path: '/prep/course/:id', component: () => import('@/views/prep/PrepCourseView.vue') },
    { path: '/prep/lesson/:id', component: () => import('@/views/prep/PrepEditorView.vue') },
    { path: '/module/assistant', component: () => import('@/views/assistant/AssistantView.vue') },
    { path: '/module/:name', component: () => import('@/views/PlaceholderView.vue') }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
})

export default router
