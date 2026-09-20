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
  const names: string[] = (m as any).internalModel?.coreModel?.parameters?.ids ?? []
  return names.find((n) => re.test(n)) ?? fallback
}

function setParam(core: any, id: string, v: number) {
  try {
    if (typeof core.setParamFloat === 'function') core.setParamFloat(id, v)
    else if (typeof core.setParameterValueById === 'function') core.setParameterValueById(id, v)
  } catch {
    // 参数不存在时忽略
  }
}

/** 音量 0~1 直驱口型（PlaybackManager.onVolume 每帧回调，值经 afterMotionUpdate 低通后写入参数）。 */
function setMouth(v: number) {
  lastMouth = Math.max(0, Math.min(1, v))
}

/** 口型平滑状态：快开慢合低通，跟上语音节奏且无逐帧抖动。 */
let mouthSmooth = 0
let breathClock = 0

/** 每帧（afterMotionUpdate）写口型与呼吸：音量目标逐帧 0.95 衰减（回调停更自动闭口）。 */
function onAfterMotion() {
  const core = (model as any)?.internalModel?.coreModel
  if (!core || !mouthParam) return
  lastMouth *= 0.95
  const k = lastMouth > mouthSmooth ? 0.55 : 0.16
  mouthSmooth += (lastMouth - mouthSmooth) * k
  setParam(core, mouthParam, mouthSmooth)
  if (breathParam) {
    breathClock += 0.0167  // 帧累计时钟（正常 ticker 下等价实时；手动步进调试时可复现）
    setParam(core, breathParam, 0.5 + 0.5 * Math.sin(breathClock * 0.9))  // 呼吸 0~1
  }
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

onBeforeUnmount(() => {
  if (gestureTimer) clearTimeout(gestureTimer)
  try { (model as any)?.internalModel?.off?.('afterMotionUpdate', onAfterMotion) } catch { /* 忽略 */ }
  ro?.disconnect()
  model?.destroy()
  app?.destroy(true)
})

defineExpose({ setMouth, getMouth })
if (import.meta.env.DEV) {
  ;(window as any).__live2dMouth = getMouth
  ;(window as any).__live2dSetMouth = setMouth   // 调试探针：强制口型值做视觉验证
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
