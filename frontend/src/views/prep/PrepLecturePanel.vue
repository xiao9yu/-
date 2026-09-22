<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17扩展：课件数字人讲课) -->
<template>
  <div>
    <el-page-header class="page-header" @back="onClose">
      <template #content>
        <span class="lecture-title">
          <el-icon class="head-icon"><VideoPlay /></el-icon>
          {{ lessonTitle || '课件' }} · 数字人讲课
        </span>
      </template>
    </el-page-header>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="10">
        <div class="avatar-stage">
          <Live2DAvatar ref="avatarRef" />
          <div class="talk-bubble">
            <div class="subtitle">{{ currentScript }}</div>
          </div>
        </div>
      </el-col>
      <el-col :span="14">
        <div class="slide-preview">
          <div class="slide-tag">第 {{ pageIndex + 1 }} 页 · 共 {{ slides.length }} 页</div>
          <h2 class="slide-title">{{ currentSlide.标题 }}</h2>
          <ul class="slide-points">
            <li v-for="p in currentSlide.要点" :key="p">{{ p }}</li>
          </ul>
        </div>
      </el-col>
    </el-row>
    <el-alert v-if="hasLegacySlide" type="info" :closable="false" class="legacy-tip"
      title="该课件生成于讲课功能上线前，部分页面无讲稿，将朗读要点；重新生成可获得完整讲稿。" />
    <div class="control-bar">
      <el-button type="primary" :disabled="playing" @click="onPlay">
        <el-icon class="btn-ico"><VideoPlay /></el-icon>播放
      </el-button>
      <el-button :disabled="pageIndex === 0" @click="onPrev">
        <el-icon class="btn-ico"><ArrowLeft /></el-icon>上一页
      </el-button>
      <el-button :disabled="pageIndex >= slides.length - 1" @click="onNext">
        下一页<el-icon class="btn-ico2"><ArrowRight /></el-icon>
      </el-button>
      <el-button type="danger" plain @click="onStop">
        <el-icon class="btn-ico"><CloseBold /></el-icon>停止
      </el-button>
      <el-tooltip :content="muted ? '取消静音' : '静音'">
        <el-button circle @click="toggleMute">
          <el-icon><Mute v-if="muted" /><Microphone v-else /></el-icon>
        </el-button>
      </el-tooltip>
      <span class="page-ind">{{ pageIndex + 1 }} / {{ slides.length }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ArrowLeft, ArrowRight, CloseBold, Microphone, Mute, VideoPlay } from '@element-plus/icons-vue'
import { PlaybackManager } from '@/utils/audio'
import { speakTextTimed } from '@/api/voice'
import Live2DAvatar from '@/components/live2d/Live2DAvatar.vue'

interface LectureSlide {
  标题: string
  要点: string[]
  讲稿?: string
}

