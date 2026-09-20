<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展) -->
<template>
  <div ref="canvasHost" class="avatar-canvas" />
</template>

<script setup lang="ts">
// Live2D 渲染器封装：加载官方样例模型 + 音量驱动口型 + 呼吸/待机（Pixi 与 Vue 响应式隔离）
import { onBeforeUnmount, onMounted, ref } from 'vue'
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

onMounted(async () => {
  app = new PIXI.Application({ resizeTo: canvasHost.value, backgroundAlpha: 0 })
  canvasHost.value!.appendChild(app.view as unknown as Node)
  try {
    model = await Live2DModel.from('/live2d/hiyori/hiyori.model3.json')
    // 适配面板：底部对齐、宽度自适应
    const scale = Math.min(app.screen.width / model.width, 1.2)
    model.scale.set(scale)
    model.x = (app.screen.width - model.width * scale) / 2
    model.y = app.screen.height - model.height * scale
    app.stage.addChild(model)
    mouthParam = findParam(model, /MouthOpen/i, 'ParamMouthOpenY')
    breathParam = findParam(model, /Breath/i, 'ParamBreath')
    try { model.motion('idle') } catch { /* 无 idle motion 时走手动呼吸 */ }
    rafId = requestAnimationFrame(tick)
  } catch (e) {
    console.error('Live2D 加载失败', e)
  }
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
  model?.destroy()
  app?.destroy(true)
})

defineExpose({ setMouth })
</script>

<style scoped>
.avatar-canvas { width: 100%; height: 100%; }
</style>
