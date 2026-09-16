// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
// 注意：不 import router（避免 http→router→stores/auth→http 循环依赖），401 直接整页跳转登录
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    ElMessage.error(err.response?.data?.detail || '请求失败')
    if (err.response?.status === 401) window.location.href = '/login'
    return Promise.reject(err)
  }
)

export default http
