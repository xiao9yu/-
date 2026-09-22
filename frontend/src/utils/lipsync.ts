// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
// 口型时间轴：把 TTS 的词级时间边界转成"逐音节张口包络"，替代纯音量驱动。
//
// 为什么要换掉音量包络：音量只说明"有多响"，不说明"在发什么音"。旧实现下句读停顿、
// 环境噪底都会让嘴继续动，而一个字该张多大口完全看不出来。
// 现在的时间轴来源是 edge-tts 的 WordBoundary（offset/duration，100ns 单位）：
//   · 中文按词切分，一个词内按字符数均分时窗 → 得到**音节级**时间对齐；
//   · 每个音节在自己的时窗内走一个 sin 半波（张口 → 最大 → 闭口），即真实的
//     "一字一开合"节奏，而不是持续张着；
//   · 标点/空白音节张口度置 0 → 停顿处闭嘴，这是观感提升最明显的一处。
//
// 能力边界（诚实标注）：张口**幅度**仍是启发式（字符散列取 0.55~1.0 的稳定值 +
// 长词略宽），不是音素级视位（viseme）。做真视位需要拼音/音素词典把韵母映射到
// 口型分组（a/o/e 大开、i 扁、u/ü 圆小、b/p/m 闭唇），属下一步工作。

export interface VoiceMark {
  text: string
  t0: number
  t1: number
}

export interface MouthSegment {
  t0: number
  t1: number
  open: number
}

export interface MouthSchedule {
  duration: number
  segments: MouthSegment[]
  /** 音节数：调试与"是否真的拿到时间轴"的判据 */
  syllables: number
}

/** 纯标点（或空白）音节：这些时窗应当闭嘴。 */
const PUNCT_ONLY = /^[\s，。！？；、：·…—～,.!?;:'"“”‘’（）()《》〈〉【】[\]{}]+$/

const EMPTY: MouthSchedule = { duration: 0, segments: [], syllables: 0 }

/** 单音节张口峰值：字符散列 → [0.55, 1.0]，保证同一字每帧一致（否则口型会抖）。 */
function peakOf(ch: string): number {
  let h = 0
  for (let i = 0; i < ch.length; i++) h = (h * 31 + ch.charCodeAt(i)) & 0xffff
  return 0.55 + ((h % 1000) / 1000) * 0.45
}

/**
 * 词级 marks → 音节级张口时间轴；marks 为空返回空时间轴（调用方退回音量驱动）。
 * 单个词的时窗按其字符数均分，因此"梯度下降"这类两字词会得到两次开合而非一次长张。
 */
export function buildSchedule(marks: VoiceMark[] | undefined | null): MouthSchedule {
  if (!marks || !marks.length) return EMPTY
  const segments: MouthSegment[] = []
  let duration = 0
  for (const m of marks) {
    const t0 = Math.max(0, m.t0)
    const t1 = Math.max(t0 + 0.02, m.t1)
    duration = Math.max(duration, t1)
    const chars = Array.from(m.text || '').filter((c) => !/\s/.test(c))
    if (!chars.length) continue
    const span = (t1 - t0) / chars.length
    chars.forEach((ch, i) => {
      segments.push({
        t0: t0 + i * span,
        t1: t0 + (i + 1) * span,
        open: PUNCT_ONLY.test(ch) ? 0 : peakOf(ch),
      })
    })
  }
  if (!segments.length) return EMPTY
  segments.sort((a, b) => a.t0 - b.t0)
  return { duration, segments, syllables: segments.length }
}

/**
 * 播放进度游标式的包络查询：t 单调递增，用游标而非二分/线性扫描，
 * 每帧 O(1)（长回答有几百个音节，逐帧全扫会白烧 CPU）。
 */
export class MouthEnvelope {
  private i = 0

  constructor(private readonly schedule: MouthSchedule) {}

  get syllables(): number {
    return this.schedule.syllables
  }

  /** 返回该时刻的张口包络 0~1（音节的 sin 半波；间隙与标点处为 0）。 */
  at(t: number): number {
    const segs = this.schedule.segments
    if (!segs.length) return 0
    while (this.i < segs.length && t > segs[this.i].t1) this.i++
    while (this.i > 0 && t < segs[this.i].t0) this.i--
    const g = segs[this.i]
    if (!g || t < g.t0 || t > g.t1) return 0
    const u = (t - g.t0) / Math.max(1e-3, g.t1 - g.t0)
    return g.open * Math.sin(Math.PI * Math.min(1, Math.max(0, u)))
  }
}
