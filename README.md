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
- **V1 范围说明**：问答为单轮（不保存会话历史）；.doc/.ppt/.xls 二进制老格式请先转换为 docx/pptx/xlsx 再上传；公式暂以文本/图片 OCR 兜底识别。

## 测试

```
cd backend && pytest          # 单元测试（不含 smoke）
cd backend && pytest -m smoke -o addopts=""   # 冒烟测试（需已下载 bge-m3 等模型）
```

## 工单对照

| 工单 | 模块 | 状态 |
|---|---|---|
| 16 | 需求分析与软件架构设计 | ✅ docs/工单16-教育智能体需求分析与软件架构设计.md |
| 17 | 智能备课 | ✅ 课程/生成/编辑器/引用/导出/版本（Plan B） |
| 18 | 智能助教（多模态RAG） | Plan C |
| 19 | 个性化学习推荐 | Plan D |
| 20 | 面试AI复盘 | Plan E |

## 目录结构

```
backend/app/{api,core,models,services} 后端分层
frontend/src/{api,router,stores,views} 前端
docs/ 工单文档与设计/计划
```
