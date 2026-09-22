// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
// 会话接口：历史会话列表 / 单会话消息回放 / 删除。
import http from './http'
import type { KbCitation } from './kb'

export interface ChatSessionInfo {
  id: number
  title: string
  turns: number
  created_at: string
  updated_at: string
}

export interface ChatMessageInfo {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: KbCitation[]
  created_at: string
}

export const listChatSessions = () =>
  http.get('/chat/sessions') as Promise<ChatSessionInfo[]>

/** 消息回放：带每轮 citations，翻页/刷新后引用溯源不丢（"引用延续"）。 */
export const listChatMessages = (sessionId: number) =>
  http.get(`/chat/sessions/${sessionId}/messages`) as Promise<{
    id: number
    title: string
    messages: ChatMessageInfo[]
  }>

export const deleteChatSession = (sessionId: number) =>
  http.delete(`/chat/sessions/${sessionId}`)
