# Plan B：工单 17 智能备课（LLM 生成 + 富文本编辑 + 资源引用 + 导出 + 版本）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付工单 17 智能备课模块：教师登录 → 填课程信息 → LLM 结构化生成教案/课件大纲/习题/月考试题 → 校本资源检索引用 → 富文本编辑 → 导出 Word/PPT/PDF → 版本快照回溯。

**Architecture:** 复用 Plan A 公共底座（认证/LLM 网关/RAG 引擎/文件服务/解析管线/向量库），新增备课域：数据模型（courses/lessons/exercises/version_snapshots/media_files/citations/course_files）→ 生成服务（DeepSeek JSON 结构化）→ 资源检索（解析+混合检索，复用 hybrid_retrieve）→ 导出服务（python-docx/python-pptx/reportlab）→ /api/prep 路由 → Vue3 前端三页面（wangeditor 富文本）。协同编辑 V1 简化：课程协作者 + 版本快照回溯（Yjs 实时同步为加分项，不做）。

**Tech Stack:** 底座（FastAPI/SQLAlchemy/OpenAI SDK/rank-bm25/jieba/pymupdf 等）+ python-docx + python-pptx + reportlab + 前端 wangeditor（@wangeditor/editor-for-vue ^5）。

## Global Constraints

- 本计划所有新 Python 文件头部注释用模块专属工单编号：`# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)`；Vue/TS 文件用 `<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->`（HTML）或 `// 工单编号：...`（TS）
- 代码注释用中文；每个任务结束必须 git commit（身份 `huqiaoyu <huqiaoyu@local>`，用 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit ...`）
- TDD：后端每个任务先写失败测试→跑测试确认失败→实现→跑测试确认通过→提交；pytest 从 `backend/` 目录运行（`python -m pytest`），默认排除 smoke
- 前端不写单测，以 `npm run build` 通过 + 手动功能清单验证
- 习题 JSON 结构（设计文档 6.1 原文，工单 19 直接复用）：`{题干, 选项, 答案, 解析, 知识点, 难度}`——**中文键**
- lesson_type 枚举：`plan`（教案）/ `cw`（课件大纲）/ `exercises`（习题集）/ `case`（教学案例）/ `exam`（月考试题）——设计文档 6.1 五种生成类型全覆盖
- 角色约束：仅 `teacher`/`admin` 可创建课程与操作备课内容；`student` 只读不可操作（后端 403 拦截）；`counselor` 不参与本模块
- 导出格式映射：教案/案例 → Word（docx）；课件大纲 → PPT（pptx）；习题/月考试题 → PDF（reportlab，中文字体注册 simhei.ttf 回退 STSong-Light）；其余组合返回 400 友好提示
- 引用标注格式：`[N] 来源：文件名 第X页`（页为空时省略"第X页"）——设计文档"教材名-章节"的语义落实：教材名=文件名，章节位置用页码精确定位（Office 文档无页码时省略）
- 插入多媒体 V1：wangeditor 图片上传（base64 嵌入编辑器展示 + 底座 files 表落盘 + media_files 登记）；音视频文件走 files 表（工单20 场景），编辑器内不内嵌播放器
- **V1 范围声明**（写进 README）：导出内容以"生成时的结构化数据"为准；编辑器 HTML 编辑用于展示/微调与版本回溯，不与导出联动（富交互后置，设计文档 §11 风险应对）
- 版本策略：保存（更新内容）时 lesson.version 递增并写入 VersionSnapshot；恢复历史版本 = 快照内容写回 + version 递增 + 新快照
- DeepSeek API key 未配置时生成接口返回友好错误（LLM 网关既有行为），不阻塞课程 CRUD/资源检索/导出等本地功能

---

### Task 1: 备课数据模型（七张表）

**Files:**
- Create: `backend/app/models/prep.py`
- Create: `backend/tests/test_models_prep.py`

**Interfaces:**
- Consumes: `app.db.Base`（Plan A Task 1）
- Produces: `Course / Lesson / Exercise / VersionSnapshot / MediaFile / Citation / CourseFile` 七个 ORM 模型（表名 `courses / lessons / exercises / version_snapshots / media_files / citations / course_files`）。Task 3/5/6 全部依赖。

- [ ] **Step 1: 写失败测试** `backend/tests/test_models_prep.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课数据模型测试：七张表的建表与基本 CRUD。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.file import FileRecord  # 注册 files 表（media_files 外键依赖）
from app.models.prep import Citation, Course, CourseFile, Exercise, Lesson, MediaFile, VersionSnapshot


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'prep.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def test_course_crud(db):
    course = Course(name="人工智能导论", subject="人工智能", description="导论课", owner_id=1)
    db.add(course)
    db.commit()
    got = db.get(Course, course.id)
    assert got.name == "人工智能导论"
    assert got.member_ids == []
    assert got.created_at is not None


def test_lesson_version_and_type(db):
    lesson = Lesson(course_id=1, title="第1课 教案", lesson_type="plan",
                    content_json={"标题": "测试"}, created_by=1)
    db.add(lesson)
    db.commit()
    got = db.get(Lesson, lesson.id)
    assert got.version == 1
    assert got.lesson_type == "plan"
    assert got.content_json["标题"] == "测试"


def test_exercise_standard_structure(db):
    """习题标准结构（中文键，工单19 复用）：题干/选项/答案/解析/知识点/难度。"""
    ex = Exercise(course_id=1, stem="梯度下降中控制步长的参数是",
                  options=["学习率", "批量大小", "迭代次数", "正则系数"],
                  answer="A", analysis="学习率控制步长", knowledge_point="梯度下降", difficulty="易")
    db.add(ex)
    db.commit()
    got = db.get(Exercise, ex.id)
    assert got.options[0] == "学习率"
    assert got.difficulty == "易"


def test_version_snapshot_and_citation(db):
    snap = VersionSnapshot(lesson_id=1, version=2, content_json={"标题": "旧版"}, created_by=1)
    cit = Citation(lesson_id=1, ref_no=1, source="教材.pdf", page=3, excerpt="梯度下降是……")
    db.add_all([snap, cit])
    db.commit()
    assert db.get(VersionSnapshot, snap.id).version == 2
    assert db.get(Citation, cit.id).ref_no == 1


def test_media_file_and_course_file(db):
    mf = MediaFile(lesson_id=1, file_id=10, position="body")
    cf = CourseFile(course_id=1, file_id=11)
    db.add_all([mf, cf])
    db.commit()
    assert db.get(MediaFile, mf.id).file_id == 10
    assert db.get(CourseFile, cf.id).file_id == 11
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_models_prep.py -v`
Expected: FAIL（ModuleNotFoundError: app.models.prep）

- [ ] **Step 3: 实现数据模型** `backend/app/models/prep.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课模块数据模型：课程/教案课件/习题/版本快照/多媒体/引用/课程资源。"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Course(Base):
    """课程：备课的组织单元；member_ids 存协作者（协同编辑 V1 简化）。"""
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(50), default="人工智能")   # 学科
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(Integer, index=True)            # 创建者
    member_ids: Mapped[list] = mapped_column(JSON, default=list)          # 协作者用户 id 列表
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Lesson(Base):
    """教案/课件大纲/习题集/教学案例/月考试题：content_json 存结构化内容（键见各生成服务）。"""
    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    lesson_type: Mapped[str] = mapped_column(String(20))  # plan|cw|exercises|case|exam
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Exercise(Base):
    """习题：标准结构（题干/选项/答案/解析/知识点/难度），工单 19 复用。"""
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    stem: Mapped[str] = mapped_column(Text)               # 题干
    options: Mapped[list] = mapped_column(JSON, default=list)  # 选项列表
    answer: Mapped[str] = mapped_column(String(200))      # 答案
    analysis: Mapped[str] = mapped_column(Text, default="")    # 解析
    knowledge_point: Mapped[str] = mapped_column(String(100), default="")  # 知识点
    difficulty: Mapped[str] = mapped_column(String(10), default="易")       # 易/中/难
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class VersionSnapshot(Base):
    """版本快照：每次保存/恢复时写入，支持历史回溯。"""
    __tablename__ = "version_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class MediaFile(Base):
    """教案/课件中插入的多媒体文件（关联底座 files 表）。"""
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))   # 底座 FileRecord
    position: Mapped[str] = mapped_column(String(50), default="body")  # 插入位置标记
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Citation(Base):
    """引用记录：资源检索后插入正文的引用标注。"""
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    ref_no: Mapped[int] = mapped_column(Integer)               # [N] 编号
    source: Mapped[str] = mapped_column(String(255))           # 来源文件名
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 页码（可空）
    excerpt: Mapped[str] = mapped_column(Text, default="")     # 原文摘录
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class CourseFile(Base):
    """课程级资源文件关联（资源检索的语料来源；设计文档表清单的合理扩展）。"""
    __tablename__ = "course_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_models_prep.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add backend/app/models/prep.py backend/tests/test_models_prep.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 备课数据模型（课程/教案/习题/版本快照/引用/课程资源，工单17）"
