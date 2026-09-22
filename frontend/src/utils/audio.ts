// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
// 音频工具：WAV 编码（16k 单声道 PCM，供后端 FunASR）+ 播放器（口型时间轴驱动）
//           + 麦克风 PCM 流（流式自然对话，送服务端 FSMN-VAD 端点检测）

import { buildSchedule, MouthEnvelope, type MouthSchedule, type VoiceMark } from './lipsync'

/** AudioBuffer → 16 位 PCM WAV（单声道，采样率不变；调用方先经 decodeTo16k 重采样）。 */
export function wavEncode(buffer: AudioBuffer): ArrayBuffer {
  const numCh = 1
  const rate = buffer.sampleRate
  const data = buffer.getChannelData(0)
  const blockAlign = numCh * 2
  const buf = new ArrayBuffer(44 + data.length * blockAlign)
  const view = new DataView(buf)
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + data.length * blockAlign, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, numCh, true)
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeStr(36, 'data')
  view.setUint32(40, data.length * blockAlign, true)
  let off = 44
  for (let i = 0; i < data.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, data[i]))
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return buf
}

/** webm/opus Blob → 16k 单声道 AudioBuffer（decodeAudioData + OfflineAudioContext 重采样，零后端 ffmpeg）。 */
export async function decodeTo16k(blob: Blob): Promise<AudioBuffer> {
  const arrayBuf = await blob.arrayBuffer()
  const ctx = new AudioContext()
  try {
    const decoded = await ctx.decodeAudioData(arrayBuf)
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000)
    const src = offline.createBufferSource()
    src.buffer = decoded
    src.connect(offline.destination)
    src.start()
    return await offline.startRendering()
  } finally {
    void ctx.close()
  }
}

/** ArrayBuffer → base64（分块拼接避免大数组展开爆栈）。 */
export function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let bin = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) {
    bin += String.fromCharCode(...bytes.subarray(i, i + step))
  }
  return btoa(bin)
}

/** mp3 顺序播放器：口型由"时间轴包络 × 实时音量"驱动；stop() 立即静音。 */
export class PlaybackManager {
  /** 原始音量 0~1（AnalyserNode RMS，调试与降级用） */
  onVolume: ((v: number) => void) | null = null
  /** 最终口型开合 0~1：有时间轴时 = 音节包络 × 音量门限，无时间轴时 = 音量 */
  onMouth: ((v: number) => void) | null = null
  onEnd: (() => void) | null = null

  private ctx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private queue: { buf: AudioBuffer; env: MouthEnvelope | null }[] = []
  private playing = false
  private stopped = false
  private amp = 0                 // 当前帧音量（RAF 循环刷新）
  private env: MouthEnvelope | null = null
  private startedAt = 0           // 当前 buffer 的起播时钟（ctx.currentTime 基准）

