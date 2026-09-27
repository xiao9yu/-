<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展) -->
<template>
  <div ref="canvasHost" class="avatar-canvas" />
</template>

<script setup lang="ts">
// Live2D 渲染器封装：加载官方样例模型 + 音量驱动口型 + 呼吸/待机（Pixi 与 Vue 响应式隔离）
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as PIXI from 'pixi.js'
// 用 cubism4 单版本子包（Hiyori 为 Cubism 4 模型）：模块级只要求 Live2DCubismCore，
// 避免主入口 index 导入即抛 "Could not find Cubism 2 runtime"（官方 2019 年起已停发 live2d.min.js）
import { Live2DModel } from 'pixi-live2d-display/cubism4'

// 插件默认从 window.PIXI 取 Ticker（ESM 下不存在）→ autoUpdate 时无 ticker 可用，
// 模型时间不推进（动作/表情冻结）。显式注册 v7 共享 Ticker（shared.autoStart=true，
// 自带 RAF 循环），并保证与 App 渲染器同为 v7 实例（vite alias 强制单实例）。
Live2DModel.registerTicker(PIXI.Ticker)

const canvasHost = ref<HTMLElement>()
let app: PIXI.Application | null = null
let model: Live2DModel | null = null
let mouthParam = ''
let breathParam = ''
let lastMouth = 0
let ro: ResizeObserver | null = null
let gestureTimer: number | undefined
let baseW = 0   // 模型原始尺寸（scale=1 时捕获，适配计算不受后续缩放影响）
let baseH = 0

// 随机小动作（头部张望/身体轻摆）：说话与待机都定时触发，让"表情"不只有眨眼和待机循环。
// 组名按模型设置归一化（首字母小写）；priority=1 打断当前待机，结束后自动恢复待机。
const GESTURE_GROUPS = ['flick', 'flickDown', 'flick@Body']
function scheduleGesture() {
  gestureTimer = window.setTimeout(() => {
    if (model) {
      const g = GESTURE_GROUPS[Math.floor(Math.random() * GESTURE_GROUPS.length)]
      try { model.motion(g, undefined, 1) } catch { /* 组不存在时忽略 */ }
    }
    scheduleGesture()
  }, 8000 + Math.random() * 6000)
}

// 取景参数：只取模型顶部 45%（头+肩）充满舞台——整体等比缩放会让人物只有舞台
// 1/3 宽（口型十几像素、看不清），顶部取景后头部约占舞台 7 成、口型清晰可辨；
// 底部超出部分由舞台 overflow:hidden 裁掉，形象不变。
const FRAME_FRACTION = 0.45
const SCALE_CAP = 2.0   // 放大上限，防极小舞台时纹理糊

/** 画布容器当前尺寸；flex 布局未结算时给兜底尺寸，避免 0 尺寸画布导致模型不可见。 */
function hostSize(): { w: number; h: number } {
  const el = canvasHost.value
  return { w: el?.clientWidth || 320, h: el?.clientHeight || 480 }
}

/** 顶部取景：以头部高度充满舞台为准缩放，水平居中，头顶留一点呼吸空间。 */
function fitModel() {
  if (!app || !model || !baseW || !baseH) return
  const { w, h } = hostSize()
  const scale = Math.min(h / (baseH * FRAME_FRACTION), SCALE_CAP)
  model.scale.set(scale)
  model.x = (w - baseW * scale) / 2
  model.y = h * 0.04
}