```

---

### Task 2: 备课生成服务（LLM 结构化生成四种内容）

**Files:**
- Create: `backend/app/services/prep_generator.py`
- Create: `backend/tests/test_prep_generator.py`

**Interfaces:**
- Consumes: `app.services.llm_gateway.LLMGateway.chat_json(messages, temperature) -> dict`、`get_gateway()`（Plan A Task 3）；`app.core.exceptions.BizError`
- Produces:
  - `generate_lesson_plan(course_name, subject, chapter, objectives, hours, resources="", llm=None) -> dict`（键：标题/教学目标/教学重点/教学难点/教学过程/作业/板书设计）
  - `generate_courseware(course_name, subject, chapter, objectives, hours, resources="", llm=None) -> dict`（键：标题/幻灯片[{标题, 要点[]}]）
  - `generate_exercises(course_name, subject, chapter, knowledge_points, count, resources="", llm=None) -> dict`（键：习题[{题干, 选项[], 答案, 解析, 知识点, 难度}]）
  - `generate_monthly_exam(course_name, subject, distribution, resources="", llm=None) -> dict`（键：试卷标题/大题[{题型, 知识点, 题目[{题干, 选项, 答案, 解析, 知识点, 难度}]}]）
  - `generate_case(course_name, subject, chapter, objectives, resources="", llm=None) -> dict`（键：标题/案例背景/案例描述/问题/案例分析/结论）
  - `validate_lesson_plan(data) / validate_courseware(data) / validate_exercises(data) / validate_exam(data) / validate_case(data)`——结构校验，缺必需键抛 BizError(502, ...)。Task 5 路由直接调用。

- [ ] **Step 1: 写失败测试** `backend/tests/test_prep_generator.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课生成服务测试：prompt 组装、JSON 校验、温度参数（不依赖真实 API）。"""
import pytest

from app.core.exceptions import BizError
from app.services.prep_generator import (
    generate_case,
    generate_courseware,
    generate_exercises,
    generate_lesson_plan,
    generate_monthly_exam,
    validate_case,
    validate_courseware,
    validate_exam,
    validate_exercises,
    validate_lesson_plan,
)

LESSON_PLAN = {
    "标题": "梯度下降教案",
    "教学目标": ["理解梯度下降原理", "掌握学习率作用"],
    "教学重点": ["梯度下降迭代公式"],
    "教学难点": ["学习率选择"],
    "教学过程": [{"环节": "导入", "内容": "回顾线性回归", "时长": "5分钟"}],
    "作业": "完成课后习题1-3",
    "板书设计": "迭代公式与示意图",
}

COURSEWARE = {
    "标题": "机器学习基础课件",
    "幻灯片": [
        {"标题": "梯度下降", "要点": ["沿负梯度方向迭代", "学习率控制步长"]},
        {"标题": "线性回归", "要点": ["拟合直线", "房价预测"]},
    ],
}

EXERCISES = {
    "习题": [
        {"题干": "梯度下降中控制步长的参数是", "选项": ["A.学习率", "B.批量大小", "C.迭代次数", "D.正则系数"],
         "答案": "A", "解析": "学习率控制步长", "知识点": "梯度下降", "难度": "易"},
    ]
}

EXAM = {
    "试卷标题": "人工智能导论月考试卷",
    "大题": [
        {"题型": "选择题", "知识点": "梯度下降",
         "题目": [{"题干": "梯度下降中控制步长的参数是", "选项": ["A.学习率", "B.批量大小"],
                   "答案": "A", "解析": "学习率控制步长", "知识点": "梯度下降", "难度": "易"}]},
    ]
}

CASE = {
    "标题": "垃圾邮件分类教学案例",
    "案例背景": "某电商平台每日收到大量垃圾邮件，影响客服效率。",
    "案例描述": "使用朴素贝叶斯对邮件进行二分类，训练集包含 5000 封标注邮件。",
    "问题": "如何设计特征并评估模型效果？",
    "案例分析": "提取词频特征，使用交叉验证评估准确率与召回率。",
    "结论": "朴素贝叶斯在小样本文本分类中效果良好，垃圾邮件召回率达 95%。",
}


class FakeLLM:
    """记录调用并返回预设 JSON。"""
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, messages, temperature=0.3):
        self.calls.append({"messages": messages, "temperature": temperature})
        return self.result


def _gw():
    return FakeLLM(LESSON_PLAN)


def test_generate_lesson_plan_prompt_and_temperature():
    llm = FakeLLM(LESSON_PLAN)
    result = generate_lesson_plan(
        course_name="人工智能导论", subject="人工智能", chapter="第3章 机器学习基础",
        objectives="理解梯度下降", hours="2课时", resources="[1] 来源：教材.pdf\n梯度下降通过沿负梯度方向迭代更新参数。", llm=llm,
    )
    assert result == LESSON_PLAN
    prompt_text = llm.calls[0]["messages"][-1]["content"]
    assert "人工智能导论" in prompt_text and "第3章 机器学习基础" in prompt_text
    assert "理解梯度下降" in prompt_text and "2课时" in prompt_text
    assert "[1] 来源：教材.pdf" in prompt_text          # 资源上下文拼入 prompt
    assert "JSON" in prompt_text                         # 结构化输出要求
    assert llm.calls[0]["temperature"] == 0.7            # 教案用 0.7


def test_generate_exercises_uses_low_temperature():
    llm = FakeLLM(EXERCISES)
    result = generate_exercises(
        course_name="人工智能导论", subject="人工智能", chapter="第3章",
        knowledge_points=["梯度下降", "线性回归"], count=5, llm=llm,
    )
    assert result == EXERCISES
    assert "梯度下降" in llm.calls[0]["messages"][-1]["content"]
    assert "5" in llm.calls[0]["messages"][-1]["content"]      # 数量要求
    assert llm.calls[0]["temperature"] == 0.3                  # 习题用 0.3（JSON 严格）


def test_generate_courseware_and_exam():
    gw1 = FakeLLM(COURSEWARE)
    assert generate_courseware("人工智能导论", "人工智能", "第3章", "目标", "2课时", llm=gw1) == COURSEWARE
    gw2 = FakeLLM(EXAM)
    assert generate_monthly_exam(
        "人工智能导论", "人工智能", [{"知识点": "梯度下降", "占比": "30%"}], llm=gw2) == EXAM
    assert "30%" in gw2.calls[0]["messages"][-1]["content"]


def test_generate_case():
    llm = FakeLLM(CASE)
    result = generate_case(
        "人工智能导论", "人工智能", "第4章 朴素贝叶斯", "理解分类器原理", llm=llm)
    assert result == CASE
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "第4章 朴素贝叶斯" in prompt and "理解分类器原理" in prompt
    assert llm.calls[0]["temperature"] == 0.7     # 案例用 0.7


def test_validators_accept_valid_and_reject_missing_keys():
    validate_lesson_plan(LESSON_PLAN)
    validate_courseware(COURSEWARE)
    validate_exercises(EXERCISES)
    validate_exam(EXAM)
    validate_case(CASE)
    with pytest.raises(BizError):
        validate_lesson_plan({"标题": "缺字段"})
    with pytest.raises(BizError):
        validate_exercises({"习题": [{"题干": "缺答案"}]})
    with pytest.raises(BizError):
        validate_exam({"试卷标题": "缺大题"})
    with pytest.raises(BizError):
        validate_case({"标题": "缺案例描述"})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_generator.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.prep_generator）

- [ ] **Step 3: 实现生成服务** `backend/app/services/prep_generator.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课生成服务：DeepSeek JSON 结构化生成教案/课件大纲/习题/案例/月考试题。
各生成函数统一签名：课程信息 + 教学参数 + 可选校本资源上下文（RAG 检索结果）→ 结构化 dict。
"""
from .llm_gateway import get_gateway
from ..core.exceptions import BizError

_LESSON_PLAN_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成一份详细教案。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n课时：{hours}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题、教学目标（列表）、教学重点（列表）、教学难点（列表）、"
    "教学过程（列表，每项含 环节/内容/时长）、作业（字符串）、板书设计（字符串）。不要输出其他内容。"
)

_COURSEWARE_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成课件大纲。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n课时：{hours}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题（字符串）、幻灯片（列表，每项含 标题/要点（字符串列表），"
    "10~15 页）。不要输出其他内容。"
)

_EXERCISES_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请根据以下信息生成练习题。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "覆盖知识点：{knowledge_points}\n题目数量：{count} 道\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：习题（列表，每项含 题干/选项（列表，如 [\"A.学习率\", ...]）/"
    "答案（如 \"A\"）/解析/知识点/难度（易/中/难））。题型为选择题。不要输出其他内容。"
)

_EXAM_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请根据以下知识点分布生成一份月考试卷。\n"
    "课程名称：{course_name}\n学科：{subject}\n"
    "知识点分布（知识点：占比）：\n{distribution}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：试卷标题（字符串）、大题（列表，每项含 题型/知识点/"
    "题目（列表，每项含 题干/选项/答案/解析/知识点/难度））。"
    "题型至少包含选择题与简答题；题目总数为 10 道左右，按占比分配。不要输出其他内容。"
)

_CASE_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成一个教学案例。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题（字符串）、案例背景（字符串）、案例描述（字符串）、"
    "问题（字符串）、案例分析（字符串）、结论（字符串）。不要输出其他内容。"
)


def _resources_section(resources: str) -> str:
    """校本资源上下文：无资源时给空段，有资源时拼入提示词。"""
    if not resources:
        return ""
    return f"【校本参考资料】\n{resources}\n回答内容应参考上述资料。\n"


