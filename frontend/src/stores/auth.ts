// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import { defineStore } from 'pinia'
import http from '@/api/http'

interface User { id: number; username: string; role: string; real_name: string }

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: JSON.parse(localStorage.getItem('user') || 'null') as User | null
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
