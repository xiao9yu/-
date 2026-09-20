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

const canvasHost = ref<HTMLElement>()
let app: PIXI.Application | null = null
let model: Live2DModel | null = null
let mouthParam = ''
let breathParam = ''
let lastMouth = 0
let rafId = 0
let ro: ResizeObserver | null = null
let baseW = 0   // 模型原始尺寸（scale=1 时捕获，适配计算不受后续缩放影响）
let baseH = 0

/** 画布容器当前尺寸；flex 布局未结算时给兜底尺寸，避免 0 尺寸画布导致模型不可见。 */
function hostSize(): { w: number; h: number } {
  const el = canvasHost.value
  return { w: el?.clientWidth || 320, h: el?.clientHeight || 480 }
}

/** 底部居中 + 等比缩放（面板较窄时以高度为准；cap 防窗口极大时模型糊）。 */
function fitModel() {
  if (!app || !model || !baseW || !baseH) return
  const { w, h } = hostSize()
  const scale = Math.min(w / baseW, h / baseH, 1.5)
  model.scale.set(scale)
  model.x = (w - baseW * scale) / 2
  model.y = h - baseH * scale
}

onMounted(async () => {
  await nextTick()  // 等 flex 布局结算后再量尺寸
  const { w, h } = hostSize()
  app = new PIXI.Application({ width: w, height: h, backgroundAlpha: 0, autoDensity: true })
  const view = app.view as HTMLCanvasElement
  view.style.width = '100%'
  view.style.height = '100%'
  canvasHost.value!.appendChild(view)
  try {
    model = await Live2DModel.from('/live2d/hiyori/hiyori.model3.json')
    baseW = model.width
    baseH = model.height
    app.stage.addChild(model)
    mouthParam = findParam(model, /MouthOpen/i, 'ParamMouthOpenY')
    breathParam = findParam(model, /Breath/i, 'ParamBreath')
    try { model.motion('idle') } catch { /* 无 idle motion 时走手动呼吸 */ }
    fitModel()
    rafId = requestAnimationFrame(tick)
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

function tick() {
  if (model && mouthParam) {
    const core = (model as any).internalModel?.coreModel
    setParam(core, mouthParam, lastMouth)
    if (breathParam) {
      const t = performance.now() / 1000
      setParam(core, breathParam, 0.5 + 0.5 * Math.sin(t * 0.9))  // 呼吸 0~1
    }
  }
  rafId = requestAnimationFrame(tick)
}

/** 音量 0~1 直驱口型（PlaybackManager.onVolume 每帧回调）。 */
function setMouth(v: number) {
  lastMouth = Math.max(0, Math.min(1, v))
}

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  ro?.disconnect()
  model?.destroy()
  app?.destroy(true)
})

defineExpose({ setMouth })
</script>

<style scoped>
.avatar-canvas { width: 100%; height: 100%; }
</style>
