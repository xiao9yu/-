# 数字人交互设计（智能助教内嵌）

- 日期：2026-09-19
- 状态：已确认（用户 2026-09-19 批准）
- 关联：工单18 智能助教（Plan C，已合 master 2232650/0379890）；工单20 已取消（79c7d26）

## 1. 背景与目标

工单20（面试 AI 复盘）取消后，语音交互能力（ASR/TTS）并入工单18 智能助教：在助教页内嵌一个 Live2D 数字人形象，支持语音问答与回答朗读，达到演示级实时交互效果（存量评估 2~3 天增量）。

用户已确认的四个决策（2026-09-19 问答确认）：

| 决策点 | 结论 |
|---|---|
| 形象实现 | Live2D 模型 |
| 模型素材 | 官方免费样例模型（Hiyori，Live2D Free Material License，免费商用需保留版权声明） |
| 语音交互 | 按住说话 + 一键打断（回避回声消除与 VAD 自动检测两大翻车点） |
| 朗读范围 | 语音提问与打字提问的回答均由数字人朗读（带静音开关） |

网络与环境事实（2026-09-19 实测）：modelscope / PyPI / edge-tts 端点可达；HF 不可达（既有代码级自动离线不变）；本机已有 torch 2.13 + modelscope 1.39；Python 3.12.7；磁盘余量 149GB。

## 2. 范围

**做：**
- 助教页右侧数字人面板：Live2D 形象（呼吸/眨眼待机 + 说话口型）
- 语音问答：按住说话采集 → FunASR 转写 → 走既有 ask_stream 链（检索→精排→DeepSeek）→ edge-tts 分句合成 → 逐句播放 + 口型；聊天框同步渲染转写文本与回答
- 一键打断：播报中点击即停播并取消后端生成；按住说话时若正在播报自动先打断
- 打字问答朗读：既有 SSE 渲染完成后经 HTTP TTS 端点朗读（默认开，静音开关控制）
- 静音开关、识别中状态、WS 断连提示

**不做：**
- 实时流式 ASR（paraformer-zh-streaming）：本版为整段转写
- 全自动 VAD 打断、回声消除（麦克风自收听问题由"按住说话"规避）
- 写实渲染（Wav2Lip 需 GPU，明确不碰）
- 新角色/新权限：复用智能助教既有权限（登录师生同权）

## 3. 架构

后端全语音链路 + WebSocket 双工（语音模式），打字模式复用既有 SSE + 新增 HTTP TTS 端点。

```
语音模式:
  前端按住说话(MediaRecorder 采集 webm/opus)
    → 松开后 decodeAudioData 重编码 16k 单声道 WAV → WS 发送
    → 后端 FunASR paraformer-zh 离线转写(懒加载 + lifespan 预热)
    → 复用 kb_service.ask_stream 内部链(检索→精排→DeepSeek 流式)
    → 回答文本按中文标点分句 → edge-tts 逐句合成 mp3
    → WS 逐句下发音频 + citations/delta/done 事件(与 SSE 同名,前端复用渲染)
    → 前端 AudioContext 逐句排队播放, AnalyserNode 音量驱动口型
  打断: 前端点打断 → 立即停播 + WS 发 cancel → 后端取消 LLM/TTS 任务

打字模式:
  既有 SSE 问答照常 → done 后前端取完整回答文本
    → POST /api/voice/tts → 整段 mp3 → 播放 + 口型(共用播放器)
```

**已排除的备选**：① HTTP 上行 + SSE 复用混合——改动少但语音链路延迟高、打断控制分散；② 浏览器 SpeechSynthesis 朗读——拿不到音频流、无法驱动口型且音质差。

## 4. 组件

### 后端（backend/app/）

| 文件 | 职责 |
|---|---|
| `services/asr_service.py` | FunASR 懒加载单例 + lifespan 预热；`transcribe(wav_bytes) -> str`；模型缺失/加载失败抛 ASRUnavailableError |
| `services/tts_service.py` | edge-tts 合成；`synthesize(text) -> bytes`（整段）与 `synthesize_sentences(text) -> AsyncIterator[(sentence, bytes)]`（分句）；按文本哈希 LRU 内存缓存（上限 50 条）；失败重试 1 次后抛 TTSUnavailableError |
| `api/voice.py` | WS `/api/voice/chat`（语音全链路）+ HTTP `POST /api/voice/tts`（打字朗读）；均登录鉴权（复用 deps.get_current_user） |
| `scripts/download_funasr_model.py` | FunASR 模型预下载脚本（modelscope，一次性） |

依赖新增（钉版）：`funasr`、`edge-tts`、`torchaudio`（与既有 torch 2.13 匹配的版本）。

### 前端（frontend/src/、frontend/public/）

| 文件 | 职责 |
|---|---|
| `public/live2d/hiyori/` | 官方样例模型文件（.moc3 系列 + 贴图 + motions），README 保留 Live2D 版权声明 |
| `components/live2d/` 或 views/assistant 内 | pixi.js + pixi-live2d-display 渲染器封装：挂载模型、待机（PARAM_BREATH 呼吸 + PARAM_EYE_BLINK 眨眼）、`setVolume(v)` 驱动 PARAM_MOUTH_OPEN_Y |
| `api/voice.ts` | WS 客户端（重连/断连处理）+ `/api/voice/tts` 调用 |
| AssistantView 数字人面板 | Live2D 画布 + 静音开关 + 按住说话按钮（含"识别中…"状态）+ 播报中打断按钮；面板沿用既有深色面板/靛蓝主色风格，形象外不做卡通装饰 |

