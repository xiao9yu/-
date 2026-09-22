# 课件数字人讲课模式（Plan F）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让教师把生成的课件交给数字人朵娅逐页讲出来，并把讲稿带进导出的 PPT 备注栏。

**Architecture:** 讲稿作为可选键存进课件 `content_json`（`幻灯片[].讲稿`），生成课件时由 LLM 顺带产出；导出 PPTX 时写进每页备注；前端在备课编辑页新增讲课面板，复用智能助教的 Live2D + TTS 时间轴 + 播放器链路逐页朗读、自动翻页。旧课件无讲稿自动降级朗读要点。

**Tech Stack:** FastAPI + python-pptx（备注走 notesSlide 惰性创建）；Vue3 + Element Plus + pixi-live2d-display；edge-tts（`speakTextTimed`，含 WordBoundary 口型时间轴）。

## Global Constraints

- 提交身份 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local"`，只在 master；**绝不 `git add -A`**（显式路径）；提交信息末尾附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- pytest 从 backend/ 跑：`cd backend && python -m pytest tests/ -q`。**不要传 `--basetemp`**；本机批量删除防护会拦截 pytest 收尾清理，**退出码不可信**，判读结果看逐用例输出（如 `grep -c PASSED`）。
- 前端验证：`cd frontend && npm run build` + `npx tsc --noEmit`（tsc 0 错误）；前端无单测基建，TDD 不适用。
- `frontend/vite.config.ts` 的本机 8001 代理补丁保持**未提交**，任何任务不得 git add 该文件。
- UI 文案中文、El 图标禁 emoji；设计 token（`var(--surface)`/`var(--border)`/`var(--text-1)`/`var(--text-2)`/`var(--text-3)`/`var(--accent)`/`var(--shadow-sm)` 等，见 main.css）沿用现有体系。
- 子代理不指定 model（Anthropic 402 余额问题）；**Task 3/4 前端按用户 2026-09-22 裁定由控制器直接实现**，不派前端子代理。
- 课件结构契约：`content_json = {标题, 幻灯片[{标题, 要点[], 讲稿?}]}`；**讲稿为可选键**——旧课件无讲稿必须兼容（讲课降级朗读要点、导出不写备注）。
- 全量基线 291 passed, 2 deselected 不得回退；每任务收尾跑全量。

---

### Task 1: 课件生成——讲稿字段（提示词 + 校验）

**Files:**
- Modify: `backend/app/services/prep_generator.py`（`_COURSEWARE_PROMPT` 与 `validate_courseware`）
- Test: `backend/tests/test_prep_generator.py`（COURSEWARE 夹具补讲稿 + 2 个新测试）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces: `validate_courseware(data)` 现在要求每页含非空字符串 `讲稿`，缺失或空白抛 `BizError(502, "生成结果缺少讲稿，请重试")`；`generate_courseware(...)` 的 prompt 要求 LLM 每页输出讲稿。**API 层（`app/api/prep.py` 生成端点）已调用此校验，无需改动即自动生效。**

- [ ] **Step 1: 更新 COURSEWARE 夹具 + 写失败测试**

在 `backend/tests/test_prep_generator.py` 中把 COURSEWARE 夹具（第 29~35 行）替换为：

```python
COURSEWARE = {
    "标题": "机器学习基础课件",
    "幻灯片": [
        {"标题": "梯度下降", "要点": ["沿负梯度方向迭代", "学习率控制步长"],
         "讲稿": "同学们好，今天我们来学习梯度下降。它的核心思想是沿负梯度方向一步步迭代，让损失函数不断下降。"},
        {"标题": "线性回归", "要点": ["拟合直线", "房价预测"],
         "讲稿": "接下来看线性回归。我们用一条直线拟合数据，最典型的应用就是房价预测。"},
    ],
}
```

文件末尾追加两个测试：