onMounted(async () => {
  await nextTick()  // 等 flex 布局结算后再量尺寸
  const { w, h } = hostSize()
  app = new PIXI.Application({ width: w, height: h, backgroundAlpha: 0, autoDensity: true,
    preserveDrawingBuffer: true })  // 保留帧缓冲：口型渲染验证（readPixels）与调试截帧需要
  const view = app.view as HTMLCanvasElement
  view.style.width = '100%'
  view.style.height = '100%'
  canvasHost.value!.appendChild(view)
  try {
    model = await Live2DModel.from('/live2d/hiyori/hiyori.model3.json')
    // pixi v7 下 renderer.plugins.interaction 返回 EventSystem（无 .on/.off，那是 v6
    // InteractionManager 的 API）：插件 _render 每帧调 registerInteraction → TypeError
    // → 渲染循环中断、模型画不出来。本项目不需要点击/焦点交互（口型由音量驱动），
    // 实例级覆写掉这两个钩子（unregisterInteraction 同样会被调用）。
    ;(model as any).registerInteraction = () => {}
    ;(model as any).unregisterInteraction = () => {}
    baseW = model.width
    baseH = model.height
    app.stage.addChild(model)
    mouthParam = findParam(model, /MouthOpen/i, 'ParamMouthOpenY')
    breathParam = findParam(model, /Breath/i, 'ParamBreath')
    try { model.motion('idle') } catch { /* 无 idle motion 时走手动呼吸 */ }
    fitModel()
    // 口型写入必须挂在 afterMotionUpdate：待机/手势 motion 每帧经 motionManager.update
    // 覆写口型参数后再构建绘制数据，RAF 里写参数（晚于绘制数据构建）永远进不了画面；
    // 该事件在 motionManager.update 之后、saveParameters/模型 update 之前触发，
    // 写入的值即为本帧绘制所用 → 音量驱动的口型真正对上画面。
    ;(model as any).internalModel?.on?.('afterMotionUpdate', onAfterMotion)
    scheduleGesture()
  } catch (e) {
    console.error('Live2D 加载失败', e)
  }
  // 面板尺寸变化（窗口缩放/布局调整）时重建渲染尺寸并重新适配模型
  ro = new ResizeObserver(() => {
    const { w: nw, h: nh } = hostSize()
    if (app && nw > 0 && nh > 0) {
      app.renderer.resize(nw, nh)
      fitModel()
    }
  })
  ro.observe(canvasHost.value!)
})

function findParam(m: Live2DModel, re: RegExp, fallback: string): string {
  // Cubism4 core 参数表是 _parameterIds（带下划线的私有字段）；parameters.ids 为其它
  // 版本/结构的兜底路径。头显无头实测确认 _parameterIds 为 29 个 "ParamXxx" 字符串。
  const core = (m as any).internalModel?.coreModel
  const names: string[] = core?._parameterIds ?? core?.parameters?.ids ?? []
  return names.find((n) => re.test(String(n))) ?? fallback
}

function setParam(core: any, id: string, v: number) {
  try {
    if (typeof core.setParamFloat === 'function') core.setParamFloat(id, v)
    else if (typeof core.setParameterValueById === 'function') core.setParameterValueById(id, v)
  } catch {
    // 参数不存在时忽略
  }
}

/** 音量 0~1 直驱口型（PlaybackManager 每帧回调：有时间轴时已是"音节包络 × 音量"的合成值，
 *  经 afterMotionUpdate 低通后写入参数）。 */
function setMouth(v: number) {
  lastMouth = Math.max(0, Math.min(1, v))
}

