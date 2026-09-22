# edu-agent-platform 教育智能体平台

Agent 数字人项目-教育智能体方向实训（工单 16~20）。单体平台四层架构：Vue3 + FastAPI + 智能服务层 + 数据层。

## 快速启动

### 后端（端口 8000）

```
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
python -m scripts.seed_demo_data   # 预置账号、演示数据与备课课程资源
python -m uvicorn app.main:app --reload --port 8000
```

### 前端（端口 5173）

```
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 ，账号：admin/admin123（管理员）、teacher/teacher123（教师）、student/student123（学生）、counselor/counselor123（就业指导）

## 智能备课演示（工单17）

```
cd backend && python -m scripts.seed_demo_data   # 预置课程与资源
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
浏览器登录 teacher/teacher123 → 智能备课 → 人工智能导论 → 上传资源/检索引用/生成/编辑/版本/导出
（生成功能需在 backend/.env 配置 DEEPSEEK_API_KEY）
```

测试用例与验收清单见 `docs/工单17-智能备课-测试用例与结果.md`。

V1 范围说明：导出以"生成时的结构化数据"为准；编辑器 HTML 编辑用于展示/微调与版本回溯，不与导出联动。

## 智能助教（工单 18）

- **多模态知识库**：上传 PDF/DOCX/PPTX/XLSX/图片 → 解析为文本/表格/图片块（OCR+原图保留）→ bge-m3 向量化入库（Milvus，异常自动退回 FAISS）。公共库由 admin 预置维护（seed 脚本已入库演示文档《人工智能导论知识库.pdf》），私有库按用户隔离。
- **混合检索重排**：提问后私有库+公共库各取向量 top-k 与 BM25 top-k → RRF 融合 → bge-reranker-v2-m3 精排（加载失败自动降级跳过精排）。
- **流式问答**：DeepSeek 流式生成（SSE），回答附引用溯源卡片（文件名+页码+原文摘录；图片块直显原图、表格块展示结构化文本）。
- **模型**：bge-m3（向量化）+ bge-reranker-v2-m3（精排），首次运行需联网下载（约 3GB），可设 `HF_ENDPOINT=https://hf-mirror.com` 加速；已有缓存可设 `HF_HUB_OFFLINE=1` 离线加载。
- **V1 范围说明**：.doc/.ppt/.xls 二进制老格式请先转换为 docx/pptx/xlsx 再上传；公式暂以文本/图片 OCR 兜底识别。（多轮会话已于 2026-09-22 补齐，见下方「数字人互动」）

## 个性化学习（工单 19）

- **演示数据**：seed 脚本预置知识图谱（12 个知识点 + 12 条前置关系）与《个性化学习演示习题》习题集（18 道选择题，覆盖全部知识点、易/中/难三档）。
- **诊断测试与初始画像**：学生首次进入先做诊断测试（复用备课习题，默认 10 题、易/中优先、不含答案），按知识点正确率生成初始画像；或导入历史课程成绩（0~100 均匀初始化）。
- **画像仪表盘**：雷达图（ECharts）展示全图谱知识点掌握度 + 推荐学习路径（未掌握按前置拓扑排序、附理由）+ 今日任务。
- **自适应练习**：按学生当前难度抽题，后端比对判分（提交裸字母"B"或完整选项"B.文本"均可），滚动近 10 次正确率 >80% 升档 / <50% 降档；答对 +10、答错 -15、提问 +2，每日 ×0.95 时间衰减。
- **AIGC 错题本**：答错自动入册并生成 AI 解析/错误原因/变式题（LLM 失败保留记录不报错，可手动重新生成）。
- **相似学生推荐（加分项）**：余弦相似度 top3，仅展示"对方掌握而我未掌握"的知识点（numpy 实现，无重型依赖）。
- **V1 范围说明**：知识图谱本机未装 Neo4j，按工单 16 退化方案用 SQL 表 + networkx 实现；前端学习页（`/module/learn`）随 Task 7 发布（菜单项学生角色可见，开发中标记"规划"）。

测试用例与验收清单见 `docs/工单19-个性化学习推荐-测试用例与结果.md`。

## 测试

```
cd backend && pytest          # 单元测试（不含 smoke）
cd backend && pytest -m smoke -o addopts=""   # 冒烟测试（需已下载 bge-m3 等模型）
```

当前基线：**221 passed, 2 deselected**（实测）。跑测前建议 `set HF_HUB_OFFLINE=1` 走本地模型缓存。