```python
COURSEWARE_NO_SCRIPT = {
    "标题": "机器学习基础课件",
    "幻灯片": [{"标题": "梯度下降", "要点": ["沿负梯度方向迭代"]}],
}


def test_validate_courseware_requires_script_per_slide():
    """每页必须含非空讲稿：缺失或纯空白均 502；齐全则通过。"""
    with pytest.raises(BizError):
        validate_courseware(COURSEWARE_NO_SCRIPT)
    with pytest.raises(BizError):
        validate_courseware({"标题": "课件", "幻灯片": [{"标题": "梯度下降", "要点": [], "讲稿": "   "}]})
    validate_courseware(COURSEWARE)  # 每页含讲稿 → 通过


def test_generate_courseware_prompt_asks_for_script():
    llm = FakeLLM(COURSEWARE)
    generate_courseware("人工智能导论", "人工智能", "第3章", "目标", "2课时", llm=llm)
    prompt_text = llm.calls[0]["messages"][-1]["content"]
    assert "讲稿" in prompt_text
    assert "口语化" in prompt_text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_generator.py -q`
Expected: 两个新测试 FAILED——`test_validate_courseware_requires_script_per_slide` 因 COURSEWARE_NO_SCRIPT 缺讲稿却未抛 BizError（DID NOT RAISE）；`test_generate_courseware_prompt_asks_for_script` 因 prompt 无"讲稿"/"口语化"字样。既有测试（含 `test_validators_accept_valid_and_reject_missing_keys`）仍 PASS（夹具已补讲稿，旧校验不查讲稿也能过）。

- [ ] **Step 3: 改提示词与校验**

`backend/app/services/prep_generator.py`，替换 `_COURSEWARE_PROMPT`（第 17~24 行）：

```python
_COURSEWARE_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成课件大纲。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n课时：{hours}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题（字符串）、幻灯片（列表，每项含 标题/要点（字符串列表）/"
    "讲稿（字符串，该页的口语化串讲：面向学生讲课的口吻，每页 2~4 句，开场页可含欢迎语，"
    "不照念要点原文，不用 markdown 与引用编号），10~15 页）。不要输出其他内容。"
)
```

替换 `validate_courseware`（第 137~140 行）：

```python
def validate_courseware(data: dict) -> None:
    _require_keys(data, ["标题", "幻灯片"])
    if not isinstance(data["幻灯片"], list) or not data["幻灯片"]:
        raise BizError(502, "生成结果缺少幻灯片内容，请重试")
    for slide in data["幻灯片"]:
        _require_keys(slide, ["标题", "要点", "讲稿"])
        if not isinstance(slide["讲稿"], str) or not slide["讲稿"].strip():
            raise BizError(502, "生成结果缺少讲稿，请重试")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_generator.py -q`
Expected: 全部 PASS（含既有测试——`test_generate_courseware_and_exam` 与 `test_validators_accept_valid_and_reject_missing_keys` 用的夹具已补讲稿）。

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest tests/ -q`
Expected: 293 passed（291 + 2 新增）, 2 deselected；输出无既有用例失败。

```bash
git add backend/app/services/prep_generator.py backend/tests/test_prep_generator.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 课件生成增加每页讲稿字段（提示词+校验）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 课件导出——讲稿写入 PPT 备注栏

**Files:**
- Modify: `backend/app/services/prep_export.py`（`export_courseware_pptx`）
- Test: `backend/tests/test_prep_export.py`（COURSEWARE 夹具补讲稿 + 2 个新测试）

**Interfaces:**
- Consumes: `幻灯片[].讲稿`（可选字符串，Task 1 产出契约）。
- Produces: `export_courseware_pptx(content, out_path)`——有讲稿的页生成 notesSlide（备注正文=讲稿全文），无讲稿的页不生成（旧课件导出行为与现状一致）。python-pptx 1.0.2 的 `slide.notes_slide` 访问即惰性创建备注部件。

- [ ] **Step 1: 更新夹具 + 写失败测试**

在 `backend/tests/test_prep_export.py` 中把 COURSEWARE（第 24~27 行）替换为：

```python
COURSEWARE = {
    "标题": "机器学习基础课件",
    "幻灯片": [{"标题": "梯度下降", "要点": ["沿负梯度方向迭代", "学习率控制步长"],
                "讲稿": "同学们好，今天我们来学习梯度下降。它的核心思想是沿负梯度方向一步步迭代。"}],
}

COURSEWARE_LEGACY = {
    "标题": "旧版课件",
    "幻灯片": [{"标题": "梯度下降", "要点": ["沿负梯度方向迭代"]}],
}
```

