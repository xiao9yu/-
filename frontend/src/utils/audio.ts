// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
// 音频工具：WAV 编码（16k 单声道 PCM，供后端 FunASR）+ 播放器（音量驱动口型）

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

/** mp3 顺序播放器：AnalyserNode 取音量回调（驱动 Live2D 口型）；stop() 立即静音。 */
export class PlaybackManager {
  onVolume: ((v: number) => void) | null = null
  onEnd: (() => void) | null = null

  private ctx: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private queue: AudioBuffer[] = []
  private playing = false
  private stopped = false

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

  /** 入队一段 mp3 blob（解码后顺序播放；stop() 清空）。 */
  async enqueue(blob: Blob) {
    this.ensureContext()
    const buf = await this.ctx!.decodeAudioData(await blob.arrayBuffer())
    this.queue.push(buf)
    if (!this.playing) void this.playLoop()
  }

  get isPlaying() { return this.playing }

  stop() {
    this.stopped = true
    this.queue = []
    void this.ctx?.close()
    this.ctx = null
    this.analyser = null
    this.playing = false
    this.onVolume?.(0)
  }

  private async playLoop() {
    this.playing = true
    this.stopped = false
    const data = new Uint8Array(this.analyser!.fftSize)
    const tick = () => {
      if (!this.stopped && this.analyser) {
        this.analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
        }
        this.onVolume?.(Math.min(1, Math.sqrt(sum / data.length) * 4))
        requestAnimationFrame(tick)
      } else {
        this.onVolume?.(0)
      }
    }
    requestAnimationFrame(tick)
    while (this.queue.length && !this.stopped) {
      const buf = this.queue.shift()!
      await this.playBuffer(buf)
    }
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
