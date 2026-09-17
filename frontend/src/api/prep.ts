// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
import http from './http'

export interface Course { id: number; name: string; subject: string; description: string; owner_id: number; member_ids: number[] }
export interface Lesson { id: number; course_id: number; title: string; lesson_type: string; content_json: any; version: number }
export interface SearchHit { ref: string; score: number; excerpt: string; source: string; page: number | null }

export const createCourse = (data: Partial<Course>) => http.post('/prep/courses', data)
export const listCourses = () => http.get('/prep/courses')
export const getCourse = (id: number) => http.get(`/prep/courses/${id}`)
export const addCollaborator = (courseId: number, userId: number) =>
  http.post(`/prep/courses/${courseId}/collaborators`, { user_id: userId })
export const uploadResource = (courseId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post(`/prep/courses/${courseId}/resources`, form)
}
export const searchResources = (courseId: number, q: string, topK = 5) =>
  // bge-m3 冷启动首查需 30~60s，覆盖全局 30s 超时（终审修复）
  http.get(`/prep/courses/${courseId}/search`, { params: { q, top_k: topK }, timeout: 120000 }) as Promise<{ hits: SearchHit[] }>
export const generateContent = (courseId: number, data: any) =>
  http.post(`/prep/courses/${courseId}/generate`, data)
export const createLesson = (courseId: number, data: Partial<Lesson>) =>
  http.post(`/prep/courses/${courseId}/lessons`, data)
export const listCourseLessons = (courseId: number) =>
  http.get(`/prep/courses/${courseId}/lessons`)
export const getLesson = (id: number) => http.get(`/prep/lessons/${id}`)
export const updateLesson = (id: number, contentJson: any) =>
  http.put(`/prep/lessons/${id}`, { content_json: contentJson })
export const listVersions = (id: number) => http.get(`/prep/lessons/${id}/versions`)
export const restoreLesson = (id: number, version: number) =>
  http.post(`/prep/lessons/${id}/restore`, { version })
export const addLessonMedia = (lessonId: number, fileId: number) =>
  http.post(`/prep/lessons/${lessonId}/media`, { file_id: fileId })
export const uploadFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/files/upload', form) as Promise<{ id: number; filename: string }>
}
// 导出需 Authorization 头（后端仅支持 Bearer 认证），window.open 无法携带
// 请求头，故走 axios 以 blob 方式下载（偏离 brief 的 exportLessonUrl 直链方案，原因见上）。
export const exportLesson = (id: number, format: string) =>
  http.get(`/prep/lessons/${id}/export`, { params: { format }, responseType: 'blob' }) as Promise<Blob>

/** 教案类型中文名（列表展示用）。 */
export const LESSON_TYPE_LABELS: Record<string, string> = {
  plan: '教案', cw: '课件大纲', exercises: '习题集', case: '教学案例', exam: '月考试题',
}