文件末尾追加两个测试：

```python
def test_export_courseware_pptx_writes_script_to_notes(tmp_path):
    out = export_courseware_pptx(COURSEWARE, tmp_path / "课件.pptx")
    assert out.exists()
    from pptx import Presentation
    prs = Presentation(str(out))
    slide = prs.slides[0]
    assert slide.has_notes_slide
    assert slide.notes_slide.notes_text_frame.text == COURSEWARE["幻灯片"][0]["讲稿"]


def test_export_courseware_pptx_legacy_without_script_has_no_notes(tmp_path):
    """旧课件（无讲稿）导出与现状一致：不产生备注页。"""
    out = export_courseware_pptx(COURSEWARE_LEGACY, tmp_path / "旧课件.pptx")
    assert out.exists()
    from pptx import Presentation
    prs = Presentation(str(out))
    assert not prs.slides[0].has_notes_slide
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_export.py -q`
Expected: `test_export_courseware_pptx_writes_script_to_notes` FAILED（`has_notes_slide` 为 False，备注未写入）。

- [ ] **Step 3: 实现备注写入**

`backend/app/services/prep_export.py`，替换 `export_courseware_pptx`（第 65~74 行）：

```python
def export_courseware_pptx(content: dict, out_path: Path) -> Path:
    """课件大纲 JSON → PPT 文档（标题+要点列表；每页讲稿写入备注栏供教师放映讲解）。"""
    prs = Presentation()
    for slide_data in content.get("幻灯片", []):
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # 标题+内容版式
        slide.shapes.title.text = slide_data.get("标题", "")
        body = slide.placeholders[1].text_frame
        body.text = "\n".join(slide_data.get("要点", []))
        script = (slide_data.get("讲稿") or "").strip()
        if script:
            # python-pptx 无显式建备注 API：访问 notes_slide 时惰性创建 notesSlide 部件
            slide.notes_slide.notes_text_frame.text = script
    prs.save(str(out_path))
    return out_path
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_export.py -q`
Expected: 全部 PASS（既有 `test_export_courseware_pptx` 断言不变仍过）。

- [ ] **Step 5: 全量回归 + 提交**

Run: `cd backend && python -m pytest tests/ -q`
Expected: 295 passed（293 + 2 新增）, 2 deselected。

