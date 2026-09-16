// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { defineStore } from 'pinia'
import http from '@/api/http'

interface User { id: number; username: string; role: string; real_name: string }

// 容错读取 localStorage 中的 user：存储值可能被手动编辑、写入截断或来自旧 schema，
// 直接 JSON.parse 抛异常会导致 store 初始化失败；useAuthStore() 被路由守卫（router/index.ts）
// 与 axios 拦截器（http.ts）调用，一旦抛出整个应用无法启动。解析失败时回退 null。
function loadUserFromStorage(): User | null {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null') as User | null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: loadUserFromStorage()
  }),
  actions: {
    async login(username: string, password: string) {
      const data = await http.post('/auth/login', { username, password }) as any
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', this.token)
      localStorage.setItem('user', JSON.stringify(this.user))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }
})