> **跑测注意（实测踩坑，两条）**
>
> 1. **不要传 `--basetemp`**。指定自定义临时目录后，全量运行时会出现大批夹具级假失败（实测同一份代码：默认目录 221 全绿，自定义目录先后出现 6 failed / 5 failed+1 error / 72 passed+149 errors 三种结果）。保持默认临时目录即可。
> 2. **本机环境下退出码不可信**。若本机的批量删除防护拦截了 pytest 收尾时的临时目录清理，进程会在所有用例跑完后被中止，导致 `-q` 的汇总行丢失、退出码为 1。**判读结果请看逐用例输出**，例如：
>    `pytest -v > out.txt 2>&1`，再数 `grep -c PASSED out.txt` / `grep -c FAILED out.txt`。

### 已知限制：FAISS 与含中文的路径

FAISS 的 C++ 写盘接口（`FileIOWriter`）用窄字符 `fopen` 打开文件，**Windows 下无法写入路径中含非 ASCII 字符的索引文件**。实测：

| 写入路径 | 结果 |
|---|---|
| `C:/.../项目/数字人/.../faiss`（含中文绝对路径） | `RuntimeError: ... could not open ...` |
| `C:/Users/.../Temp/probe/faiss`（纯 ASCII 绝对路径） | 正常 |
| `./data/faiss`（相对路径，项目当前用法） | 正常 |

项目当前通过 `settings` 中的**相对路径** `./data/faiss` 规避（相对路径字符串里没有中文字符，C++ 层只看到相对串）。**若把 `data_dir` 改成含中文的绝对路径，`upsert` 会直接抛 `RuntimeError`。** 稳妥修法是改用 `faiss.serialize_index` / `deserialize_index` + Python 层 `read_bytes`/`write_bytes`（Python 的 IO 正确处理 Unicode 路径），但会变更磁盘格式，需兼容旧索引文件，故暂未实施。

## 工单对照

| 工单 | 模块 | 状态 |
|---|---|---|
| 16 | 需求分析与软件架构设计 | ✅ docs/工单16-教育智能体需求分析与软件架构设计.md |
| 17 | 智能备课 | ✅ 课程/生成/编辑器/引用/导出/版本（Plan B） |
| 18 | 智能助教（多模态RAG） | ✅ Plan C + 数字人交互（Plan E：语音问答/朗读/Live2D） |
| 19 | 个性化学习推荐 | ✅ docs/工单19-个性化学习推荐-测试用例与结果.md |
| 20 | 面试AI复盘 | ❌ 已取消（2026-09-19 用户决策） |

## 目录结构

```
backend/app/{api,core,models,services} 后端分层
frontend/src/{api,router,stores,views} 前端
docs/ 工单文档与设计/计划
```

## 数字人互动（智能助教内嵌）

- **多轮会话**：问答按会话落库（`chat_sessions` / `chat_messages`），最近 3 轮上下文进提示词，数字人能接指代型追问
  （"那它设大了会怎样"）；检索 query 自动拼接上一轮问题，避免追问检索空手；引用随轮次落库，历史回放不丢溯源。
  头部显示「第 N 轮」、可开`历史对话`抽屉续接、可`新对话`重开。
- **自然对话（流式）**：点`自然对话`后持续送 16k PCM，**服务端 FSMN-VAD 自动断句**（`fsmn-vad`）+
  `paraformer-zh-streaming` 增量转写（边说边上屏），判定停顿即回答；`打断`只掐本轮播报，监听继续（可抢话）。
  流式模型不可用时该入口自动隐藏，退回按住说话。
- **语音问答**：按住说话 → FunASR 本地转写（`paraformer-zh`，录音不出本机）→ 知识库 RAG → edge-tts 分句朗读
- **口型时间轴**：edge-tts `WordBoundary` 词级时间戳 → 音节级张合包络（标点处闭嘴），与实时音量相乘驱动
  Live2D `ParamMouthOpenY`；拿不到时间轴时自动退回纯音量驱动。**当前是音节级对齐 + 启发式幅度，非音素级视面（viseme）**。
- 打字朗读：文字问答的回答默认朗读，右上角开关可静音
- 依赖：`pip install -r requirements.txt`（funasr/kaldi-native-fbank/edge-tts）；FunASR 模型首次使用自动下载
  （约 2GB：批量 paraformer + 流式 paraformer + FSMN-VAD，modelscope），或先跑 `python scripts/download_funasr_model.py` 预热；
  edge-tts 需联网（失败自动降级为纯文字）
- 浏览器：建议 Chrome/Edge；首次按住说话时授权麦克风
- 形象版权：Hiyori 为 Live2D 官方样例模型（Live2D Free Material License，可商用演示，保留本声明）

设计与能力边界见 `docs/superpowers/specs/2026-09-22-digital-human-conversation-design.md`。