```bash
git add backend/app/services/prep_export.py backend/tests/test_prep_export.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 课件导出 PPTX 讲稿写入备注栏

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 前端讲课面板组件 PrepLecturePanel.vue（控制器直接实现）

**Files:**
- Create: `frontend/src/views/prep/PrepLecturePanel.vue`

**Interfaces:**
- Consumes:
  - `speakTextTimed(text)` from `@/api/voice` → `Promise<{ blob: Blob; marks: VoiceMark[] } | null>`（TTS 不可用返回 null）。
  - `PlaybackManager` from `@/utils/audio`：`ensureContext()` / `enqueue(blob, marks?)` / `stop()` / `isPlaying` / 回调 `onMouth(v)`、`onEnd()`（队列播完且未 stop 时触发；stop 后不触发）。
  - `Live2DAvatar` from `@/components/live2d/Live2DAvatar.vue`：`defineExpose({ setMouth })`。
- Produces: 组件 props `{ slides: { 标题: string; 要点: string[]; 讲稿?: string }[]; lessonTitle?: string }`，emit `close`。

- [ ] **Step 1: 创建组件（完整代码）**

创建 `frontend/src/views/prep/PrepLecturePanel.vue`：

```vue
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
```

- [ ] **Step 2: 构建与类型验证**

Run: `cd frontend && npm run build && npx tsc --noEmit`
Expected: build 成功；tsc 0 错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/prep/PrepLecturePanel.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 新增数字人讲课面板 PrepLecturePanel

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: PrepEditorView 接入讲课入口（控制器直接实现）

**Files:**
- Modify: `frontend/src/views/prep/PrepEditorView.vue`

**Interfaces:**
- Consumes: `PrepLecturePanel`（Task 3 的 props/emit）；`lesson.content_json?.幻灯片`（Task 1 契约，旧课件可能无讲稿）。
- Produces: 课件编辑页工具栏的「数字人讲课」按钮；`lectureMode` 开启时整页切换为讲课面板。

- [ ] **Step 1: 模板改造（完整替换）**

`frontend/src/views/prep/PrepEditorView.vue` 的 `<template>` 整体替换为：

```vue
<template>
  <div>
    <!-- 讲课模式：整页切换为数字人讲课面板（仅课件类型） -->
    <PrepLecturePanel
      v-if="lectureMode"
      :slides="lesson?.content_json?.幻灯片 || []"
      :lesson-title="lesson?.title"
      @close="lectureMode = false"
    />
    <template v-else>
      <el-page-header class="page-header" :content="lesson?.title || '教案编辑'" @back="$router.push(`/prep/course/${lesson?.course_id}`)" />
      <el-row :gutter="16" style="margin-top: 16px">
        <el-col :span="17">
          <el-card>
            <template #header>
              <div class="card-head">
                <span><el-icon class="head-icon"><EditPen /></el-icon>内容编辑</span>
                <div>
                  <!-- 导出按钮按教案类型显示（后端映射：docx←plan/case，pptx←cw，pdf←exercises/exam） -->
                  <el-button v-if="['plan', 'case'].includes(lesson?.lesson_type || '')" @click="onExport('docx')">
                    <el-icon class="btn-ico"><Download /></el-icon>导出 Word
                  </el-button>
                  <el-button v-if="lesson?.lesson_type === 'cw'" @click="onExport('pptx')">
                    <el-icon class="btn-ico"><Download /></el-icon>导出 PPT
                  </el-button>
                  <el-button v-if="lesson?.lesson_type === 'cw'" type="primary" plain
                    :disabled="!(lesson?.content_json?.幻灯片 || []).length" @click="enterLecture">
                    <el-icon class="btn-ico"><VideoPlay /></el-icon>数字人讲课
                  </el-button>
                  <el-button v-if="['exercises', 'exam'].includes(lesson?.lesson_type || '')" @click="onExport('pdf')">
                    <el-icon class="btn-ico"><Download /></el-icon>导出 PDF
                  </el-button>
                  <el-button type="primary" :loading="saving" @click="onSave">保存（新版本）</el-button>
                </div>
              </div>
            </template>
            <div class="editor-frame">
              <Toolbar style="border-bottom: 1px solid #eef0f6" :editor="editorRef" :default-config="toolbarConfig" />
              <Editor style="height: 480px; overflow-y: hidden" v-model="html" :default-config="editorConfig" @on-created="onCreated" />
            </div>
          </el-card>
        </el-col>
        <el-col :span="7">
          <el-card>
            <template #header>
              <div class="card-head"><el-icon class="head-icon"><Search /></el-icon>资源引用（检索后一键插入）</div>
            </template>
            <el-input v-model="refQuery" placeholder="检索课程资源">
              <template #append><el-button :loading="refSearching" @click="onRefSearch">检索</el-button></template>
            </el-input>
            <div v-for="h in refHits" :key="h.ref" class="ref-hit">
              <div class="ref-name"><b>{{ h.ref }}</b></div>
              <div class="ref-excerpt">{{ h.excerpt }}</div>
              <el-button size="small" text type="primary" @click="onInsertRef(h)">插入正文</el-button>
            </div>
            <div v-if="!refHits.length" class="ref-empty">输入关键词检索课程资源，点击「插入正文」引用到编辑器中</div>
          </el-card>
          <el-card style="margin-top: 16px">
            <template #header>
              <div class="card-head"><el-icon class="head-icon"><Clock /></el-icon>版本历史</div>
            </template>
            <el-timeline>
              <el-timeline-item v-for="v in versions" :key="v.version" :timestamp="`v${v.version}`">
                <el-button size="small" @click="onRestore(v.version)">恢复此版本</el-button>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>
