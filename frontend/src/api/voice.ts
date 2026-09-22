// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
import http from './http'
import { useAuthStore } from '@/stores/auth'
import type { VoiceMark } from '@/utils/lipsync'
import type { KbCitation } from './kb'

export type VoiceState = 'ready' | 'transcribing' | 'thinking' | 'listening' | 'cancelled'

export type VoiceEvent =
  | { type: 'status'; state: VoiceState }
  | { type: 'transcript'; text: string }
  | { type: 'partial'; text: string }
  | { type: 'session'; id: number; turns: number }
  | { type: 'citations'; items: KbCitation[] }
  | { type: 'delta'; text: string }
  | { type: 'audio'; seq: number; marks: VoiceMark[]; data: string }
  | { type: 'done'; audio_total: number }
  | { type: 'segment_done'; audio_total: number }
  | { type: 'error'; message: string }

export interface VoiceHandlers {
  onEvent: (e: VoiceEvent) => void
  onClose: (reason: string) => void
}

export interface VoiceCapabilities {
  stream: boolean
  push_to_talk: boolean
  tts: boolean
}

/** 语音能力探测：stream=false 时前端不展示"自然对话"模式（模型未预热/不可用）。 */
export const voiceCapabilities = () =>
  http.get('/voice/capabilities') as Promise<VoiceCapabilities>

/** 打字朗读：整段文本合成 mp3；TTS 不可用（502/网络失败）返回 null（前端静默降级）。 */
export async function speakText(text: string): Promise<Blob | null> {
  try {
    const resp = await http.post('/voice/tts', { text }, { responseType: 'blob' })
    return resp as unknown as Blob
  } catch {
    return null
  }
}

/** 打字朗读（带口型时间轴）：返回 mp3 blob 与音节级 marks；失败返回 null 静默降级。 */
export async function speakTextTimed(
  text: string,
): Promise<{ blob: Blob; marks: VoiceMark[] } | null> {
  try {
    const resp = (await http.post('/voice/tts/timed', { text })) as unknown as {
      audio: string
      marks: VoiceMark[]
    }
    const bin = atob(resp.audio)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    return { blob: new Blob([bytes], { type: 'audio/mpeg' }), marks: resp.marks || [] }
  } catch {
    return null
  }
}

/** WS 语音客户端：首消息 auth 鉴权（带 session_id 续接会话）；断线自动重连（最多 3 次）。 */
export class VoiceClient {
  private ws: WebSocket | null = null
  private retries = 0
  private closedByUser = false
  private handlers: VoiceHandlers | null = null
  private sessionId: number | null = null

  /** 已知会话 id：重连时随 auth 一起发，语音链路也能接上文字链路的上下文。 */
  setSession(id: number | null) {
    this.sessionId = id
  }

  connect(handlers: VoiceHandlers, sessionId: number | null = null) {
    this.handlers = handlers
    if (sessionId !== null) this.sessionId = sessionId
    this.closedByUser = false
    this.open()
  }

  private open() {
    const auth = useAuthStore()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${proto}://${window.location.host}/api/voice/chat`)
    this.ws.onopen = () => {
      this.retries = 0
      const msg: Record<string, unknown> = { type: 'auth', token: auth.token }
      if (this.sessionId !== null) msg.session_id = this.sessionId
      this.send(msg)
    }
    this.ws.onmessage = (ev) => {
      try {
        this.handlers?.onEvent(JSON.parse(ev.data))
      } catch {
        // 脏帧忽略
      }
    }
    this.ws.onclose = () => {
      if (this.closedByUser) return
      this.retries += 1
      if (this.retries > 3) {
        this.handlers?.onClose('语音连接断开，请刷新页面重试')
        return
      }
      this.handlers?.onClose('语音连接已断开，正在重连…')
      setTimeout(() => this.open(), 2000)
    }
  }

  get isOpen() { return this.ws?.readyState === WebSocket.OPEN }

  /** 按住说话：整个 WAV 一次性送出。 */
  sendAudio(wavBase64: string) { this.send({ type: 'audio', data: wavBase64 }) }

  /** 流式自然对话：开始监听 / 送一帧 PCM16 16k / 结束监听。 */
  streamStart() { this.send({ type: 'stream_start' }) }
  streamChunk(pcm16: ArrayBuffer) { this.send({ type: 'stream_chunk', data: toBase64(pcm16) }) }
  streamEnd() { this.send({ type: 'stream_end' }) }

  cancel() { this.send({ type: 'cancel' }) }

  /** 只中断本轮回答（自然对话里"抢话"），监听继续。 */
  interrupt() { this.send({ type: 'interrupt' }) }

  close() {
    this.closedByUser = true
    this.ws?.close()
  }

  private send(obj: unknown) {
    if (this.isOpen) this.ws!.send(JSON.stringify(obj))
  }
}

/** ArrayBuffer → base64（分块拼接，避免大数组展开爆栈）。 */
function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) {
    bin += String.fromCharCode(...bytes.subarray(i, i + step))
  }
  return btoa(bin)
}