const props = defineProps<{
  slides: LectureSlide[]
  lessonTitle?: string
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const avatarRef = ref<InstanceType<typeof Live2DAvatar>>()
const pageIndex = ref(0)
const playing = ref(false)
const muted = ref(false)

/** 当前页朗读文本：优先讲稿；旧课件无讲稿时降级为要点拼接。 */
const currentScript = computed(() => scriptOf(props.slides[pageIndex.value]))
const currentSlide = computed<LectureSlide>(
  () => props.slides[pageIndex.value] || { 标题: '', 要点: [] },
)
/** 是否存在无讲稿页（旧课件）：一次性提示重新生成。 */
const hasLegacySlide = computed(() => props.slides.some((s) => !(s.讲稿 || '').trim()))

function scriptOf(slide: LectureSlide | undefined): string {
  if (!slide) return ''
  return (slide.讲稿 || '').trim() || (slide.要点 || []).join('，')
}

// 播放器：口型驱动朵娅；队列播完（onEnd）自动进入下一页
const player = new PlaybackManager()
player.onMouth = (v) => avatarRef.value?.setMouth(v)

/** 播放代次：手动翻页/停止/静音后作废未完成的合成与定时器回调。 */
let seq = 0

player.onEnd = () => {
  if (!playing.value) return
  if (pageIndex.value < props.slides.length - 1) {
    pageIndex.value += 1
    void playCurrent()
  } else {
    playing.value = false  // 末页播完自动停止
  }
}

async function playCurrent() {
  const my = ++seq
  const text = currentScript.value
  if (!text || muted.value) return
  const timed = await speakTextTimed(text)
  if (my !== seq) return  // 期间被手动翻页/停止/静音
  if (!timed) {
    fallbackAdvance(my)   // TTS 不可用：字幕仍显示，短暂停留后继续（讲课不中断）
    return
  }
  try {
    playing.value = true
    await player.enqueue(timed.blob, timed.marks)
  } catch {
    fallbackAdvance(my)   // 解码失败等同 TTS 不可用
  }
}

/** 无音频路径的翻页：字幕停留 1.5s 后进入下一页/结束。 */
function fallbackAdvance(my: number) {
  playing.value = true
  setTimeout(() => { if (my === seq && playing.value) advanceOrStop() }, 1500)
}

function advanceOrStop() {
  if (pageIndex.value < props.slides.length - 1) {
    pageIndex.value += 1
    void playCurrent()
  } else {
    playing.value = false
  }
}

function onPlay() {
  // 播放按钮是用户手势：在回调内同步创建/恢复 AudioContext（Chrome 自动播放策略，
  // 手势激活过期后再创建会被静音——表现为"数字人不讲话"且口型不动）。
  player.ensureContext()
  if (!playing.value && pageIndex.value >= props.slides.length - 1) pageIndex.value = 0
  void playCurrent()
}

function onPrev() {
  if (pageIndex.value === 0) return
  player.stop()
  seq += 1
  playing.value = false
  pageIndex.value -= 1
}

function onNext() {
  if (pageIndex.value >= props.slides.length - 1) return
  player.stop()
  seq += 1
  playing.value = false
  pageIndex.value += 1
}

function onStop() {
  player.stop()
  seq += 1
  playing.value = false
  pageIndex.value = 0
}

/** 静音 = 停口型不停字幕：掐断当前朗读，字幕保留。 */
function toggleMute() {
  muted.value = !muted.value
  if (muted.value && playing.value) {
    player.stop()
    seq += 1
    playing.value = false
  }
}

function onClose() {
  player.stop()
  seq += 1
  playing.value = false
  emit('close')
}

onBeforeUnmount(() => {
  player.stop()
  seq += 1
})
</script>

<style scoped>
.page-header { margin-bottom: 2px; }
.lecture-title { display: inline-flex; align-items: center; }
.head-icon { margin-right: 7px; color: var(--accent); }
.btn-ico { margin-right: 5px; }
.btn-ico2 { margin-left: 5px; }

/* 数字人形象区：固定高度舞台（讲课页不随窗口拉伸，固定取景更稳） */
.avatar-stage {
  position: relative;
  height: 560px;
  background: radial-gradient(ellipse at 50% 38%, #eef0fb 0%, #f7f8fc 58%, #f2f3f9 100%);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

/* 讲稿字幕气泡：覆盖在舞台下半部（人物脸部在上半部不被遮挡），尾巴朝上指向人物 */
.talk-bubble {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  width: min(62%, 540px);
  max-height: 42%;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px 14px;
  box-shadow: var(--shadow-sm);
  overflow-y: auto;
  z-index: 2;
}
.talk-bubble::before {
  content: ''; position: absolute; left: 50%; top: -9px; transform: translateX(-50%);
  border: 9px solid transparent; border-bottom-color: #fff;
}
.subtitle { font-size: 13.5px; line-height: 1.7; color: var(--text-1); word-break: break-word; }

/* 右侧课件页预览 */
.slide-preview {
  height: 560px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px 32px;
  overflow-y: auto;
}
.slide-tag { font-size: 12px; color: var(--text-3); }
.slide-title { margin: 10px 0 18px; font-size: 22px; color: var(--text-1); }
.slide-points { margin: 0; padding-left: 20px; }
.slide-points li { font-size: 14px; line-height: 2.1; color: var(--text-1); }

.legacy-tip { margin-top: 16px; }

/* 底部控制条 */
.control-bar {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.page-ind { margin-left: auto; font-size: 13px; color: var(--text-2); }
</style>
