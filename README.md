# edu-agent-platform 教育智能体平台

Agent 数字人项目-教育智能体方向实训（工单 16~20）。单体平台四层架构：Vue3 + FastAPI + 智能服务层 + 数据层。

## 平台简介

面向高职院校的**教育智能体平台**：以课程知识库为核心，把备课、答疑、个性化学习串成一条 AI 驱动的教与学链路；智能助教内嵌可语音对话的 Live2D 数字人「朵娅」，文字与语音提问共用同一套检索增强问答。

| 模块 | 能力 |
|---|---|
| 智能备课（教师） | 校本资源上传 → 检索引用 → AI 生成教案/习题/试卷（课件自带每页讲稿）→ 版本管理 → 导出（PPT 备注栏含讲稿）→ 数字人讲课 |
| 智能助教（数字人） | 多模态知识库 + 混合检索重排 + 流式问答（带引用溯源）；按住说话 / 自然对话（VAD 自动断句），数字人分句朗读、口型对齐，支持打断与静音 |
| 个性化学习（学生） | 诊断测试 → 知识图谱画像（雷达图 + 推荐路径）→ 自适应练习（难度滚动）→ AIGC 错题本 → 相似学生推荐 |

**技术栈**：Vue3 + Element Plus + FastAPI + SQLAlchemy ｜ DeepSeek（LLM）· bge-m3 / bge-reranker-v2-m3（向量与精排）· Milvus / FAISS ｜ FunASR + FSMN-VAD + edge-tts + Live2D（Cubism 4）

**质量基线**：后端 295 个自动化用例全绿（`pytest`，2 deselected；2026-09-22）；RAG 检索评测 hit@5 **96.7%**、MRR **0.869**、引用合法率 **100%**（`backend/eval/` 可复现）。

## 界面预览

> 截图待补：登录页 / 智能备课 / 数字人助教 / 个性化学习仪表盘

## 快速启动

### 后端（端口 8000）

```
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
python -m scripts.seed_demo_data   # 预置账号、演示数据与备课课程资源
python -m uvicorn app.main:app --reload --port 8000
```

> **JWT 密钥（SECRET_KEY）**：`.env` 未配置时不使用任何默认密钥——dev 环境自动生成随机密钥并保存到 `backend/.secret_key`（已 gitignore，重启复用，已签发 token 不失效）；`APP_ENV=prod` 且未配置则**拒绝启动**。
> 注意：首次启动后密钥即固定，若清掉 `.secret_key`，此前签发的 token 全部失效（需重新登录）。

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

- **数字人讲课**：打开课件（课件大纲）→「数字人讲课」：朵娅按页朗读讲稿、自动翻页，控制条支持播放/暂停/上一页/下一页/停止（退出讲课）/静音；生成于讲课功能上线前的旧课件自动降级朗读要点（重新生成可获讲稿）。

测试用例与验收清单见 `docs/工单17-智能备课-测试用例与结果.md`。

V1 范围说明：导出以"生成时的结构化数据"为准；编辑器 HTML 编辑用于展示/微调与版本回溯，不与导出联动。

## 智能助教（工单 18）

- **多模态知识库**：上传 PDF/DOCX/PPTX/XLSX/图片 → 解析为文本/表格/图片块（OCR+原图保留）→ bge-m3 向量化入库（Milvus，异常自动退回 FAISS）。公共库由 admin 预置维护（seed 脚本已入库演示文档《人工智能导论知识库.pdf》），私有库按用户隔离。
- **混合检索重排**：提问后私有库+公共库各取向量 top-k 与 BM25 top-k → RRF 融合 → bge-reranker-v2-m3 精排（加载失败自动降级跳过精排）。送精排的候选数由 `settings.rerank_candidates`（默认 10）控制，取值依据见 `backend/eval/rerank_ab.py` 的 A/B。
- **流式问答**：DeepSeek 流式生成（SSE），回答附引用溯源卡片（文件名+页码+原文摘录；图片块直显原图、表格块展示结构化文本）。
- **模型**：bge-m3（向量化）+ bge-reranker-v2-m3（精排），首次运行需联网下载（约 3GB），可设 `HF_ENDPOINT=https://hf-mirror.com` 加速；已有缓存可设 `HF_HUB_OFFLINE=1` 离线加载。
- **知识库一致性自检**：向量库落盘是整库覆盖写，一旦某次载入失败/中断就可能让已有向量静默消失，而文档状态仍是 `ready`（检索悄悄少一条召回通道）。现已加固：载入失败即锁定集合拒绝写入、写盘原子化、启动后台自检；管理员可用 `GET /api/kb/consistency` 查看全库一致性、`POST /api/kb/consistency/repair` 幂等补回缺失向量。详见 `docs/RAG检索与引用质量评测报告.md` §5.2。
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

当前基线：**295 passed, 2 deselected**（2026-09-22 实测）。跑测前建议 `set HF_HUB_OFFLINE=1` 走本地模型缓存。