  /** 用户手势后调用一次（按住说话/发送/开关切换均满足 Chrome 自动播放策略）。 */
  ensureContext() {
    if (!this.ctx) {
      this.ctx = new AudioContext()
      this.analyser = this.ctx.createAnalyser()
      this.analyser.fftSize = 512
      this.analyser.connect(this.ctx.destination)
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume()
  }

  /** 入队一段 mp3（可选口型时间轴 marks：后端 edge-tts WordBoundary 产出）。 */
  async enqueue(blob: Blob, marks?: VoiceMark[]) {
    this.ensureContext()
    const buf = await this.ctx!.decodeAudioData(await blob.arrayBuffer())
    const schedule: MouthSchedule = buildSchedule(marks)
    this.queue.push({ buf, env: schedule.syllables ? new MouthEnvelope(schedule) : null })
    if (!this.playing) void this.playLoop()
  }

  get isPlaying() { return this.playing }

  /** 当前是否在按时间轴驱动（探针：验证 marks 是否真的到位）。 */
  get hasSchedule() { return this.env !== null }

  stop() {
    this.stopped = true
    this.queue = []
    void this.ctx?.close()
    this.ctx = null
    this.analyser = null
    this.playing = false
    this.env = null
    this.amp = 0
    this.onMouth?.(0)
  }

  private async playLoop() {
    this.playing = true
    this.stopped = false
    const data = new Uint8Array(this.analyser!.fftSize)
    const tick = () => {
      if (this.stopped || !this.analyser) {
        this.onMouth?.(0)
        return
      }
      this.analyser.getByteTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128
        sum += v * v
      }
      this.amp = Math.min(1, Math.sqrt(sum / data.length) * 4)
      this.onVolume?.(this.amp)
      if (this.env && this.ctx) {
        // 音量门限：包络决定"何时张口、张多大"，音量决定"这一刻是否真在出声"，
        // 两者相乘 → 时间轴错位或静音段都不会出现凭空张合的嘴。
        const gate = Math.min(1, this.amp * 3)
        this.onMouth?.(this.env.at(this.ctx.currentTime - this.startedAt) * (0.35 + 0.65 * gate))
      } else {
        this.onMouth?.(this.amp)
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    while (this.queue.length && !this.stopped) {
      const item = this.queue.shift()!
      this.env = item.env
      this.startedAt = this.ctx!.currentTime
      await this.playBuffer(item.buf)
    }
    this.env = null
    this.playing = false
    if (!this.stopped) this.onEnd?.()
  }

  private playBuffer(buf: AudioBuffer) {
    return new Promise<void>((resolve) => {
      const ctx = this.ctx!
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(this.analyser!)
      src.onended = () => resolve()
      src.start()
    })
  }
}

/**
 * 线性插值重采样器（源采样率 → 16k），支持跨块连续：麦克风每个回调整体长度不定，
 * 跨块保留残余采样点与小数相位，避免每块独立重采样引入的咔哒声与累计漂移。
 * 即便 AudioContext 已按 16k 创建（ratio=1 时退化为直通），也保留通用实现——
 * 部分浏览器会忽略 sampleRate 选项，届时仍能输出正确的 16k 数据。
 */
class Resampler {
  private rest = new Float32Array(0)
  private pos = 0

  constructor(private readonly srcRate: number) {}

  push(input: Float32Array): Int16Array {
    const merged = new Float32Array(this.rest.length + input.length)
    merged.set(this.rest, 0)
    merged.set(input, this.rest.length)
    const ratio = this.srcRate / 16000
    const out: number[] = []
    while (this.pos + 1 < merged.length) {
      const i = Math.floor(this.pos)
      const frac = this.pos - i
      out.push(merged[i] * (1 - frac) + merged[i + 1] * frac)
      this.pos += ratio
    }
    const consumed = Math.min(Math.floor(this.pos), Math.max(0, merged.length - 1))
    this.rest = merged.slice(consumed)
    this.pos -= consumed
    if (out.length === 0) return new Int16Array(0)
    const pcm = new Int16Array(out.length)
    for (let i = 0; i < out.length; i++) {
      const s = Math.max(-1, Math.min(1, out[i]))
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    return pcm
  }
}

/**
 * 麦克风 → 16k PCM16 帧流（流式自然对话用）。
 * 刻意不在前端做 VAD：端点判定交给服务端 FSMN-VAD（训练模型，抗噪与轻声起头都更稳），
 * 前端只负责"持续送干净数据"，客户端不再引入一个阈值参数需要调。
 */
export class PcmStreamer {
  onFrame: ((pcm16: ArrayBuffer) => void) | null = null
  sampleRate = 0

  private ctx: AudioContext | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private node: ScriptProcessorNode | null = null
  private resampler: Resampler | null = null

  constructor(private readonly stream: MediaStream) {}

  start() {
    // 优先请求 16k（Chrome 支持）；不支持时由 Resampler 兜住
    this.ctx = new AudioContext({ sampleRate: 16000 })
    this.sampleRate = this.ctx.sampleRate
    this.resampler = new Resampler(this.ctx.sampleRate)
    this.source = this.ctx.createMediaStreamSource(this.stream)
    // ScriptProcessorNode 已标记废弃但仍是全平台可用且无需额外资源的方案；
    // AudioWorklet 需要单独模块文件与加载时序，演示规模下收益不足以抵复杂度。
    this.node = this.ctx.createScriptProcessor(2048, 1, 1)
    this.node.onaudioprocess = (e) => {
      if (!this.onFrame || !this.resampler) return
      const pcm = this.resampler.push(e.inputBuffer.getChannelData(0).slice())
      if (pcm.length) this.onFrame(pcm.buffer as ArrayBuffer)
    }
    this.source.connect(this.node)
    this.node.connect(this.ctx.destination)   // 需连到 destination 才会被驱动
  }

  stop() {
    this.onFrame = null
    try { this.node?.disconnect() } catch { /* 已断开 */ }
    try { this.source?.disconnect() } catch { /* 已断开 */ }
    void this.ctx?.close()
    this.ctx = null
    this.node = null
    this.source = null
    this.resampler = null
  }
}
