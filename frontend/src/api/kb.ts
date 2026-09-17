// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能助教任务(18)
import http from './http'
import { useAuthStore } from '@/stores/auth'

export interface KbDocument {
  id: number; title: string; scope: string; owner_id: number; status: string
  error: string; chunk_count: number; created_at: string
}
export interface KbCitation {
  ref_no: number; source: string; page: number | null; kind: string
  excerpt: string; text: string; image_path: string | null; chunk_id: string
}

export const listKbDocuments = () => http.get('/kb/documents') as Promise<KbDocument[]>

export const uploadKbDocument = (file: File, scope: string) => {
  const form = new FormData()
  form.append('file', file)
  form.append('scope', scope)
  return http.post('/kb/documents', form)
}

export const deleteKbDocument = (id: number) => http.delete(`/kb/documents/${id}`)

/** 知识块原图：接口需 Bearer 鉴权，img 标签无法带头，故 fetch 成 blob 再给 objectURL。 */
export const loadChunkImage = (chunkId: string) =>
  http.get(`/kb/chunks/${chunkId}/image`, { responseType: 'blob' }) as Promise<Blob>

/** 流式问答：axios 不支持流式，用 fetch 手动解析 SSE（citations → delta* → done / error）。 */
export async function askStream(
  question: string,
  onCitations: (citations: KbCitation[]) => void,
  onDelta: (text: string) => void,
): Promise<void> {
  const auth = useAuthStore()
  const resp = await fetch('/api/kb/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => null)
    throw new Error(err?.detail || '请求失败')
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = ''
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (!event) continue
      if (event === 'citations') onCitations(JSON.parse(data))
      else if (event === 'delta') onDelta(JSON.parse(data).text)
      else if (event === 'error') throw new Error(JSON.parse(data).message || '生成失败')
    }
  }
}
