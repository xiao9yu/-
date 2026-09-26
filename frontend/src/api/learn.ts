// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
import http from './http'

export interface KpMastery { kp_id: number; name: string; mastery: number }
export interface ProfileData { initialized: boolean; kps: KpMastery[]; created_at: string | null }
export interface PathItem { kp_id: number; name: string; mastery: number; order: number; why: string }
export interface Question { lesson_id: number; stem: string; options: string[]; knowledge_point: string; difficulty: string; source?: string }
export interface TaskItem { kp_id: number; name: string; mastery: number; why: string; question: Question }
export interface SimilarStudent { user_id: number; real_name: string; similarity: number; strengths: string[] }
export interface PracticeResult {
  correct: boolean; answer: string; analysis: string
  knowledge_point: string; difficulty_new: string
  wrong_question?: { id: number; status: string }
}
// 变式题由 DeepSeek 按中文键生成（题干/选项/答案/解析），与后端 learn_wrongbook 输出一致
export interface WrongVariant { 题干: string; 选项: string[]; 答案: string; 解析: string }
export interface WrongQuestionItem {
  id: number; stem: string; options: string[]; user_answer: string; correct_answer: string
  knowledge_point: string; difficulty: string; analysis: string; error_reason: string
  variants: WrongVariant[]; status: string; created_at: string
}

export const getProfile = (courseId?: number) =>
  http.get('/learn/profile', { params: { course_id: courseId } }) as Promise<ProfileData>
export const listLearnCourses = () =>
  http.get('/learn/courses') as Promise<{ id: number; name: string }[]>
export const getDiagnostic = (courseId?: number) =>
  http.get('/learn/diagnostic', { params: { course_id: courseId } }) as Promise<{ questions: Question[]; count: number }>
export const submitDiagnostic = (answers: { lesson_id: number; stem: string; answer: string }[]) =>
  http.post('/learn/diagnostic', { answers }) as Promise<{ initialized: boolean; kp_count: number }>
export const importScore = (courseId: number, score: number) =>
  http.post('/learn/import', { course_id: courseId, score }) as Promise<{ initialized: boolean; kp_count: number }>
export const getPath = (courseId?: number) =>
  http.get('/learn/path', { params: { course_id: courseId } }) as Promise<{ path: PathItem[]; mastered: number; unmastered: number }>
export const getTasks = (courseId?: number) =>
  http.get('/learn/tasks', { params: { course_id: courseId } }) as Promise<TaskItem[]>
export const getSimilar = () => http.get('/learn/similar') as Promise<SimilarStudent[]>
export const getPractice = (kp: string, courseId?: number, prevStem?: string) =>
  http.get('/learn/practice', { params: { kp, course_id: courseId, prev_stem: prevStem } }) as Promise<Question>
// 答错同步生成 AI 解析（DeepSeek 调用），覆盖全局 30s 超时
export const submitPractice = (lessonId: number, stem: string, answer: string) =>
  http.post('/learn/practice/submit', { lesson_id: lessonId, stem, answer },
    { timeout: 120000 }) as Promise<PracticeResult>
export const listWrongbook = (courseId?: number) =>
  http.get('/learn/wrongbook', { params: { course_id: courseId } }) as Promise<WrongQuestionItem[]>
export const regenerateWrong = (id: number) =>
  http.post(`/learn/wrongbook/${id}/regenerate`, undefined,
    { timeout: 120000 }) as Promise<WrongQuestionItem>