// ---------- 表情联动（参数级临时覆写） ----------
// 模型无表情文件（Hiyori 官方包 Expressions 为空），"表情"与口型共用同一写入点：
// afterMotionUpdate 在动作更新之后、绘制之前触发，覆写值即本帧绘制所用，因此可以用
// 参数目标值临时接管表情；释放时渐隐到 0 后**停止写入**，模型自带的眨眼/待机动作
// 立即恢复接管这些参数（持续写 0 会把眼睛钉死在闭眼上）。
// 参数按正则从模型实际参数名解析（findParam 兜底），模型缺该参数时静默跳过。
interface ExprEntry { param: string; current: number; target: number }
const EXPRESSIONS: Record<string, { re: RegExp; target: number }[]> = {
  happy: [                              // 高兴：笑眼（下眼睑上弯）
    { re: /EyeLSmile/i, target: 1 },
    { re: /EyeRSmile/i, target: 1 },
  ],
  think: [                              // 思考：眼珠向右上看
    { re: /EyeBallX/i, target: 0.55 },
    { re: /EyeBallY/i, target: 0.45 },
  ],
  surprise: [                           // 惊讶（打断时一闪）：睁大眼 + 脸颊泛红
    { re: /EyeLOpen/i, target: 1 },
    { re: /EyeROpen/i, target: 1 },
    // Hiyori 无眉部抬升参数（只有 BrowLForm/BrowRForm，语义不定），
    // 用 ParamCheek 脸红做惊讶的视觉主体——方向确定（1=红）且符合"被抢话"人设。
    { re: /Cheek/i, target: 1 },
  ],
}
const EXPR_APPLY_K = 0.25    // 表情上身：稍快，反应跟手
const EXPR_RELEASE_K = 0.12  // 表情释放：渐隐，回归自然动作不跳变

let exprName: string | null = null
let exprHoldTimer: number | undefined
const exprActive: ExprEntry[] = []

/** 读取模型参数当前值（新表情项以此为起点渐入，避免从 0 起跳把眼睛瞬闭再睁开）。 */
function paramValue(core: any, id: string): number {
  try {
    if (core && typeof core.getParameterValueById === 'function') {
      return Number(core.getParameterValueById(id)) || 0
    }
  } catch { /* 参数不存在时忽略 */ }
  return 0
}

/** 切换表情；holdMs>0 表示到时自动复位（如打断惊讶）。复位前忽略外部置空请求，
 *  避免"惊讶 → 服务端 listening 状态 → 立即置空"把表情一闪而过。 */
function setExpression(name: string | null, holdMs?: number) {
  if (name === exprName && name !== null) return
  if (name === null && exprHoldTimer !== undefined) return
  if (exprHoldTimer !== undefined) { clearTimeout(exprHoldTimer); exprHoldTimer = undefined }
  exprName = name
  const wants = new Map<string, number>()
  for (const spec of EXPRESSIONS[name || ''] || []) {
    const param = findParam(model as Live2DModel, spec.re, '')
    if (param) wants.set(param, spec.target)
  }
  // 不再需要的活跃参数 → 目标 0 渐隐释放；仍需要的 → 原地换目标；新参数 → 从当前值渐入
  const core = (model as any)?.internalModel?.coreModel
  for (const entry of exprActive) {
    const t = wants.get(entry.param)
    if (t !== undefined) { entry.target = t; wants.delete(entry.param) } else { entry.target = 0 }
  }
  for (const [param, target] of wants) {
    exprActive.push({ param, current: paramValue(core, param), target })
  }
  // 惊讶叠加一个低点头动作：参数覆写只有脸红/睁眼，配上动作反应才"肉眼可见"。
  // flickDown 与随机小动作同组名，priority=1 打断当前待机、结束后自动恢复。
  if (name === 'surprise') {
    try { model?.motion('flickDown', undefined, 1) } catch { /* 组不存在时忽略 */ }
  }
  if (name && holdMs) {
    exprHoldTimer = window.setTimeout(() => {
      exprHoldTimer = undefined
      setExpression(null)
    }, holdMs)
  }
}

/** 每帧（afterMotionUpdate，口型之后）推进表情覆写：渐入/渐隐，释放完毕即停止写入。 */
function applyExpression(core: any) {
  for (let i = exprActive.length - 1; i >= 0; i--) {
    const e = exprActive[i]
    const k = e.target === 0 ? EXPR_RELEASE_K : EXPR_APPLY_K
    e.current += (e.target - e.current) * k
    setParam(core, e.param, e.current)
    if (e.target === 0 && Math.abs(e.current) < 0.02) exprActive.splice(i, 1)
  }
}

