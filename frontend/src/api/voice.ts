// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
import http from './http'
import { useAuthStore } from '@/stores/auth'
import type { KbCitation } from './kb'

export type VoiceEvent =
  | { type: 'status'; state: 'ready' | 'transcribing' | 'thinking' | 'cancelled' }
  | { type: 'transcript'; text: string }
  | { type: 'citations'; items: KbCitation[] }
  | { type: 'delta'; text: string }
  | { type: 'audio'; seq: number; data: string }
  | { type: 'done'; audio_total: number }
  | { type: 'error'; message: string }

export interface VoiceHandlers {
  onEvent: (e: VoiceEvent) => void
  onClose: (reason: string) => void
}

/** 打字朗读：整段文本合成 mp3；TTS 不可用（502/网络失败）返回 null（前端静默降级）。 */
export async function speakText(text: string): Promise<Blob | null> {
  try {
    const resp = await http.post('/voice/tts', { text }, { responseType: 'blob' })
    return resp as unknown as Blob
  } catch {
    return null
  }
}

/** WS 语音客户端：首消息 auth 鉴权；断线自动重连（最多 3 次）。 */
export class VoiceClient {
  private ws: WebSocket | null = null
  private retries = 0
  private closedByUser = false
  private handlers: VoiceHandlers | null = null

  connect(handlers: VoiceHandlers) {
    this.handlers = handlers
    this.closedByUser = false
    this.open()
  }

  private open() {
    const auth = useAuthStore()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${proto}://${window.location.host}/api/voice/chat`)
    this.ws.onopen = () => {
      this.retries = 0
      this.send({ type: 'auth', token: auth.token })
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

  sendAudio(wavBase64: string) { this.send({ type: 'audio', data: wavBase64 }) }

  cancel() { this.send({ type: 'cancel' }) }

  close() {
    this.closedByUser = true
    this.ws?.close()
  }

  private send(obj: unknown) {
    if (this.isOpen) this.ws!.send(JSON.stringify(obj))
  }
}