```

（改动点：外层包 `<PrepLecturePanel v-if="lectureMode" ...>` 与 `<template v-else>`；header 加「数字人讲课」按钮。）

- [ ] **Step 2: 脚本改动**

`<script setup>` 顶部 imports 修改（第 66 行 `@element-plus/icons-vue` 与第 69~72 行 `@/api/prep` 之间）：

```ts
import { Clock, Download, EditPen, Search, VideoPlay } from '@element-plus/icons-vue'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import '@wangeditor/editor/dist/css/style.css'
import PrepLecturePanel from './PrepLecturePanel.vue'
```

state 区（`const refQuery = ref('')` 附近）加：

```ts
const lectureMode = ref(false)
```

函数区（`onCreated` 之前）加：

```ts
function enterLecture() { lectureMode.value = true }
```

- [ ] **Step 3: 构建与类型验证**

Run: `cd frontend && npm run build && npx tsc --noEmit`
Expected: build 成功；tsc 0 错误。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/prep/PrepEditorView.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 课件编辑页接入数字人讲课入口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 测试文档与 README 收尾

**Files:**
- Modify: `docs/工单17-智能备课-测试用例与结果.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1/2 的测试函数名（P23~P26 引用）；Task 3/4 的讲课面板（F07 彩排项）。

- [ ] **Step 1: 工单17 文档追加讲课模式用例**

`docs/工单17-智能备课-测试用例与结果.md`，在第一节表格末行（P22）后追加 4 行：

```markdown
| P23 | 生成课件含讲稿（mock LLM） | mock 网关 | POST /courses/{id}/generate type=cw | prompt 含讲稿要求，结果带每页讲稿 | ✅ `test_generate_courseware_prompt_asks_for_script` |
| P24 | 课件校验缺讲稿 | mock 返回缺讲稿 JSON | generate type=cw | BizError 502 提示重试 | ✅ `test_validate_courseware_requires_script_per_slide`（缺讲稿/纯空白均 502；齐全通过） |
| P25 | 导出 pptx 备注含讲稿 | 课件含讲稿 | GET .../export?format=pptx | 备注页读回讲稿全文 | ✅ `test_export_courseware_pptx_writes_script_to_notes` |
| P26 | 旧课件导出无备注（兼容） | 课件无讲稿字段 | GET .../export?format=pptx | 无备注页，其余与现状一致 | ✅ `test_export_courseware_pptx_legacy_without_script_has_no_notes` |
```

第二节表格末行（F06）后追加 1 行：

```markdown
| F07 | 教师打开课件 → 点「数字人讲课」→ 播放/暂停/上一页/下一页/停止/静音 → 末页自动停止；旧课件出现降级提示并朗读要点 | 朵娅逐页朗读、口型同步、自动翻页；控制条行为正确；导出 PPT 打开可见备注栏讲稿 | 待彩排（用户浏览器验收后回填） |
```

第三节「测试结果汇总」第 1 条后端行更新为实测数字：

```markdown
- 后端：`python -m pytest -q` → **295 passed, 2 deselected**（2026-09-22；291 基线 + Plan F 新增 4 用例）
```

- [ ] **Step 2: README 更新**

`README.md` 两处：

模块能力表「智能备课（教师）」行改为：

```markdown
| 智能备课（教师） | 校本资源上传 → 检索引用 → AI 生成教案/习题/试卷（课件自带每页讲稿）→ 版本管理 → 导出（PPT 备注栏含讲稿）→ 数字人讲课 |
```

「智能备课演示（工单17）」代码块后的说明段加一行：

```markdown
- **数字人讲课**：打开课件（课件大纲）→「数字人讲课」：朵娅按页朗读讲稿、自动翻页，控制条支持播放/翻页/停止/静音；生成于讲课功能上线前的旧课件自动降级朗读要点（重新生成可获讲稿）。
```

- [ ] **Step 3: 提交**

```bash
git add docs/工单17-智能备课-测试用例与结果.md README.md
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "docs: 讲课模式测试用例与 README 更新

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 收尾清单（全部任务完成后，控制器执行）

1. 全量回归：`cd backend && python -m pytest tests/ -q` → 295 passed, 2 deselected；`cd frontend && npm run build && npx tsc --noEmit` → 0 错误。
2. 浏览器彩排（用户执行）：teacher/teacher123 → 智能备课 → 打开课件（cw）→ 生成新课件（真实 LLM 出讲稿）→ 讲课按钮全流程 + 旧课件降级 + 导出 PPT 打开看备注；结果回填 F07 行。
3. 台账 `.superpowers/sdd/progress.md` 记录 Plan F 各任务状态与恢复地图（gitignored）。
4. GitHub 同步（按需，用户确认后推送）。