> **跑测注意（实测踩坑，两条）**
>
> 1. **不要传 `--basetemp`**。指定自定义临时目录后，全量运行时会出现大批夹具级假失败（实测同一份代码：默认目录全绿，自定义目录先后出现 6 failed / 5 failed+1 error / 72 passed+149 errors 三种结果）。保持默认临时目录即可。
> 2. **本机环境下退出码不可信**。若本机的批量删除防护拦截了 pytest 收尾时的临时目录清理，进程会在所有用例跑完后被中止，导致 `-q` 的汇总行丢失、退出码为 1。**判读结果请看逐用例输出**，例如：
>    `pytest -v > out.txt 2>&1`，再数 `grep -c PASSED out.txt` / `grep -c FAILED out.txt`。

### FAISS 索引与含中文的路径（已修复）

FAISS 的 C++ 写盘接口（`FileIOWriter`）用窄字符 `fopen` 打开文件，**Windows 下无法打开路径中含非 ASCII 字符的索引文件**。历史实测：

| 路径 | `faiss.write_index` 结果 |
|---|---|
| `C:/.../项目/数字人/.../faiss`（含中文绝对路径） | `RuntimeError: ... could not open ...` |
| `C:/Users/.../Temp/probe/faiss`（纯 ASCII 绝对路径） | 正常 |
| `./data/faiss`（相对路径） | 正常 |

原先只是靠 `settings` 里的**相对路径** `./data/faiss` 侥幸规避（相对字符串中没有中文，C++ 层看不到中文）。**若把 `data_dir` 配成含中文的绝对路径，`upsert` 会直接抛错。**

现已修复：`FaissVectorStore` 的索引读写改走 Python 层字节 IO（`read_bytes`/`write_bytes`）配合 `serialize_index` / `deserialize_index`，绕开 C++ 窄字符 `fopen`，任何路径（含中文、含空格）均可正常读写。

**无需数据迁移**：实测两种方式的产物字节完全一致（均为 4 字节 fourcc `IBxF` 开头，同一索引经 `write_index` 与 `serialize_index` 得到的 109 字节逐字节相同），旧索引文件可直接读。`test_faiss_reads_legacy_index_written_by_write_index` 把该兼容性钉死。

顺带加固：`_load()` 现在对单个损坏/截断的索引文件（如写盘中断留下的 0 字节）只记录告警并跳过，不再让整个向量库构造失败。

对应回归用例：`test_faiss_roundtrip_under_non_ascii_path`（中文目录落盘 + 重开读回）、`test_faiss_reads_legacy_index_written_by_write_index`（向后兼容）、`test_faiss_load_tolerates_corrupt_index`（容错）。

## RAG 检索与引用质量评测

`backend/eval/` 提供一套可复现的评测（题目集 32 题 + 脚本 + 指标单测），让"检索准不准、引用有没有编"从主观感受变成可对比的数字。

```
cd backend
pytest tests/test_eval_metrics.py                      # 指标函数单测（纯函数，不加载模型）
HF_HUB_OFFLINE=1 python -m eval.run_eval               # 检索层（零 LLM 成本，约 3 分钟）
HF_HUB_OFFLINE=1 python -m eval.run_eval --with-llm    # 端到端（消耗 32 次 LLM 调用）
HF_HUB_OFFLINE=1 python -m eval.run_eval --no-rerank   # 对照组：关闭精排
HF_HUB_OFFLINE=1 python -m eval.rerank_ab              # 精排候选数/截断长度的质量-时延 A/B
```

当前基线（`student` 视角，342 chunks，top_k=5，精排开启）：

| 指标 | 结果 |
|---|---|
| hit@1 / hit@3 / hit@5 | 80.0% / 93.3% / **96.7%** |
| MRR | **0.869** |
| 引用合法率（无越界 `[n]`） | **100%** |
| 引用覆盖率（带标注的句子占比） | 87.0% |
| 负样本无误引用率（资料不足不编造） | **100%** |
| 平均检索耗时 | 21.1 s → **11.5 s**（候选数 20→10 后） |

> **检索时延**：本机 `torch` 为 CPU 版（CUDA 不可用），bge-reranker-v2-m3 精排约 1.1 s/对且与本机 token 计算量近似线性，占检索耗时约 99%，是语音对话首响的主要瓶颈。已把送精排的候选数从 20 降到 10（`settings.rerank_candidates`）：32 题 A/B 显示 hit@1/3/5 与 MRR **逐项不变、逐题无回退**，耗时降 37%。另已实测 `settings.rerank_max_len=384`（截断）可再降 43% 且 32 题无损失，**但该题库对"答案在 chunk 尾部"的问法覆盖不足，故未设为默认**——详见报告 §4.2。残留的 11.5 秒属结构性（5.7 亿参数交叉编码器 + 无 GPU），再压需换模型/量化/上 GPU，均须先用本评测集做对照验证。完整归因与其余发现见 `docs/RAG检索与引用质量评测报告.md`。

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