前端依赖新增：`pixi.js`、`pixi-live2d-display`。

## 5. 协议与数据流细节

### WS 协议（/api/voice/chat）

客户端 → 服务端（JSON）：
```json
{"type": "audio", "data": "<base64 16k 单声道 WAV>"}
{"type": "cancel"}
```

服务端 → 客户端（JSON，事件名与既有 SSE 对齐以复用前端渲染）：
```json
{"type": "status", "state": "transcribing"}   // 收到音频,开始转写
{"type": "transcript", "text": "转写结果"}     // 转写完成,前端作为用户消息渲染
{"type": "status", "state": "thinking"}       // 检索/生成中
{"type": "citations", "items": [...]}         // 复用既有结构
{"type": "delta", "text": "..."}              // 回答文本流式
{"type": "audio", "seq": 1, "data": "<base64 mp3>"}  // 分句音频
{"type": "done", "audio_total": 3}
{"type": "error", "message": "..."}           // ASR/TTS/LLM 错误,协议不中断
```

### 音频格式决策

- 采集：MediaRecorder（webm/opus），按住期间持续收集 chunks，松开合成 blob
- 转码：前端 `decodeAudioData` 解码 → 重采样 16k 单声道 → 编码 WAV（纯浏览器内完成，后端零 ffmpeg 依赖）
- 播放：AudioContext + 逐句 decodeAudioData + 顺序排队调度；AnalyserNode 挂增益节点取音量驱动口型
- 首次音频前必须已完成一次用户手势（按住说话/发送/切换开关即满足），规避 Chrome 自动播放策略；麦克风授权在首次按住说话时触发

### 分句合成与延迟

- 中文标点（。！？；\n）分句；首句合成完成即下发，边生成边播
- 预期：松开说话 → 转写（10s 语音 ≈ 5s，UI 显示"识别中…"）→ LLM 首 token → 首句播报 ≈ 2~4s 起播
- 单句过长（>120 字）再按逗号切分；空句/纯符号句跳过

### 打断语义

- 前端点打断：立即停止当前播放、清空播放队列、发 `cancel`
- 后端收到 cancel：取消当前连接的生成任务（asyncio 任务取消 + 生成器关闭），不再下发后续音频
- 按住说话开始瞬间若正在播报：前端先执行打断流程再开始采集
- 转写/生成自然结束后连接保持，前端可继续下一次按住说话（同一 WS 复用）

## 6. 错误处理与降级

| 场景 | 行为 |
|---|---|
| ASR 模型未下载/加载失败 | 转写请求回 `error`（"语音识别未就绪，请打字提问"）；文字功能零影响 |
| 转写结果为空 | 回 `error` 提示未识别到语音 |
| edge-tts 网络失败 | 重试 1 次后该句/整段静默跳过；回答文字照常显示；前端收到 `done` 无音频正常结束 |
| WS 断连 | 前端语音按钮禁用 + 提示重连；打字聊天不受影响 |
| 按住说话超过 60s | 前端自动松开并发送 |

## 7. 测试与验收

- 后端 pytest（backend/ 下运行）：
  - asr_service：mock AutoModel 的转写结果、模型未就绪抛 ASRUnavailableError
  - tts_service：mock edge-tts Communicate 的字节输出、分句切分边界（长句/空句）、缓存命中、重试后失败
  - api/voice：TestClient websocket_connect 全链路（audio→transcript→delta→audio→done）、cancel 后不再有后续帧、HTTP /tts 鉴权与字节返回
  - 全量回归（既有 153 passed, 2 deselected 基线）
- 前端：npm run build + tsc 0 错误
- 彩排清单（用户浏览器执行，结果回填测试文档）：
  1. 打字提问 → 聊天框照常 + 数字人口型朗读；静音开关生效
  2. 按住说话语音提问 → 转写进聊天框 → 回答流式 + 分句朗读
  3. 播报中点击打断 → 立即停声，可继续下一次提问
  4. 断网（或停 edge-tts）→ 回答文字正常、朗读静默降级不报错
  5. 刷新页面 → WS 重连、待机动画正常

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| FunASR 模型 ~1GB 下载失败/过慢 | modelscope 已验证可达；提供预下载脚本先行下载；失败则语音功能降级、文字不受影响 |
| CPU 整段转写延迟（RTF ≈ 0.5） | UI 明确"识别中…"状态；后续可换 paraformer-zh-streaming（本版不做） |
| edge-tts 依赖外网 | 已验证可达；失败静默降级（第 6 节） |
| Live2D 样例为二次元风，与平台成熟内敛风有张力 | 用户已确认；面板沿用深色/靛蓝既有设计 token，形象外不加卡通装饰 |
| Chrome 自动播放/麦克风权限 | 以用户手势为触发点；首次交互请求授权 |
| pixi-live2d-display 与 Vue 3/TS 集成 | 渲染器独立封装为组件，口型驱动走 ref 方法调用，与 Vue 响应式隔离 |

## 9. 收尾事项（全部完工后统一执行）

1. Plan D 用例30 浏览器彩排结果回填测试文档（2026-09-18 已交付清单）
2. 数字人彩排结果回填测试文档
3. README 更新：工单18 行标注数字人交互完成
4. 依赖钉版 + seed/文档收尾 + 全量回归
5. dev → master 合并（SDD 既定流程：终审后 finishing-a-development-branch）
