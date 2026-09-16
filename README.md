# edu-agent-platform 教育智能体平台

Agent 数字人项目-教育智能体方向实训（工单 16~20）。单体平台四层架构：Vue3 + FastAPI + 智能服务层 + 数据层。

## 快速启动

### 后端（端口 8000）

```
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填写 DEEPSEEK_API_KEY
python -m scripts.seed_demo_data   # 预置账号与演示数据
python -m uvicorn app.main:app --reload --port 8000
```

### 前端（端口 5173）

```
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 ，账号：admin/admin123（管理员）、teacher/teacher123（教师）、student/student123（学生）、counselor/counselor123（就业指导）

## 测试

```
cd backend && pytest          # 单元测试（不含 smoke）
cd backend && pytest -m smoke -o addopts=""   # 冒烟测试（需已下载 bge-m3 等模型）
```

## 工单对照

| 工单 | 模块 | 状态 |
|---|---|---|
| 16 | 需求分析与软件架构设计 | ✅ docs/工单16-教育智能体需求分析与软件架构设计.md |
| 17 | 智能备课 | Plan B |
| 18 | 智能助教（多模态RAG） | Plan C |
| 19 | 个性化学习推荐 | Plan D |
| 20 | 面试AI复盘 | Plan E |

## 目录结构

```
backend/app/{api,core,models,services} 后端分层
frontend/src/{api,router,stores,views} 前端
docs/ 工单文档与设计/计划
```