/** 口型平滑状态：快开慢合低通，跟上语音节奏且无逐帧抖动。 */
let mouthSmooth = 0
let breathClock = 0

/** 每帧（afterMotionUpdate）写口型与呼吸。
 *  不再做帧间衰减：驱动方（PlaybackManager）每帧都给新值，停播时显式给 0；
 *  旧实现的 0.95 衰减是为"回调停更"兜底，保留它只会白白压掉 5% 张口幅度。 */
function onAfterMotion() {
  const core = (model as any)?.internalModel?.coreModel
  if (!core || !mouthParam) return
  // 快开慢合：开（目标更大）跟随快，合（目标更小）收得慢，贴近真实口部惯量
  const k = lastMouth > mouthSmooth ? 0.6 : 0.3
  mouthSmooth += (lastMouth - mouthSmooth) * k
  setParam(core, mouthParam, mouthSmooth)
  if (breathParam) {
    breathClock += 0.0167  // 帧累计时钟（正常 ticker 下等价实时；手动步进调试时可复现）
    setParam(core, breathParam, 0.5 + 0.5 * Math.sin(breathClock * 0.9))  // 呼吸 0~1
  }
  applyExpression(core)   // 表情覆写最后写入：不被本函数其它参数覆盖
}

/** 当前口型状态（调试探针：无头验证读参数值确认音量→口型链路）。 */
function getMouth() {
  const core = (model as any)?.internalModel?.coreModel
  let param: number | null = null
  try {
    if (core && mouthParam && typeof core.getParameterValueById === 'function') {
      param = core.getParameterValueById(mouthParam)
    }
  } catch { /* 参数不存在时忽略 */ }
  return {
    lastMouth, param, mouthParam,
    scale: model?.scale?.x ?? null, x: model?.x ?? null, y: model?.y ?? null,
    baseW, baseH, host: hostSize(),
  }
}

/** 当前表情状态（调试探针：确认哪些参数被解析命中、覆写推进到什么值）。 */
function getExpression() {
  return {
    name: exprName,
    hold: exprHoldTimer !== undefined,
    entries: exprActive.map((e) => ({ param: e.param, current: +e.current.toFixed(3), target: e.target })),
  }
}

onBeforeUnmount(() => {
  if (gestureTimer) clearTimeout(gestureTimer)
  try { (model as any)?.internalModel?.off?.('afterMotionUpdate', onAfterMotion) } catch { /* 忽略 */ }
  ro?.disconnect()
  model?.destroy()
  app?.destroy(true)
})

defineExpose({ setMouth, getMouth, setExpression, getExpression })
if (import.meta.env.DEV) {
  ;(window as any).__live2dMouth = getMouth
  ;(window as any).__live2dSetMouth = setMouth   // 调试探针：强制口型值做视觉验证
  ;(window as any).__live2dExpression = setExpression  // 调试探针：强制表情做视觉验证
  ;(window as any).__live2dExprState = getExpression
  // 冻结探针：停 ticker 后手动以 dt=0、固定 now 推进模型——动作/物理/眨眼/自然运动
  // 全部静止，仅 afterMotionUpdate 写的口型与呼吸变化 → 像素差即口型视觉证据
  ;(window as any).__live2dFreeze = () => {
    if (gestureTimer) clearTimeout(gestureTimer)
    app?.ticker?.stop()
  }
  ;(window as any).__live2dUnfreeze = () => {
    app?.ticker?.start()
    scheduleGesture()
  }
  ;(window as any).__live2dStep = (n: number = 1) => {
    for (let i = 0; i < n; i++) (model as any)?.internalModel?.update(0, 12345678)
    app?.render()
  }
  // 顶点级验证探针：闭口/开口对比顶点位置缓冲（渲染器每帧绘制的正是这份数据）
  ;(window as any).__live2dModel = () => model
}
</script>

<style scoped>
.avatar-canvas { width: 100%; height: 100%; }
</style>