def _call_json(prompt: str, temperature: float, llm) -> dict:
    chat = llm or get_gateway()
    messages = [
        {"role": "system", "content": "你是教育智能备课助手，只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    data = chat.chat_json(messages, temperature=temperature)
    if not isinstance(data, dict):
        raise BizError(502, "生成结果格式异常，请重试")
    return data


def _require_keys(data: dict, keys: list[str]) -> None:
    """结构校验：缺必需键抛业务异常（LLM 输出不完整时给出友好提示）。"""
    missing = [k for k in keys if k not in data]
    if missing:
        raise BizError(502, f"生成结果缺少字段：{'、'.join(missing)}，请重试")


def generate_lesson_plan(course_name, subject, chapter, objectives, hours,
                         resources="", llm=None) -> dict:
    """生成教案：{标题, 教学目标[], 教学重点[], 教学难点[], 教学过程[], 作业, 板书设计}。"""
    prompt = _LESSON_PLAN_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, hours=hours, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def generate_courseware(course_name, subject, chapter, objectives, hours,
                        resources="", llm=None) -> dict:
    """生成课件大纲：{标题, 幻灯片[{标题, 要点[]}]}。"""
    prompt = _COURSEWARE_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, hours=hours, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def generate_exercises(course_name, subject, chapter, knowledge_points, count,
                       resources="", llm=None) -> dict:
    """生成习题集：{习题[{题干, 选项[], 答案, 解析, 知识点, 难度}]}（工单19 复用结构）。"""
    prompt = _EXERCISES_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        knowledge_points="、".join(knowledge_points), count=count,
        resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.3, llm=llm)


def generate_monthly_exam(course_name, subject, distribution, resources="", llm=None) -> dict:
    """生成月考试卷：{试卷标题, 大题[{题型, 知识点, 题目[]}]}。distribution 为 [{知识点, 占比}]。"""
    dist_text = "\n".join(f"- {d['知识点']}：{d['占比']}" for d in distribution)
    prompt = _EXAM_PROMPT.format(
        course_name=course_name, subject=subject, distribution=dist_text,
        resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.3, llm=llm)


def generate_case(course_name, subject, chapter, objectives, resources="", llm=None) -> dict:
    """生成教学案例：{标题, 案例背景, 案例描述, 问题, 案例分析, 结论}。"""
    prompt = _CASE_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def validate_lesson_plan(data: dict) -> None:
    _require_keys(data, ["标题", "教学目标", "教学重点", "教学难点", "教学过程", "作业", "板书设计"])


def validate_courseware(data: dict) -> None:
    _require_keys(data, ["标题", "幻灯片"])
    if not isinstance(data["幻灯片"], list) or not data["幻灯片"]:
        raise BizError(502, "生成结果缺少幻灯片内容，请重试")


def validate_exercises(data: dict) -> None:
    _require_keys(data, ["习题"])
    if not isinstance(data["习题"], list) or not data["习题"]:
        raise BizError(502, "生成结果缺少习题，请重试")
    for ex in data["习题"]:
        _require_keys(ex, ["题干", "选项", "答案", "解析", "知识点", "难度"])


def validate_exam(data: dict) -> None:
    _require_keys(data, ["试卷标题", "大题"])
    if not isinstance(data["大题"], list) or not data["大题"]:
        raise BizError(502, "生成结果缺少大题，请重试")
    for section in data["大题"]:
        _require_keys(section, ["题型", "知识点", "题目"])


def validate_case(data: dict) -> None:
    _require_keys(data, ["标题", "案例背景", "案例描述", "问题", "案例分析", "结论"])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_generator.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add backend/app/services/prep_generator.py backend/tests/test_prep_generator.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 备课生成服务（教案/课件/习题/月考题，LLM JSON结构化，工单17）"
```

---

### Task 3: 课程资源检索（上传解析 + 混合检索引用）

**Files:**
- Create: `backend/app/services/prep_resources.py`
- Create: `backend/tests/test_prep_resources.py`

**Interfaces:**
- Consumes: `app.services.file_service.save_upload(file, owner_id, upload_dir, db) -> FileRecord`（Plan A Task 4）；`app.services.parser.parse_document(path) -> list[Chunk]`（Task 5）；`app.services.rag.KBCollection / hybrid_retrieve`（Task 8）；`app.services.vector_store.FaissVectorStore`（Task 7）；`app.services.embeddings.get_embedder`（Task 6）；`app.models.prep.CourseFile`（本计划 Task 1）
- Produces:
  - `add_resource(course_id, file, upload_dir, db) -> FileRecord`（落盘 + 登记 course_files）
  - `list_resources(course_id, db) -> list[FileRecord]`
  - `search_resources(course_id, query, upload_dir, db, top_k=5, *, vector_store=None, embedder=None) -> list[dict]`，返回 `[{"chunk": Chunk, "score": float, "ref": str}]`，`ref` 格式 `[N] 来源：文件名 第X页`
  - 检索实现：每次搜索实时解析课程全部资源文件（演示规模文件少，源文件即真相，无状态）→ 临时 FAISS 向量索引 + BM25 → `hybrid_retrieve` 融合 → 格式化引用。Task 5/6 直接调用。

- [ ] **Step 1: 写失败测试** `backend/tests/test_prep_resources.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""课程资源检索测试：上传 docx → 解析 → 混合检索 → 引用标注。"""
import io
from pathlib import Path

import pytest
from docx import Document
from fastapi import UploadFile

from app.db import Base
from app.models.prep import Course, CourseFile
from app.services.prep_resources import add_resource, list_resources, search_resources


@pytest.fixture
def db(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{tmp_path / 'res.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Course(name="人工智能导论", subject="人工智能", owner_id=1))
    session.commit()
    yield session, tmp_path
    Base.metadata.drop_all(engine)


@pytest.fixture
def docx_path(tmp_path):
    """含中文段落与表格的课程资源样例。
    评审修复（Task9 先例）：段落+表格+段落 → 3 块——rank_bm25 0.2.2 在 N=2 语料中
    IDF 恒 0（BM25 半程为空），且 FakeEmbedder 全等向量下 FAISS 同分顺序不确定，
    首位断言会偶发失败；3 块时 BM25 分数 para1>para2>0=表格，首位确定。"""
    doc = Document()
    doc.add_paragraph("梯度下降是机器学习中最基础的优化算法，通过沿负梯度方向迭代更新参数。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "算法"; table.cell(0, 1).text = "场景"
    table.cell(1, 0).text = "线性回归"; table.cell(1, 1).text = "房价预测"
    doc.add_paragraph("梯度下降在深度学习中被广泛使用。")
    path = tmp_path / "讲义.docx"
    doc.save(path)
    return path


class FakeEmbedder:
    """3 维固定向量：向量半程同分，检索结果由 BM25 半程主导，便于断言。"""
    dim = 3

    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]


def _add(db_pair, docx_path, filename="讲义.docx"):
    session, tmp_path = db_pair
    with open(docx_path, "rb") as f:
        file = UploadFile(filename=filename, file=io.BytesIO(f.read()))
        return add_resource(course_id=1, file=file, upload_dir=tmp_path / "uploads", db=session)


def test_add_resource_registers_course_file(db, docx_path):
    session, _ = db
    record = _add(db, docx_path)
    assert record.id > 0
    assert session.query(CourseFile).filter(CourseFile.course_id == 1).count() == 1
    listed = list_resources(1, session)
    assert listed[0].filename == "讲义.docx"


def test_search_resources_hits_and_ref_format(db, docx_path):
    session, tmp_path = db
    _add(db, docx_path)
    hits = search_resources(1, "梯度下降的优化原理是什么", tmp_path / "uploads", session,
                            top_k=3, embedder=FakeEmbedder())
    assert hits, "BM25 应命中语料"
    first = hits[0]
    assert first["chunk"].source == "讲义.docx"
    assert "梯度下降" in first["chunk"].text
    assert first["ref"].startswith("[1]")
    assert "来源：讲义.docx" in first["ref"]           # 引用标注格式
    assert first["score"] > 0


def test_search_resources_empty_course_returns_empty(db):
    session, tmp_path = db
    assert search_resources(1, "梯度下降", tmp_path / "uploads", session, embedder=FakeEmbedder()) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_resources.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.prep_resources）

- [ ] **Step 3: 实现资源检索** `backend/app/services/prep_resources.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""课程资源检索：上传课程资源 → 实时解析 → 关键词+向量混合检索 → 引用标注。
实现策略：每次搜索实时解析课程全部资源文件（演示规模文件少，源文件即真相、无状态、
重启安全），构建临时 FAISS 索引 + BM25，复用底座 hybrid_retrieve（RRF 融合）。
"""
import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..models.prep import CourseFile
from ..services.embeddings import get_embedder
from ..services.file_service import get_file_path, save_upload
from ..services.parser import parse_document
from ..services.rag import KBCollection, hybrid_retrieve
from ..services.vector_store import FaissVectorStore


def add_resource(course_id: int, file: UploadFile, upload_dir: Path | str, db: Session):
    """上传课程资源文件：底座落盘 + course_files 登记。owner_id 记 0（课程资源不属个人）。"""
    record = save_upload(file, owner_id=0, upload_dir=upload_dir, db=db)
    db.add(CourseFile(course_id=course_id, file_id=record.id))
    db.commit()
    return record


def list_resources(course_id: int, db: Session):
    """课程资源文件列表。"""
    from ..models.file import FileRecord
    links = db.query(CourseFile).filter(CourseFile.course_id == course_id).all()
    records = [db.get(FileRecord, link.file_id) for link in links]
    return [r for r in records if r is not None]


def search_resources(course_id: int, query: str, upload_dir: Path | str, db: Session,
                     top_k: int = 5, *, vector_store=None, embedder=None) -> list[dict]:
    """混合检索课程资源，返回 [{chunk, score, ref}]；ref 为引用标注文本。"""
    resources = list_resources(course_id, db)
    if not resources:
        return []
    chunks = []
    for record in resources:
        path = get_file_path(record, upload_dir)
        if path.exists():
            parsed = parse_document(path)
            for c in parsed:          # 评审修复：引用标注用用户上传的原始文件名（磁盘名为 uuid）
                c.source = record.filename
            chunks.extend(parsed)
    if not chunks:
        return []
    emb = embedder or get_embedder()
    # 临时向量索引：每次搜索重建（演示规模 chunk 数少，内积索引构建为毫秒级）
    with tempfile.TemporaryDirectory(prefix="prep_search_") as tmp:
        store = vector_store or FaissVectorStore(data_dir=tmp)
        store.create_collection("course_res", dim=emb.dim)
        store.upsert(
            "course_res",
            ids=[c.id for c in chunks],
            vectors=emb.embed_texts([c.text for c in chunks]),
            metadatas=[{"chunk_id": c.id, "source": c.source, "page": c.page} for c in chunks],
        )
        collection = KBCollection(name="course_res", chunks=chunks)
        hits = hybrid_retrieve(query, [collection], top_k=top_k,
                               vector_store=store, embedder=emb)
    return [
        {
            "chunk": h.chunk,
            "score": round(h.score, 4),
            "ref": _format_ref(i, h.chunk),
        }
        for i, h in enumerate(hits, start=1)
    ]


def _format_ref(ref_no: int, chunk) -> str:
    """引用标注：[N] 来源：文件名 第X页（页为空时省略）。"""
    page = f" 第{chunk.page}页" if chunk.page is not None else ""
    return f"[{ref_no}] 来源：{chunk.source}{page}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_resources.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add backend/app/services/prep_resources.py backend/tests/test_prep_resources.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 课程资源检索（上传解析+混合检索+引用标注，工单17）"
```

---

### Task 4: 导出服务（Word/PPT/PDF）

**Files:**
- Create: `backend/app/services/prep_export.py`
- Create: `backend/tests/test_prep_export.py`
- Modify: `backend/requirements.txt`（追加 python-docx/python-pptx/reportlab——若已有则跳过）

**Interfaces:**
- Consumes: 生成服务产出的结构化 dict（本计划 Task 2 的 JSON 键）
- Produces:
  - `export_lesson_docx(content: dict, out_path: Path) -> Path`（教案 → Word）
  - `export_courseware_pptx(content: dict, out_path: Path) -> Path`（课件大纲 → PPT）
  - `export_exercises_pdf(exercises: list[dict], title: str, out_path: Path) -> Path`（习题/月考题 → PDF，中文字体注册 simhei.ttf 回退 STSong-Light）
  - `export_case_docx(content: dict, out_path: Path) -> Path`（教学案例 → Word）
  - Task 5 导出端点调用。

- [ ] **Step 1: 写失败测试** `backend/tests/test_prep_export.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""导出服务测试：教案→docx、课件→pptx、习题→pdf，生成后读回断言内容。"""
from pathlib import Path

import pytest

from app.services.prep_export import (
    export_case_docx,
    export_courseware_pptx,
    export_exercises_pdf,
    export_lesson_docx,
)

LESSON_PLAN = {
    "标题": "梯度下降教案",
    "教学目标": ["理解梯度下降原理"],
    "教学重点": ["迭代公式"],
    "教学难点": ["学习率选择"],
    "教学过程": [{"环节": "导入", "内容": "回顾线性回归", "时长": "5分钟"}],
    "作业": "完成课后习题",
    "板书设计": "迭代公式示意图",
}

COURSEWARE = {
    "标题": "机器学习基础课件",
    "幻灯片": [{"标题": "梯度下降", "要点": ["沿负梯度方向迭代", "学习率控制步长"]}],
}

EXERCISES = [
    {"题干": "梯度下降中控制步长的参数是", "选项": ["A.学习率", "B.批量大小"],
     "答案": "A", "解析": "学习率控制步长", "知识点": "梯度下降", "难度": "易"},
]

CASE = {
    "标题": "垃圾邮件分类教学案例",
    "案例背景": "某电商平台每日收到大量垃圾邮件。",
    "案例描述": "使用朴素贝叶斯对邮件进行二分类。",
    "问题": "如何设计特征并评估模型效果？",
    "案例分析": "提取词频特征，交叉验证评估。",
    "结论": "垃圾邮件召回率达 95%。",
}


def test_export_lesson_docx(tmp_path):
    out = export_lesson_docx(LESSON_PLAN, tmp_path / "教案.docx")
    assert out.exists()
    from docx import Document
    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "梯度下降教案" in text and "理解梯度下降原理" in text


def test_export_courseware_pptx(tmp_path):
    out = export_courseware_pptx(COURSEWARE, tmp_path / "课件.pptx")
    assert out.exists()
    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == 1
    assert prs.slides[0].shapes.title.text == "梯度下降"


def test_export_exercises_pdf(tmp_path):
    out = export_exercises_pdf(EXERCISES, "诊断试题", tmp_path / "习题.pdf")
    assert out.exists()
    import pymupdf
    doc = pymupdf.open(str(out))
    text = doc[0].get_text()
    doc.close()
    assert "梯度下降" in text          # PDF 中文正常渲染（字体注册生效）
    assert "诊断试题" in text


def test_export_case_docx(tmp_path):
    out = export_case_docx(CASE, tmp_path / "案例.docx")
    assert out.exists()
    from docx import Document
    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "垃圾邮件分类教学案例" in text
    assert "朴素贝叶斯" in text and "95%" in text


def test_export_exercises_pdf_fallback_font_twice(tmp_path, monkeypatch):
    """模拟无 simhei 环境：回退字体注册名必须被缓存，连续两次导出都不崩。"""
    import pymupdf

    import app.services.prep_export as prep_export

    monkeypatch.setattr(prep_export, "_CN_FONT_NAME", None)  # 重置缓存，强制走回退注册路径
    monkeypatch.setattr(Path, "exists", lambda self: False)  # 无 Windows 字体
    out1 = prep_export.export_exercises_pdf(EXERCISES, "诊断试题", tmp_path / "习题1.pdf")
    out2 = prep_export.export_exercises_pdf(EXERCISES, "诊断试题", tmp_path / "习题2.pdf")
    assert out1.is_file() and out2.is_file()  # Path.exists 已被 patch，用 is_file 断言落盘
    doc = pymupdf.open(str(out2))
    text = doc[0].get_text()
    doc.close()
    assert "梯度下降" in text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_export.py -v`
Expected: FAIL（ModuleNotFoundError: app.services.prep_export）

- [ ] **Step 3: 实现导出服务** `backend/app/services/prep_export.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""导出服务：教案→Word（python-docx）、课件大纲→PPT（python-pptx）、习题/月考题→PDF（reportlab）。
内容以生成时的结构化数据为准（V1 范围声明见计划 Global Constraints）。
"""
from pathlib import Path

from docx import Document
from docx.shared import Pt
from pptx import Presentation
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_CN_FONT_NAME: str | None = None


def _register_cn_font() -> str:
    """注册中文字体：优先 Windows 黑体（simhei.ttf），找不到回退 reportlab 内置 CID 字体。
    返回注册名。"""
    global _CN_FONT_NAME
    if _CN_FONT_NAME:
        return _CN_FONT_NAME
    for path in (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simfang.ttf"):
        try:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont("CnFont", path))
                _CN_FONT_NAME = "CnFont"
                return "CnFont"
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _CN_FONT_NAME = "STSong-Light"
    return "STSong-Light"


def export_lesson_docx(content: dict, out_path: Path) -> Path:
    """教案 JSON → Word 文档。"""
    doc = Document()
    doc.add_heading(content.get("标题", "教案"), level=1)
    doc.add_heading("教学目标", level=2)
    for item in content.get("教学目标", []):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("教学重点", level=2)
    for item in content.get("教学重点", []):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("教学难点", level=2)
    for item in content.get("教学难点", []):
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("教学过程", level=2)
    for step in content.get("教学过程", []):
        doc.add_paragraph(f"{step.get('环节', '')}（{step.get('时长', '')}）：{step.get('内容', '')}")
    doc.add_heading("作业", level=2)
    doc.add_paragraph(content.get("作业", ""))
    doc.add_heading("板书设计", level=2)
    doc.add_paragraph(content.get("板书设计", ""))
    for p in doc.paragraphs:
        p.style.font.size = Pt(11)
    doc.save(str(out_path))
    return out_path


def export_courseware_pptx(content: dict, out_path: Path) -> Path:
    """课件大纲 JSON → PPT 文档（标题+要点列表）。"""
    prs = Presentation()
    for slide_data in content.get("幻灯片", []):
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # 标题+内容版式
        slide.shapes.title.text = slide_data.get("标题", "")
        body = slide.placeholders[1].text_frame
        body.text = "\n".join(slide_data.get("要点", []))
    prs.save(str(out_path))
    return out_path


def export_exercises_pdf(exercises: list[dict], title: str, out_path: Path) -> Path:
    """习题列表 → PDF（选择题：题干/选项/答案/解析，中文渲染）。"""
    font = _register_cn_font()
    pdf = canvas.Canvas(str(out_path), pagesize=A4)
    pdf.setTitle(title)
    y = A4[1] - 2 * cm
    pdf.setFont(font, 18)
    pdf.drawCentredString(A4[0] / 2, y, title)
    y -= 1.2 * cm
    pdf.setFont(font, 11)
    for i, ex in enumerate(exercises, start=1):
        lines = [f"{i}. {ex.get('题干', '')}"]
        lines.extend(ex.get("选项", []))
        lines.append(f"答案：{ex.get('答案', '')}　解析：{ex.get('解析', '')}")
        lines.append(f"知识点：{ex.get('知识点', '')}　难度：{ex.get('难度', '')}")
        for line in lines:
            if y < 2 * cm:          # 翻页
                pdf.showPage()
                pdf.setFont(font, 11)
                y = A4[1] - 2 * cm
            pdf.drawString(2 * cm, y, line)
            y -= 0.7 * cm
        y -= 0.5 * cm
    pdf.save()
    return out_path


def export_case_docx(content: dict, out_path: Path) -> Path:
    """教学案例 JSON → Word 文档。"""
    doc = Document()
    doc.add_heading(content.get("标题", "教学案例"), level=1)
    for heading, key in [("案例背景", "案例背景"), ("案例描述", "案例描述"), ("问题", "问题"),
                         ("案例分析", "案例分析"), ("结论", "结论")]:
        doc.add_heading(heading, level=2)
        doc.add_paragraph(content.get(key, ""))
    for p in doc.paragraphs:
        p.style.font.size = Pt(11)
    doc.save(str(out_path))
    return out_path
```

依赖追加：`backend/requirements.txt` 已含 python-docx/python-pptx/reportlab 则不动；缺则追加三行：`reportlab>=4.0`（python-docx/python-pptx 在 Plan A Task 5 已引入）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_export.py -v`
Expected: PASS（5 passed）。若 PDF 中文断言失败，检查 simhei.ttf 是否存在（`ls C:/Windows/Fonts/simhei.ttf`），不存在则依赖回退字体 STSong-Light（读回文本仍应含中文）。

- [ ] **Step 5: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add backend/app/services/prep_export.py backend/tests/test_prep_export.py backend/requirements.txt
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 备课导出服务（教案Word/课件PPT/习题PDF，工单17）"
```

---

### Task 5: 备课 API 路由（/api/prep）

**Files:**
- Create: `backend/app/api/prep.py`
- Create: `backend/tests/test_prep_api.py`
- Modify: `backend/app/main.py`（挂载 prep 路由）

**Interfaces:**
- Consumes: 本计划 Task 1~4 全部；`app.api.deps.get_current_user`、`app.models.user.Role`、`app.core.exceptions.BizError`（Plan A）
- Produces（全部 `/api/prep` 前缀，除导出外需登录）：
  - `POST /courses`（teacher/admin 创建）、`GET /courses`（我参与的课程）、`GET /courses/{id}`（成员可读）
  - `POST /courses/{id}/collaborators`（owner 添加协作者 `{"user_id": N}`）
  - `POST /courses/{id}/resources`（成员上传课程资源）、`GET /courses/{id}/search?q=&top_k=`（成员检索资源）
  - `POST /courses/{id}/generate`（成员调生成服务；body：`{type, chapter, objectives, hours, knowledge_points, count, distribution, query}`——`type` 支持 plan/cw/exercises/case/exam；`query` 非空时先检索资源拼入 prompt，返回结构化 JSON 初稿 + 引用标注列表，不落库）
  - `GET /courses/{id}/lessons`（课程教案/课件列表，前端课程详情页用）
  - `POST /courses/{id}/lessons`（保存 lesson：`{title, lesson_type, content_json}` → 落库 version=1 + 快照 v1）
  - `GET /lessons/{id}`、`PUT /lessons/{id}`（保存新版本：version+1 + 快照）、`GET /lessons/{id}/versions`、`POST /lessons/{id}/restore`（`{version}` → 写回 + version+1 + 新快照）
  - `POST /lessons/{id}/citations`（保存引用 `{ref_no, source, page, excerpt}`）
  - `POST /lessons/{id}/media`（登记插入的多媒体 `{file_id}` → media_files 表）
  - `GET /lessons/{id}/export?format=docx|pptx|pdf`（导出文件下载）
- 权限：课程 owner/member/admin 可读写；teacher/admin 可创建课程；其余 403。
- 导出映射（Global Constraints）：docx ← plan/case（教案 JSON/案例 JSON），pptx ← cw（课件 JSON），pdf ← exercises/exam（`exercises` 取 content_json["习题"]，`exam` 取各"大题"的"题目"合并）；其余类型×格式组合返回 400 友好提示。

- [ ] **Step 1: 写失败测试** `backend/tests/test_prep_api.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课 API 测试：课程 CRUD/资源/生成/版本/导出 + 权限拦截（真实临时库 + TestClient）。"""
import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app


@pytest.fixture
def db(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(db):
    with TestClient(app) as c:
        yield c


def _register_login(client, username, role):
    client.post("/api/auth/register", json={"username": username, "password": "pass123456",
                                            "role": role, "real_name": "测试"})
    resp = client.post("/api/auth/login", json={"username": username, "password": "pass123456"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_course(client, headers, name="人工智能导论"):
    resp = client.post("/api/prep/courses", json={"name": name, "subject": "人工智能",
                                                  "description": "测试课程"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


def test_student_cannot_create_course(client):
    headers = _register_login(client, "stu_prep", "student")
    resp = client.post("/api/prep/courses", json={"name": "x", "subject": "y"}, headers=headers)
    assert resp.status_code == 403


def test_teacher_course_crud_and_collaborator(client):
    headers = _register_login(client, "t1", "teacher")
    course = _create_course(client, headers)
    listed = client.get("/api/prep/courses", headers=headers).json()
    assert any(c["id"] == course["id"] for c in listed)
    # 非成员不可见
    other = _register_login(client, "t2", "teacher")
    assert client.get(f"/api/prep/courses/{course['id']}", headers=other).status_code == 403
    # 添加协作者后可见
    resp = client.post("/api/auth/login", json={"username": "t2", "password": "pass123456"})
    uid2 = resp.json()["user"]["id"]
    assert client.post(f"/api/prep/courses/{course['id']}/collaborators",
                       json={"user_id": uid2}, headers=headers).status_code == 200
    assert client.get(f"/api/prep/courses/{course['id']}", headers=other).status_code == 200


def test_generate_endpoint_mocks_gateway_and_uses_resources(client, db, tmp_path, monkeypatch):
    from app.config import settings
    from app.services import prep_generator
    from app.services.prep_resources import search_resources
    # 上传目录与检索目录统一指向测试临时目录（API 端点内用 settings.upload_dir）
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    headers = _register_login(client, "t3", "teacher")
    course = _create_course(client, headers)
    # 上传课程资源（真实 docx）
    doc = Document()
    doc.add_paragraph("梯度下降通过沿负梯度方向迭代更新参数逼近最优解。")
    doc.save(tmp_path / "讲义.docx")
    with open(tmp_path / "讲义.docx", "rb") as f:
        client.post(f"/api/prep/courses/{course['id']}/resources",
                    files={"file": ("讲义.docx", f, "application/octet-stream")}, headers=headers)
    # 检索资源
    hits = search_resources(course["id"], "梯度下降", settings.upload_dir, db,
                            embedder=_FakeEmb())
    assert hits and "讲义.docx" in hits[0]["ref"]
    # mock 生成网关
    fake = _FakeLLM({"标题": "教案", "教学目标": ["理解梯度下降"], "教学重点": ["迭代"],
                     "教学难点": ["学习率"], "教学过程": [{"环节": "导入", "内容": "回顾", "时长": "5分钟"}],
                     "作业": "习题", "板书设计": "公式"})
    monkeypatch.setattr(prep_generator, "get_gateway", lambda: fake)
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "plan", "chapter": "第3章", "objectives": "理解梯度下降",
                             "hours": "2课时", "query": "梯度下降"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"]["标题"] == "教案"
    assert data["citations"], "query 非空时应检索资源并返回引用"
    assert "梯度下降" in fake.calls[0]["messages"][-1]["content"]  # prompt 含课程信息


def test_lesson_save_version_restore_and_citations(client):
    headers = _register_login(client, "t4", "teacher")
    course = _create_course(client, headers)
    content_v1 = {"标题": "第一版教案", "教学目标": ["目标A"]}
    resp = client.post(f"/api/prep/courses/{course['id']}/lessons",
                       json={"title": "教案1", "lesson_type": "plan", "content_json": content_v1},
                       headers=headers)
    assert resp.status_code == 200
    lesson = resp.json()
    assert lesson["version"] == 1
    # 保存新版本
    resp = client.put(f"/api/prep/lessons/{lesson['id']}",
                      json={"content_json": {"标题": "第二版教案", "教学目标": ["目标B"]}},
                      headers=headers)
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    versions = client.get(f"/api/prep/lessons/{lesson['id']}/versions", headers=headers).json()
    assert len(versions) == 2
    # 恢复 v1
    resp = client.post(f"/api/prep/lessons/{lesson['id']}/restore", json={"version": 1}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["content_json"]["标题"] == "第一版教案"
    assert resp.json()["version"] == 3
    # 保存引用
    resp = client.post(f"/api/prep/lessons/{lesson['id']}/citations",
                       json={"ref_no": 1, "source": "教材.pdf", "page": 3, "excerpt": "梯度下降"},
                       headers=headers)
    assert resp.status_code == 200


def test_media_registration(client):
    """多媒体登记：文件先走底座 files 表，再关联到教案（media_files）。"""
    headers = _register_login(client, "t6", "teacher")
    course = _create_course(client, headers)
    lesson = client.post(f"/api/prep/courses/{course['id']}/lessons",
                         json={"title": "教案", "lesson_type": "plan",
                               "content_json": {"标题": "教案"}},
                         headers=headers).json()
    # 上传图片（底座文件服务，端点为 /api/files/upload）
    import io
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    resp = client.post("/api/files/upload", files={"file": ("图片.png", io.BytesIO(png_bytes), "image/png")},
                       headers=headers)
    assert resp.status_code == 200
    file_id = resp.json()["id"]
    resp = client.post(f"/api/prep/lessons/{lesson['id']}/media",
                       json={"file_id": file_id}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_export_endpoint_docx(client, tmp_path):
    headers = _register_login(client, "t5", "teacher")
    course = _create_course(client, headers)
    lesson = client.post(f"/api/prep/courses/{course['id']}/lessons",
                         json={"title": "教案", "lesson_type": "plan",
                               "content_json": {"标题": "梯度下降教案", "教学目标": ["理解梯度下降"],
                                                "教学重点": ["迭代"], "教学难点": ["学习率"],
                                                "教学过程": [{"环节": "导入", "内容": "回顾", "时长": "5分钟"}],
                                                "作业": "习题", "板书设计": "公式"}},
                         headers=headers).json()
    resp = client.get(f"/api/prep/lessons/{lesson['id']}/export?format=docx", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream") or "docx" in resp.headers["content-disposition"]
    from docx import Document as Doc
    out = tmp_path / "export.docx"
    out.write_bytes(resp.content)
    text = "\n".join(p.text for p in Doc(str(out)).paragraphs)
    assert "梯度下降教案" in text


def test_generate_missing_api_key_returns_502(client, monkeypatch):
    """评审修复：LLMError 未捕获时返回通用 500，需在路由层转 BizError(502) 友好提示。"""
    from app.services import prep_generator
    from app.services.llm_gateway import LLMError

    def _raise_llm_error(*args, **kwargs):
        raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中配置")

    headers = _register_login(client, "t7", "teacher")
    course = _create_course(client, headers)
    # 生成路径共用的 _call_json 抛 LLMError（等价于网关 _check_key 缺 key 失败）
    monkeypatch.setattr(prep_generator, "_call_json", _raise_llm_error)
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "plan", "chapter": "第3章", "objectives": "理解梯度下降"},
                       headers=headers)
    assert resp.status_code == 502
    assert "未配置 DEEPSEEK_API_KEY" in resp.json()["detail"]


def test_export_cleanup_and_invalid_format_no_temp_leak(client):
    """评审修复：导出临时目录必须随响应清理；400 格式请求不应产生临时目录。"""
    import shutil
    import tempfile
    from pathlib import Path
    tmp_root = Path(tempfile.gettempdir())
    # 先清掉历史残留（含 RED 阶段泄漏的目录），保证断言确定性
    for d in tmp_root.glob("prep_export_*"):
        shutil.rmtree(d, ignore_errors=True)
    headers = _register_login(client, "t8", "teacher")
    course = _create_course(client, headers)
    lesson = client.post(f"/api/prep/courses/{course['id']}/lessons",
                         json={"title": "教案", "lesson_type": "plan",
                               "content_json": {"标题": "梯度下降教案", "教学目标": ["理解梯度下降"]}},
                         headers=headers).json()
    resp = client.get(f"/api/prep/lessons/{lesson['id']}/export?format=docx", headers=headers)
    assert resp.status_code == 200
    assert resp.content  # 完整读取响应体，随后 BackgroundTask 执行清理
    leftovers = list(tmp_root.glob("prep_export_*"))
    assert not leftovers, f"导出后残留临时目录: {leftovers}"
    # 格式非法组合（plan × xlsx）→ 400，且不产生临时目录
    resp = client.get(f"/api/prep/lessons/{lesson['id']}/export?format=xlsx", headers=headers)
    assert resp.status_code == 400
    leftovers = list(tmp_root.glob("prep_export_*"))
    assert not leftovers, f"400 请求不应产生临时目录: {leftovers}"


def test_add_collaborator_validates_user_and_role(client):
    """评审修复：仅 teacher/admin 可被添加为协作者，目标用户必须存在（防角色旁路）。"""
    owner = _register_login(client, "t9", "teacher")
    course = _create_course(client, owner)
    # student 不可被添加（否则获得成员读写权限，绕过"只读"约束）
    _register_login(client, "stu9", "student")
    stu_id = client.post("/api/auth/login", json={"username": "stu9",
                                                  "password": "pass123456"}).json()["user"]["id"]
    resp = client.post(f"/api/prep/courses/{course['id']}/collaborators",
                       json={"user_id": stu_id}, headers=owner)
    assert resp.status_code == 400
    # counselor 不参与本模块，同样不可被添加
    _register_login(client, "cou9", "counselor")
    cou_id = client.post("/api/auth/login", json={"username": "cou9",
                                                  "password": "pass123456"}).json()["user"]["id"]
    resp = client.post(f"/api/prep/courses/{course['id']}/collaborators",
                       json={"user_id": cou_id}, headers=owner)
    assert resp.status_code == 400
    # 不存在的用户 → 404
    resp = client.post(f"/api/prep/courses/{course['id']}/collaborators",
                       json={"user_id": 999999}, headers=owner)
    assert resp.status_code == 404


class _FakeEmb:
    dim = 3

    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]


class _FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, messages, temperature=0.3):
        self.calls.append({"messages": messages, "temperature": temperature})
        return self.result
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_api.py -v`
Expected: FAIL（ModuleNotFoundError: app.api.prep）

- [ ] **Step 3: 实现 API 路由** `backend/app/api/prep.py`

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课接口：课程管理/生成/保存版本/资源检索引用/多媒体/导出。"""
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..config import settings
from ..core.exceptions import BizError
from ..db import get_db
from ..models.prep import Citation, Course, Lesson, MediaFile, VersionSnapshot
from ..models.user import Role, User
from ..services import prep_export, prep_generator, prep_resources
from ..services.llm_gateway import LLMError
from .deps import get_current_user

router = APIRouter()

# ---------- 权限辅助 ----------


def _require_teacher(user: User) -> None:
    if user.role not in (Role.teacher, Role.admin):
        raise BizError(403, "仅教师或管理员可操作备课模块")


def _get_course(course_id: int, user: User, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise BizError(404, "课程不存在")
    if user.role == Role.admin or user.id == course.owner_id or user.id in (course.member_ids or []):
        return course
    raise BizError(403, "无权访问该课程")


# ---------- 课程 ----------


class CourseIn(BaseModel):
    name: str
    subject: str = "人工智能"
    description: str = ""


class CollaboratorIn(BaseModel):
    user_id: int


@router.post("/courses")
def create_course(data: CourseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_teacher(user)
    course = Course(name=data.name, subject=data.subject, description=data.description, owner_id=user.id)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/courses")
def list_courses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        c for c in db.query(Course).order_by(Course.id.desc()).all()
        if user.role == Role.admin or user.id == c.owner_id or user.id in (c.member_ids or [])
    ]


@router.get("/courses/{course_id}")
def get_course(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_course(course_id, user, db)


@router.post("/courses/{course_id}/collaborators")
def add_collaborator(course_id: int, data: CollaboratorIn,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _get_course(course_id, user, db)
    if user.id != course.owner_id and user.role != Role.admin:
        raise BizError(403, "仅课程创建者可添加协作者")
    target = db.get(User, data.user_id)
    if target is None:
        raise BizError(404, "用户不存在")
    if target.role not in (Role.teacher, Role.admin):
        raise BizError(400, "仅教师或管理员可被添加为协作者（该用户角色无备课模块权限）")
    members = list(course.member_ids or [])
    if data.user_id not in members:
        members.append(data.user_id)
        course.member_ids = members
        db.commit()
    return {"ok": True, "member_ids": members}


# ---------- 资源检索 ----------


@router.post("/courses/{course_id}/resources")
def upload_resource(course_id: int, file: UploadFile = File(...),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_course(course_id, user, db)
    record = prep_resources.add_resource(course_id, file, settings.upload_dir, db)
    return {"id": record.id, "filename": record.filename}


@router.get("/courses/{course_id}/search")
def search_course_resources(course_id: int, q: str = Query(...), top_k: int = 5,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_course(course_id, user, db)
    hits = prep_resources.search_resources(course_id, q, settings.upload_dir, db, top_k=top_k)
    return {"hits": [{"ref": h["ref"], "score": h["score"], "excerpt": h["chunk"].text[:200],
                      "source": h["chunk"].source, "page": h["chunk"].page} for h in hits]}


# ---------- 生成 ----------


class GenerateIn(BaseModel):
    type: str                     # plan|cw|exercises|case|exam
    chapter: str = ""
    objectives: str = ""
    hours: str = ""
    knowledge_points: list[str] = []
    count: int = 5
    distribution: list[dict] = []  # 月考题：[{"知识点": str, "占比": str}]
    query: str = ""               # 非空时先检索校本资源拼入 prompt


def _collect_resources(course_id: int, query: str, db: Session) -> tuple[str, list[dict]]:
    """检索校本资源并拼成 prompt 上下文；返回 (resources 文本, 引用列表)。"""
    if not query:
        return "", []
    hits = prep_resources.search_resources(course_id, query, settings.upload_dir, db, top_k=3)
    return "\n".join(f"{h['ref']}\n{h['chunk'].text[:300]}" for h in hits), \
        [{"ref_no": i, "source": h["chunk"].source, "page": h["chunk"].page,
          "excerpt": h["chunk"].text[:200]} for i, h in enumerate(hits, start=1)]


@router.post("/courses/{course_id}/generate")
def generate(course_id: int, data: GenerateIn,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _get_course(course_id, user, db)
    resources, citations = _collect_resources(course_id, data.query, db)
    try:
        if data.type == "plan":
            content = prep_generator.generate_lesson_plan(
                course.name, course.subject, data.chapter, data.objectives, data.hours, resources)
            prep_generator.validate_lesson_plan(content)
        elif data.type == "cw":
            content = prep_generator.generate_courseware(
                course.name, course.subject, data.chapter, data.objectives, data.hours, resources)
            prep_generator.validate_courseware(content)
        elif data.type == "exercises":
            content = prep_generator.generate_exercises(
                course.name, course.subject, data.chapter, data.knowledge_points, data.count, resources)
            prep_generator.validate_exercises(content)
        elif data.type == "case":
            content = prep_generator.generate_case(
                course.name, course.subject, data.chapter, data.objectives, resources)
            prep_generator.validate_case(content)
        elif data.type == "exam":
            content = prep_generator.generate_monthly_exam(
                course.name, course.subject, data.distribution or [{"知识点": data.chapter, "占比": "100%"}], resources)
            prep_generator.validate_exam(content)
        else:
            raise BizError(400, "不支持的生成类型（plan/cw/exercises/case/exam）")
    except LLMError as exc:
        # DeepSeek key 未配置/调用失败 → 友好 502（评审修复：原先落通用 500）
        raise BizError(502, str(exc)) from exc
    return {"type": data.type, "content": content, "citations": citations}


# ---------- 教案/课件保存与版本 ----------


class LessonIn(BaseModel):
    title: str
    lesson_type: str            # plan|cw|exercises|case|exam
    content_json: dict


class LessonUpdateIn(BaseModel):
    content_json: dict


class CitationIn(BaseModel):
    ref_no: int
    source: str
    page: int | None = None
    excerpt: str = ""


class MediaIn(BaseModel):
    file_id: int


class RestoreIn(BaseModel):
    version: int


def _snapshot(lesson: Lesson, user: User, db: Session) -> None:
    db.add(VersionSnapshot(lesson_id=lesson.id, version=lesson.version,
                           content_json=lesson.content_json, created_by=user.id))


@router.get("/courses/{course_id}/lessons")
def list_course_lessons(course_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """课程教案/课件列表（前端课程详情页）。"""
    _get_course(course_id, user, db)
    return db.query(Lesson).filter(Lesson.course_id == course_id).order_by(Lesson.id.desc()).all()


@router.post("/courses/{course_id}/lessons")
def create_lesson(course_id: int, data: LessonIn,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_course(course_id, user, db)
    if data.lesson_type not in ("plan", "cw", "exercises", "case", "exam"):
        raise BizError(400, "不支持的教案类型（plan/cw/exercises/case/exam）")
    lesson = Lesson(course_id=course_id, title=data.title, lesson_type=data.lesson_type,
                    content_json=data.content_json, created_by=user.id)
    db.add(lesson)
    db.flush()
    _snapshot(lesson, user, db)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    return lesson


@router.put("/lessons/{lesson_id}")
def update_lesson(lesson_id: int, data: LessonUpdateIn,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    lesson.version += 1
    lesson.content_json = data.content_json
    _snapshot(lesson, user, db)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.get("/lessons/{lesson_id}/versions")
def list_versions(lesson_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    snaps = (db.query(VersionSnapshot).filter(VersionSnapshot.lesson_id == lesson_id)
             .order_by(VersionSnapshot.version.desc()).all())
    return [{"version": s.version, "created_by": s.created_by, "created_at": str(s.created_at),
             "content_json": s.content_json} for s in snaps]


@router.post("/lessons/{lesson_id}/restore")
def restore_lesson(lesson_id: int, data: RestoreIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    snap = (db.query(VersionSnapshot).filter(VersionSnapshot.lesson_id == lesson_id,
                                             VersionSnapshot.version == data.version).first())
    if snap is None:
        raise BizError(404, "该版本不存在")
    lesson.version += 1
    lesson.content_json = snap.content_json
    _snapshot(lesson, user, db)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.post("/lessons/{lesson_id}/citations")
def save_citations(lesson_id: int, data: CitationIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    db.add(Citation(lesson_id=lesson_id, ref_no=data.ref_no, source=data.source,
                    page=data.page, excerpt=data.excerpt))
    db.commit()
    return {"ok": True}


@router.post("/lessons/{lesson_id}/media")
def add_media(lesson_id: int, data: MediaIn,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """登记插入教案的多媒体文件（文件本体走底座 files 表）。"""
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    db.add(MediaFile(lesson_id=lesson_id, file_id=data.file_id))
    db.commit()
    return {"ok": True}


# ---------- 导出 ----------


@router.get("/lessons/{lesson_id}/export")
def export_lesson(lesson_id: int, format: str = Query("docx"),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "教案不存在")
    _get_course(lesson.course_id, user, db)
    content = lesson.content_json or {}
    # 导出映射（Global Constraints）：docx←plan/case，pptx←cw，pdf←exercises/exam
    if format not in ("docx", "pptx", "pdf"):
        raise BizError(400, "不支持的导出格式（docx/pptx/pdf）")
    if not ((format == "docx" and lesson.lesson_type in ("plan", "case"))
            or (format == "pptx" and lesson.lesson_type == "cw")
            or (format == "pdf" and lesson.lesson_type in ("exercises", "exam"))):
        raise BizError(400, "该教案类型不支持此导出格式")
    # 格式校验通过后才建临时目录；响应完成后由 BackgroundTask 清理（评审修复：防临时目录泄漏）
    tmp = Path(tempfile.mkdtemp(prefix="prep_export_"))
    out_path = tmp / f"{lesson.title}.{format}"
    if format == "docx":
        if lesson.lesson_type == "case":
            out = prep_export.export_case_docx(content, out_path)
        else:
            out = prep_export.export_lesson_docx(content, out_path)
    elif format == "pptx":
        out = prep_export.export_courseware_pptx(content, out_path)
    else:
        exercises = content.get("习题", []) if lesson.lesson_type == "exercises" \
            else [q for s in content.get("大题", []) for q in s.get("题目", [])]
        out = prep_export.export_exercises_pdf(exercises, lesson.title, out_path)
    return FileResponse(str(out), filename=out.name,
                        media_type="application/octet-stream",
                        background=BackgroundTask(shutil.rmtree, tmp))
```

修改 `backend/app/main.py`，在 files 挂载后加：

```python
from .api import auth, files, prep  # 顶部 import 区追加 prep

app.include_router(prep.router, prefix="/api/prep", tags=["prep"])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_api.py -v`
Expected: PASS（9 passed）

- [ ] **Step 5: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add backend/app/api/prep.py backend/app/main.py backend/tests/test_prep_api.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 备课API路由（课程/生成/版本/引用/导出，工单17）"
```

---

### Task 6: 前端备课页面（课程/生成/编辑器/版本/导出）

**Files:**
- Modify: `frontend/package.json`（新增依赖 @wangeditor/editor、@wangeditor/editor-for-vue）
- Create: `frontend/src/api/prep.ts`
- Create: `frontend/src/views/prep/PrepListView.vue`
- Create: `frontend/src/views/prep/PrepCourseView.vue`
- Create: `frontend/src/views/prep/PrepEditorView.vue`
- Modify: `frontend/src/router/index.ts`（新增 /prep、/prep/course/:id、/prep/lesson/:id）
- Modify: `frontend/src/views/HomeView.vue`（菜单"智能备课"指向 /prep）

**Interfaces:**
- Consumes: 后端 `/api/prep/*`（本计划 Task 5）；`api/http.ts`、`stores/auth.ts`（Plan A Task 10）
- Produces: 前端页面：课程列表（新建/协作者）、课程详情（资源上传/检索/四种生成/保存）、教案编辑器（wangeditor/引用插入/版本历史/导出）。Plan D（工单19）复用习题展示。

- [ ] **Step 1: 新增依赖与 API 封装**

`frontend/package.json` 的 dependencies 追加：

```json
"@wangeditor/editor": "^5.1.23",
"@wangeditor/editor-for-vue": "^5.1.12"
```

`frontend/src/api/prep.ts`：

```ts
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
import http from './http'

export interface Course { id: number; name: string; subject: string; description: string; owner_id: number; member_ids: number[] }
export interface Lesson { id: number; course_id: number; title: string; lesson_type: string; content_json: any; version: number }
export interface SearchHit { ref: string; score: number; excerpt: string; source: string; page: number | null }

export const createCourse = (data: Partial<Course>) => http.post('/prep/courses', data)
export const listCourses = () => http.get('/prep/courses')
export const getCourse = (id: number) => http.get(`/prep/courses/${id}`)
export const addCollaborator = (courseId: number, userId: number) =>
  http.post(`/prep/courses/${courseId}/collaborators`, { user_id: userId })
export const uploadResource = (courseId: number, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post(`/prep/courses/${courseId}/resources`, form)
}
export const searchResources = (courseId: number, q: string, topK = 5) =>
  // bge-m3 冷启动首查需 30~60s，覆盖全局 30s 超时（终审修复）
  http.get(`/prep/courses/${courseId}/search`, { params: { q, top_k: topK }, timeout: 120000 }) as Promise<{ hits: SearchHit[] }>
export const generateContent = (courseId: number, data: any) =>
  http.post(`/prep/courses/${courseId}/generate`, data)
export const createLesson = (courseId: number, data: Partial<Lesson>) =>
  http.post(`/prep/courses/${courseId}/lessons`, data)
export const listCourseLessons = (courseId: number) =>
  http.get(`/prep/courses/${courseId}/lessons`)
export const getLesson = (id: number) => http.get(`/prep/lessons/${id}`)
export const updateLesson = (id: number, contentJson: any) =>
  http.put(`/prep/lessons/${id}`, { content_json: contentJson })
export const listVersions = (id: number) => http.get(`/prep/lessons/${id}/versions`)
export const restoreLesson = (id: number, version: number) =>
  http.post(`/prep/lessons/${id}/restore`, { version })
export const addLessonMedia = (lessonId: number, fileId: number) =>
  http.post(`/prep/lessons/${lessonId}/media`, { file_id: fileId })
export const uploadFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/files/upload', form) as Promise<{ id: number; filename: string }>
}
export const exportLessonUrl = (id: number, format: string) =>
  `/api/prep/lessons/${id}/export?format=${format}`

/** 教案类型中文名（列表展示用）。 */
export const LESSON_TYPE_LABELS: Record<string, string> = {
  plan: '教案', cw: '课件大纲', exercises: '习题集', case: '教学案例', exam: '月考试题',
}
```

- [ ] **Step 2: 课程列表页** `frontend/src/views/prep/PrepListView.vue`

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>智能备课 · 我的课程</h2>
      <el-button type="primary" @click="dialogVisible = true">新建课程</el-button>
    </div>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col v-for="c in courses" :key="c.id" :span="8">
        <el-card @click="$router.push(`/prep/course/${c.id}`)" style="cursor: pointer; margin-bottom: 16px">
          <h3>{{ c.name }}</h3>
          <p style="color: #666">{{ c.subject }} · {{ c.description || '暂无描述' }}</p>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-if="!courses.length" description="还没有课程，点击右上角新建" />

    <el-dialog v-model="dialogVisible" title="新建课程" width="420px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="课程名"><el-input v-model="form.name" placeholder="如：人工智能导论" /></el-form-item>
        <el-form-item label="学科"><el-input v-model="form.subject" placeholder="人工智能" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createCourse, listCourses, type Course } from '@/api/prep'

const courses = ref<Course[]>([])
const dialogVisible = ref(false)
const creating = ref(false)
const form = reactive({ name: '', subject: '人工智能', description: '' })

async function load() {
  courses.value = (await listCourses()) as Course[]
}

async function onCreate() {
  if (!form.name) { ElMessage.warning('请填写课程名'); return }
  creating.value = true
  try {
    await createCourse(form)
    dialogVisible.value = false
    form.name = ''; form.description = ''
    await load()
  } finally { creating.value = false }
}

onMounted(load)
</script>
```

- [ ] **Step 3: 课程详情页（资源+生成）** `frontend/src/views/prep/PrepCourseView.vue`

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <el-page-header :content="course?.name || '课程'" @back="$router.push('/prep')" />
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="10">
        <el-card>
          <template #header>校本资源（用于生成时引用）</template>
          <el-upload :show-file-list="false" :http-request="onUpload">
            <el-button>上传资源文件（docx/pptx/xlsx/pdf）</el-button>
          </el-upload>
          <el-input v-model="searchQ" placeholder="检索资源，如：梯度下降" style="margin-top: 12px">
            <template #append><el-button :loading="searching" @click="onSearch">检索</el-button></template>
          </el-input>
          <div v-for="h in searchHits" :key="h.ref" style="margin-top: 10px; font-size: 13px">
            <div><b>{{ h.ref }}</b> <el-tag size="small">{{ h.score }}</el-tag></div>
            <div style="color: #666">{{ h.excerpt }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card>
          <template #header>AI 生成</template>
          <el-form label-width="90px">
            <el-form-item label="生成类型">
              <el-radio-group v-model="genForm.type">
                <el-radio-button value="plan">教案</el-radio-button>
                <el-radio-button value="cw">课件大纲</el-radio-button>
                <el-radio-button value="exercises">习题</el-radio-button>
                <el-radio-button value="case">案例</el-radio-button>
                <el-radio-button value="exam">月考试题</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="章节"><el-input v-model="genForm.chapter" placeholder="如：第3章 机器学习基础" /></el-form-item>
            <el-form-item label="教学目标"><el-input v-model="genForm.objectives" type="textarea" /></el-form-item>
            <el-form-item label="课时"><el-input v-model="genForm.hours" placeholder="2课时" /></el-form-item>
            <el-form-item v-if="genForm.type === 'exercises'" label="知识点">
              <el-input v-model="genForm.knowledgePoints" placeholder="用、分隔：梯度下降、线性回归" />
            </el-form-item>
            <el-form-item v-if="genForm.type === 'exam'" label="知识点分布">
              <el-input v-model="genForm.distribution" placeholder="梯度下降:30%、线性回归:30%（知识点:占比 换行分隔）" type="textarea" />
            </el-form-item>
            <el-form-item label="引用资源">
              <el-input v-model="genForm.query" placeholder="留空不检索；填写关键词将检索校本资源并标注引用" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="generating" @click="onGenerate">生成初稿</el-button>
          <div v-if="result" style="margin-top: 16px">
            <h4>生成结果（{{ result.type }}）</h4>
            <pre style="background: #f5f7fa; padding: 12px; max-height: 300px; overflow: auto">{{ JSON.stringify(result.content, null, 2) }}</pre>
            <el-input v-model="lessonTitle" placeholder="保存为教案标题" style="margin-top: 8px; width: 300px" />
            <el-button type="success" @click="onSave">保存为教案/课件</el-button>
            <div v-if="result.citations?.length" style="margin-top: 8px">
              <el-tag v-for="c in result.citations" :key="c.ref_no" style="margin-right: 6px">
                [{{ c.ref_no }}] 来源：{{ c.source }}{{ c.page ? ` 第${c.page}页` : '' }}
              </el-tag>
            </div>
          </div>
        </el-card>
        <el-card style="margin-top: 16px">
          <template #header>本课程教案/课件</template>
          <el-table :data="lessons" @row-click="(row: any) => $router.push(`/prep/lesson/${row.id}`)">
            <el-table-column prop="title" label="标题" />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">{{ LESSON_TYPE_LABELS[row.lesson_type] || row.lesson_type }}</template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="80" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createLesson, generateContent, getCourse, LESSON_TYPE_LABELS, listCourseLessons,
  searchResources, uploadResource, type Course,
} from '@/api/prep'

const route = useRoute()
const courseId = Number(route.params.id)
const course = ref<Course | null>(null)
const searchQ = ref('')
const searchHits = ref<any[]>([])
const searching = ref(false)
const genForm = reactive({ type: 'plan', chapter: '', objectives: '', hours: '', knowledgePoints: '', distribution: '', query: '' })
const generating = ref(false)
const result = ref<any>(null)
const lessonTitle = ref('')
const lessons = ref<any[]>([])

async function load() {
  course.value = (await getCourse(courseId)) as Course
  lessons.value = (await listCourseLessons(courseId)) as any[]
}

async function onUpload(opt: any) {
  await uploadResource(courseId, opt.file)
  ElMessage.success('资源已上传')
}

async function onSearch() {
  if (!searchQ.value) return
  searching.value = true
  try {
    const data = await searchResources(courseId, searchQ.value)
    searchHits.value = data.hits
  } finally {
    searching.value = false
  }
}

async function onGenerate() {
  generating.value = true
  try {
    const payload: any = {
      type: genForm.type, chapter: genForm.chapter, objectives: genForm.objectives,
      hours: genForm.hours, query: genForm.query,
    }
    if (genForm.type === 'exercises') {
      payload.knowledge_points = genForm.knowledgePoints.split(/[、,，]/).filter(Boolean)
    }
    if (genForm.type === 'exam' && genForm.distribution.trim()) {
      payload.distribution = genForm.distribution.split('\n').filter(Boolean).map((line) => {
        const [kp, pct] = line.split(/[:：]/)
        return { '知识点': kp.trim(), '占比': (pct || '').trim() }
      })
    }
    result.value = await generateContent(courseId, payload)
    lessonTitle.value = result.value.content['标题'] || result.value.content['试卷标题'] || '未命名'
  } finally { generating.value = false }
}

async function onSave() {
  if (!lessonTitle.value) { ElMessage.warning('请填写标题'); return }
  await createLesson(courseId, { title: lessonTitle.value, lesson_type: genForm.type, content_json: result.value.content })
  ElMessage.success('已保存')
  await load()
}

onMounted(load)
</script>
```

（`listCourseLessons` 后端补充：Task 5 的 `GET /courses/{id}` 响应外，加 `GET /courses/{course_id}/lessons` 端点——见下方 Task 5 补丁说明。）

- [ ] **Step 4: 教案编辑器页** `frontend/src/views/prep/PrepEditorView.vue`

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17) -->
<template>
  <div>
    <el-page-header :content="lesson?.title || '教案编辑'" @back="$router.push(`/prep/course/${lesson?.course_id}`)" />
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="17">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>内容编辑</span>
              <div>
                <!-- 导出按钮按教案类型显示（后端映射：docx←plan/case，pptx←cw，pdf←exercises/exam） -->
                <el-button v-if="['plan', 'case'].includes(lesson?.lesson_type || '')" @click="onExport('docx')">导出 Word</el-button>
                <el-button v-if="lesson?.lesson_type === 'cw'" @click="onExport('pptx')">导出 PPT</el-button>
                <el-button v-if="['exercises', 'exam'].includes(lesson?.lesson_type || '')" @click="onExport('pdf')">导出 PDF</el-button>
                <el-button type="primary" :loading="saving" @click="onSave">保存（新版本）</el-button>
              </div>
            </div>
          </template>
          <div style="border: 1px solid #ccc">
            <Toolbar style="border-bottom: 1px solid #ccc" :editor="editorRef" :default-config="toolbarConfig" />
            <Editor style="height: 480px; overflow-y: hidden" v-model="html" :default-config="editorConfig" @on-created="onCreated" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card>
          <template #header>资源引用（检索后一键插入）</template>
          <el-input v-model="refQuery" placeholder="检索课程资源">
            <template #append><el-button :loading="refSearching" @click="onRefSearch">检索</el-button></template>
          </el-input>
          <div v-for="h in refHits" :key="h.ref" style="margin-top: 10px; font-size: 13px">
            <div><b>{{ h.ref }}</b></div>
            <div style="color: #666">{{ h.excerpt }}</div>
            <el-button size="small" type="text" @click="onInsertRef(h)">插入正文</el-button>
          </div>
        </el-card>
        <el-card style="margin-top: 16px">
          <template #header>版本历史</template>
          <el-timeline>
            <el-timeline-item v-for="v in versions" :key="v.version" :timestamp="`v${v.version}`">
              <el-button size="small" @click="onRestore(v.version)">恢复此版本</el-button>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import '@wangeditor/editor/dist/css/style.css'
import {
  addLessonMedia, exportLessonUrl, getLesson, listVersions, restoreLesson,
  searchResources, updateLesson, uploadFile, type Lesson,
} from '@/api/prep'

const route = useRoute()
const lessonId = Number(route.params.id)
const lesson = ref<Lesson | null>(null)
const html = ref('')
const saving = ref(false)
const versions = ref<any[]>([])
const refQuery = ref('')
const refHits = ref<any[]>([])
const refSearching = ref(false)

const editorRef = shallowRef()
const toolbarConfig = { excludeKeys: ['group-video'] }
const editorConfig = {
  placeholder: '在此编辑内容……',
  MENU_CONF: {
    // 插入多媒体：图片 base64 嵌入编辑器展示 + 底座 files 表落盘 + media_files 登记
    uploadImage: {
      async customUpload(file: File, insertFn: (url: string, alt: string, href: string) => void) {
        const reader = new FileReader()
        reader.onload = async () => {
          const base64 = reader.result as string
          insertFn(base64, file.name, base64)          // 编辑器内嵌展示（免鉴权加载）
          try {
            const record = await uploadFile(file)      // 底座文件服务落盘
            await addLessonMedia(lessonId, record.id)  // media_files 登记
            ElMessage.success('图片已上传并登记')
          } catch { ElMessage.warning('图片已插入编辑器，但服务器登记失败') }
        }
        reader.readAsDataURL(file)
      },
    },
  },
}

function onCreated(editor: any) { editorRef.value = editor }

async function load() {
  lesson.value = (await getLesson(lessonId)) as Lesson
  html.value = lesson.value.content_json?.html || jsonToHtml(lesson.value.content_json)
  versions.value = (await listVersions(lessonId)) as any[]
}

/** 结构化 JSON 初稿 → HTML（生成结果进入编辑器的展示渲染）。 */
function jsonToHtml(data: any): string {
  if (!data) return ''
  if (typeof data === 'string') return data
  const parts: string[] = []
  if (data['标题'] || data['试卷标题']) parts.push(`<h1>${data['标题'] || data['试卷标题']}</h1>`)
  for (const key of ['教学目标', '教学重点', '教学难点']) {
    if (Array.isArray(data[key])) parts.push(`<h3>${key}</h3><ul>${data[key].map((x: string) => `<li>${x}</li>`).join('')}</ul>`)
  }
  if (Array.isArray(data['教学过程'])) {
    parts.push('<h3>教学过程</h3><table border="1" cellpadding="4">' +
      data['教学过程'].map((s: any) => `<tr><td>${s['环节']}（${s['时长']}）</td><td>${s['内容']}</td></tr>`).join('') + '</table>')
  }
  if (data['作业']) parts.push(`<h3>作业</h3><p>${data['作业']}</p>`)
  if (data['板书设计']) parts.push(`<h3>板书设计</h3><p>${data['板书设计']}</p>`)
  for (const key of ['案例背景', '案例描述', '问题', '案例分析', '结论']) {
    if (data[key]) parts.push(`<h3>${key}</h3><p>${data[key]}</p>`)
  }
  if (Array.isArray(data['幻灯片'])) {
    parts.push(data['幻灯片'].map((s: any) => `<h3>${s['标题']}</h3><ul>${(s['要点'] || []).map((x: string) => `<li>${x}</li>`).join('')}</ul>`).join(''))
  }
  if (Array.isArray(data['习题'])) {
    parts.push('<h3>习题</h3>' + data['习题'].map((e: any, i: number) =>
      `<p>${i + 1}. ${e['题干']}</p><p>${(e['选项'] || []).join('<br>')}</p><p>答案：${e['答案']}　知识点：${e['知识点']}（${e['难度']}）</p>`).join(''))
  }
  if (Array.isArray(data['大题'])) {
    parts.push(data['大题'].map((s: any) =>
      `<h3>${s['题型']}（${s['知识点']}）</h3>` + (s['题目'] || []).map((q: any, i: number) =>
        `<p>${i + 1}. ${q['题干']}</p><p>答案：${q['答案']}</p>`).join('')).join(''))
  }
  return parts.join('')
}

async function onRefSearch() {
  if (!refQuery.value || !lesson.value) return
  refSearching.value = true
  try {
    const data = await searchResources(lesson.value.course_id, refQuery.value)
    refHits.value = data.hits
  } finally {
    refSearching.value = false
  }
}

function onInsertRef(h: any) {
  editorRef.value?.restoreSelection()
  editorRef.value?.insertText(h.ref)
  ElMessage.success('已插入正文')
}

async function onSave() {
  saving.value = true
  try {
    await updateLesson(lessonId, { ...(lesson.value?.content_json || {}), html: html.value })
    ElMessage.success('已保存新版本')
    await load()
  } finally { saving.value = false }
}

function onExport(format: string) {
  window.open(exportLessonUrl(lessonId, format))
}

async function onRestore(version: number) {
  await restoreLesson(lessonId, version)
  ElMessage.success('已恢复')
  await load()
}

onMounted(load)
onBeforeUnmount(() => { editorRef.value?.destroy() })
</script>
```

- [ ] **Step 5: 路由与菜单修改**

`frontend/src/router/index.ts` 的 routes 追加：

```ts
{ path: '/prep', component: () => import('@/views/prep/PrepListView.vue') },
{ path: '/prep/course/:id', component: () => import('@/views/prep/PrepCourseView.vue') },
{ path: '/prep/lesson/:id', component: () => import('@/views/prep/PrepEditorView.vue') },
```

`frontend/src/views/HomeView.vue` 菜单项 `<el-menu-item index="/module/prep">智能备课</el-menu-item>` 改为：

```vue
<el-menu-item index="/prep">智能备课</el-menu-item>
```

- [ ] **Step 6: 安装依赖并构建验证**

Run: `cd frontend && npm install && npm run build`
Expected: 构建成功无报错（既有 chunk >500kB 警告可忽略）

- [ ] **Step 7: 端到端 curl 验证（后端需运行中）**

1. `cd backend && python -m uvicorn app.main:app --port 8000`（后台）
2. `curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"teacher","password":"teacher123"}'` → 拿 token（若 teacher 不存在先跑 `python -m scripts.seed_demo_data`）
3. `curl -X POST http://localhost:8000/api/prep/courses -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name":"人工智能导论","subject":"人工智能"}'` → 返回课程 JSON
4. 上传演示资源：`curl -X POST http://localhost:8000/api/prep/courses/1/resources -H "Authorization: Bearer <token>" -F "file=@backend/data/demo/人工智能导论讲义.docx"` → 返回文件记录
5. `curl "http://localhost:8000/api/prep/courses/1/search?q=梯度下降" -H "Authorization: Bearer <token>"` → hits 非空（首次会加载 bge-m3，约 30~60 秒）
6. 生成接口在无 DEEPSEEK_API_KEY 时返回 500（detail 为"服务器内部错误"，后端日志含 LLMError"未配置 DEEPSEEK_API_KEY"）——预期行为（如实记录；有 key 时返回结构化 JSON）
7. 验证完毕停掉后端进程

Expected: 1~5 全部通过；浏览器步骤（页面交互/编辑器/导出下载）留待用户人工验证，清单写入报告。

- [ ] **Step 8: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add frontend/
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat: 备课前端（课程/生成/富文本编辑器/引用/版本/导出，工单17）"
```

---

### Task 7: 工单17 测试用例文档 + 演示数据 + 收尾

**Files:**
- Create: `docs/工单17-智能备课-测试用例与结果.md`
- Modify: `backend/scripts/seed_demo_data.py`（预置备课演示数据）
- Modify: 根目录 `README.md`（工单17 状态与演示步骤）

**Interfaces:**
- Consumes: 本计划 Task 1~6 全部
- Produces: 工单 17 验收要求的测试用例文档（含结果）；演示数据：teacher 账号预置课程"人工智能导论"并把 seed 的 4 个演示文件登记为课程资源（无需向量化——资源检索实时解析）；README 演示步骤。

- [ ] **Step 1: 扩展演示数据脚本**

`backend/scripts/seed_demo_data.py` 的 `main` 区（`seed_users(db)` 之后、打印账号之前）追加：

```python
from app.models.prep import Course, CourseFile
from app.models.file import FileRecord
from app.services.file_service import save_upload


def seed_prep_demo(db) -> None:
    """备课演示数据：teacher 预置课程 + 演示文件登记为课程资源。"""
    teacher = db.query(User).filter(User.username == "teacher").first()
    if teacher is None:
        return
    course = db.query(Course).filter(Course.name == "人工智能导论").first()
    if course is None:
        course = Course(name="人工智能导论", subject="人工智能",
                        description="高职人工智能课程（演示数据）", owner_id=teacher.id)
        db.add(course)
        db.commit()
        db.refresh(course)
    # 演示文件登记为课程资源（资源检索实时解析，无需向量化）
    demo_files = ["人工智能导论讲义.docx", "机器学习课件.pptx", "诊断试题.xlsx", "人工智能导论教材.pdf"]
    for name in demo_files:
        if not db.query(FileRecord).filter(FileRecord.filename == name).first():
            from fastapi import UploadFile
            import io
            path = DEMO_DIR / name
            if path.exists():
                with open(path, "rb") as f:
                    record = save_upload(
                        UploadFile(filename=name, file=io.BytesIO(f.read())),
                        owner_id=0, upload_dir=str(DEMO_DIR.parent.parent / "uploads"), db=db,
                    )
                db.add(CourseFile(course_id=course.id, file_id=record.id))
    db.commit()
    print("备课演示数据已就绪：课程「人工智能导论」+ 4 个课程资源文件")
```

`main` 中调用：`seed_users(db)` 后加 `seed_prep_demo(db)`。

- [ ] **Step 2: 运行验证**

Run: `cd backend && python -m scripts.seed_demo_data`
Expected: 打印"备课演示数据已就绪"；重复运行幂等（课程不重复创建）

- [ ] **Step 3: 撰写测试用例文档** `docs/工单17-智能备课-测试用例与结果.md`

内容（用实际运行结果填写"结果"列）：

```markdown
# 工单17 智能备课——测试用例与结果

> 测试范围：备课数据模型、生成服务、资源检索、导出服务、API 路由（前端以 build + 手动清单验证）。
> 运行方式：`cd backend && python -m pytest -q`；日期与结果列在测试完成后填写。

## 一、后端自动化测试用例

| 编号 | 用例 | 前置 | 步骤 | 预期 | 结果 |
|---|---|---|---|---|---|
| P01 | 课程创建/查询 | teacher 登录 | POST /api/prep/courses → GET /courses | 200，列表含新课程 | |
| P02 | 学生创建课程被拒 | student 登录 | POST /api/prep/courses | 403 | |
| P03 | 非成员访问课程被拒 | teacher2 登录 | GET /courses/{id} | 403 | |
| P04 | 添加协作者后可见 | teacher2 被加入 | GET /courses/{id} | 200 | |
| P05 | 资源上传与登记 | teacher | 上传 docx | 200，course_files +1 | |
| P06 | 资源检索命中与引用格式 | 课程含资源 | GET /courses/{id}/search?q=梯度下降 | hits 非空，ref 形如 [1] 来源：xx 第X页 | |
| P07 | 生成教案（mock LLM） | mock 网关 | POST /courses/{id}/generate type=plan | 结构化 JSON + 引用列表 | |
| P08 | 生成校验（缺字段） | mock 返回残缺 JSON | generate | BizError 502 提示 | |
| P09 | 教案保存/版本递增 | 教案 v1 | PUT /lessons/{id} | version=2，快照+1 | |
| P10 | 版本恢复 | 有 v1 快照 | POST /lessons/{id}/restore {version:1} | 内容回 v1，version+1 | |
| P11 | 引用保存 | lesson 存在 | POST /lessons/{id}/citations | 200，citations +1 | |
| P12 | 多媒体登记 | 文件已上传 | POST /lessons/{id}/media | 200，media_files +1 | |
| P13 | 导出 docx 内容正确 | 教案数据 | GET /lessons/{id}/export?format=docx | 文件可读回，含标题 | |
| P14 | 导出 pptx 页数正确 | 课件数据 | GET .../export?format=pptx | 幻灯片数与数据一致 | |
| P15 | 导出 pdf 中文正常 | 习题数据 | GET .../export?format=pdf | PDF 读回含中文 | |
| P16 | 生成案例（mock LLM） | mock 网关 | POST /courses/{id}/generate type=case | 六字段案例 JSON | |

## 二、前端手动功能清单（人工验证）

1. 教师登录 → 智能备课 → 课程列表 → 新建课程
2. 课程详情：上传资源 → 检索 → 生成教案（需配置 DEEPSEEK_API_KEY）→ 结果预览 → 保存
3. 打开教案 → wangeditor 编辑 → 检索资源 → 一键插入引用 → 保存（版本+1）
4. 版本历史 → 恢复旧版本
5. 导出 Word/PPT/PDF 并打开检查
6. 学生账号登录 → 访问备课接口被 403 拦截

## 三、测试结果汇总

- 后端：`python -m pytest -q` → N passed（填写实际数字）
- 前端：`npm run build` 通过；手动清单逐项结果（验收彩排时填写）
```

- [ ] **Step 4: README 更新**

`README.md` 工单对照表更新工单 17 行：`| 17 | 智能备课 | ✅ 课程/生成/编辑器/引用/导出/版本（Plan B） |`；快速启动小节后追加演示段：

```markdown
## 智能备课演示（工单17）
cd backend && python -m scripts.seed_demo_data   # 预置课程与资源
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
浏览器登录 teacher/teacher123 → 智能备课 → 人工智能导论 → 上传资源/检索引用/生成/编辑/版本/导出
（生成功能需在 backend/.env 配置 DEEPSEEK_API_KEY）
```

- [ ] **Step 5: 全量回归**

Run: `cd backend && python -m pytest -q`
Expected: 全部 PASS（Plan A 45 + 本计划新增 5+5+3+4+6 = 68 passed, 2 deselected；以实际为准）。前端 `cd frontend && npm run build` 通过。

- [ ] **Step 6: 提交**

```bash
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" add docs/工单17-智能备课-测试用例与结果.md backend/scripts/seed_demo_data.py README.md
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "docs: 工单17测试用例文档+备课演示数据+README（Plan B收尾）"
```

---

## 完成标准（Plan B）

- [ ] 后端全部测试通过（预计 68 passed, 2 deselected；smoke 排除）
- [ ] 教案/课件大纲/习题/案例/月考试题五种生成可用（LLM 网关 + JSON 校验）
- [ ] 课程资源上传 → 混合检索 → 引用标注链路可用（测试覆盖）
- [ ] 导出 Word/PPT/PDF 内容正确（读回断言），类型×格式映射守卫（测试覆盖）
- [ ] 插入多媒体：图片 base64 嵌入 + files 落盘 + media_files 登记（测试覆盖）
- [ ] 版本快照：保存递增、历史列表、恢复（测试覆盖）
- [ ] 角色权限：学生/非成员被 403 拦截（测试覆盖）
- [ ] 前端 build 通过 + 手动清单文档化（浏览器验证留待用户，验收彩排执行）
- [ ] 工单17 测试用例文档产出（验收要求）
- [ ] 每个任务已单独 commit
