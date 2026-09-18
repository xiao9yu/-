# Plan D：工单 19 个性化学习推荐（学习画像 + 知识图谱路径 + 自适应练习 + AIGC 错题本）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付工单 19 个性化学习推荐模块：学生首次登录做诊断测试（复用工单 17 试题）或导入历史成绩 → 初始画像 → 画像仪表盘（雷达图 + 推荐学习路径 + 今日任务 + 相似学生）→ 知识图谱路径推荐（未掌握知识点 + 前置依赖拓扑排序，展示"为什么推荐学这个"）→ 自适应练习（正确率>80% 升难度、<50% 降难度）→ 答错自动入 AIGC 错题本（解析 + 错误原因 + 2~3 道变式题）→ 画像随答题、助教提问持续迭代（加权 + 时间衰减）。

**Architecture:** 复用 Plan A/B/C 底座（认证/LLM 网关/备课试题），新增个性化学习域：数据模型（knowledge_points/kp_prereqs/student_profiles/profile_kps/learn_events/wrong_questions）→ 图谱服务（SQL 表 + networkx 拓扑排序——本机未装 Neo4j，按工单 16 退化方案，不影响验收）→ 画像服务（诊断/导入初始化、掌握度加权+时间衰减、numpy 协同过滤相似学生）→ 错题本服务（DeepSeek 同步生成解析/错误原因/变式题）→ 自适应练习服务（复用工单 17 习题集，后端判分）→ /api/learn 路由（仅 student）+ 智能助教提问画像联动 → Vue3 个性化学习页（仪表盘/练习/错题本三个 tab，ECharts 雷达图）。学生画像数据按设计文档 §331 严格本人隔离。

**Tech Stack:** FastAPI/SQLAlchemy（底座）+ networkx（知识图谱拓扑排序）+ numpy（协同过滤余弦相似度）+ DeepSeek chat_json（错题解析）+ Vue3/Element Plus/ECharts（雷达图）。

## Global Constraints

- 本计划所有新 Python 文件头部注释用模块专属工单编号：`# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)`；Vue/TS 文件模板内用 `<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19) -->`，script 内用 `// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)`
- 代码注释用中文；每个任务结束必须 git commit（身份 `huqiaoyu <huqiaoyu@local>`，用 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit ...`；显式路径 `git add`，**绝不 `git add -A`**——仓库根有无关未跟踪文件"实训日报-七天.md"）
- TDD：后端每个任务先写失败测试→跑测试确认失败→实现→跑测试确认通过→提交；pytest 从 `backend/` 目录运行（`python -m pytest`），默认排除 smoke
- 前端不写单测，以 `npm run build` 通过 + `npx tsc --noEmit` 0 错误验证
- 权限（设计文档 §331 原文落实）：/api/learn 全部端点仅 `student`（`require_roles(Role.student)`）；学生仅可访问本人画像、练习记录、错题本；相似学生推荐仅返回姓名与"对方掌握而我未掌握"的知识点名，不返回对方完整画像；前端菜单"个性化学习"仅 student 角色显示
- 知识图谱后端：SQL 表 + networkx（本机 Neo4j 未安装，工单 16 退化方案"不影响验收"；口径写入工单 19 文档与 README）；requirements.txt 钉 `networkx>=3.0`、`numpy>=1.26`
- 画像公式常量（逐字使用）：`DECAY_PER_DAY = 0.95`（每天掌握度 ×0.95）；事件增量：练习答对 `+10`、答错 `-15`、助教提问命中知识点 `+2`；掌握度夹取 `[0, 100]`；未掌握阈值 `60`；难度档 `["易", "中", "难"]`；难度阈值：滚动正确率 `>0.8` 升档、`<0.5` 降档；滚动窗口最近 `10` 次、样本不足 `5` 次不调整
- 时间比较统一用**朴素 UTC**（`datetime.now(timezone.utc).replace(tzinfo=None)`）——SQLite 会丢失 tzinfo；`_decayed` 对带 tzinfo 的存量值先 `replace(tzinfo=None)` 再比较
- 试题复用口径：工单 17 试题存于 `Lesson(lesson_type ∈ {exercises, exam})` 的 content_json（习题集 `{习题: [...]}`、月考题 `{大题: [{题目: [...]}]}`）；`Exercise` 表空置不用（口径写文档）；仅取含"选项"的选择题；题目定位 = `lesson_id + 题干全文匹配`，答案/解析不出后端（防前端作弊）
- 错题 AIGC prompt 结构（验收原文）：原题干 + 选项 + 学生答案 + 正确答案 + 知识点 + 难度 → JSON `{解析, 错误原因, 变式题[2~3 道，每项含 题干/选项/答案/解析]}`；答题提交时同步生成；LLM 失败错题保留（status=failed）、接口正常返回不抛错、前端错题本提供"重新生成"按钮
- 诊断测试口径：默认 10 题、难度易/中优先、题干去重、尽量覆盖不同知识点、**不带答案**；初始画像 = 每知识点正确率×100 直接赋值（不叠加不衰减）；导入历史成绩 = 课程级成绩 0~100 均匀初始化该课程试题涉及知识点（口径写文档）
- 助教提问联动：kb ask 流式回答完成后，按知识点名包含匹配记 +2 事件（仅 student）；记录失败不影响问答流（log 兜底）
- `GET /learn/practice` 允许建默认画像行（幂等副作用，口径写文档）
- 前端 echarts 钉 `^5.6.0`（npm 源可达已确认）；雷达图按 dataviz 参考盘：单系列蓝色 `#2a78d6`、线宽 2px、区域填充 `rgba(42, 120, 214, 0.15)`、轴名二级墨色 `#52514e`、分隔线 `#e1e0d9`、无图例（标题即系列名）、tooltip 保留
- 真实 DeepSeek key 只在 gitignored backend/.env，输出中要掩码；本机 huggingface.co 不可达（与本计划无新依赖，全量回归含 kb 测试时注意）
- 提交在 dev 分支（由控制器预先从 master 创建）；每个任务提交消息格式沿用 `feat(learn): ...` / `fix(learn): ...`

---

### Task 1: 数据模型（知识点图谱 / 学生画像 / 学习事件 / 错题本）

**Files:**
- Create: `backend/app/models/learn.py`
- Test: `backend/tests/test_models_learn.py`

**Interfaces:**
- Consumes: `app.db.Base`（Plan A）
- Produces: `KnowledgePoint`、`KpPrereq`、`StudentProfile`、`ProfileKp`、`LearnEvent`、`WrongQuestion`（Task 2~6 全部依赖）；建表经 main.py 导入链路自动 `create_all`（Task 6 注册路由后生效，测试文件直接 import 即注册）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_models_learn.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习数据模型测试：知识点图谱/画像/学习事件/错题本。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import (
    KnowledgePoint, KpPrereq, LearnEvent, ProfileKp, StudentProfile, WrongQuestion,
)
from app.models.user import Role, User


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'learn.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def test_knowledge_point_and_prereq(db):
    kp1 = KnowledgePoint(name="梯度下降", description="最优化算法")
    kp2 = KnowledgePoint(name="线性回归")
    db.add_all([kp1, kp2])
    db.commit()
    db.add(KpPrereq(kp_id=kp2.id, prereq_kp_id=kp1.id))
    db.commit()
    edge = db.query(KpPrereq).first()
    assert edge.kp_id == kp2.id and edge.prereq_kp_id == kp1.id


def test_student_profile_kp_defaults(db, user):
    profile = StudentProfile(user_id=user.id)
    db.add(profile)
    db.flush()
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.flush()
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=50.0, difficulty="易"))
    db.commit()
    got = db.query(ProfileKp).first()
    assert got.mastery == 50.0
    assert got.difficulty == "易"
    assert got.last_updated is not None
    p = db.query(StudentProfile).first()
    assert p.created_at is not None and p.updated_at is not None


def test_learn_event_types(db, user):
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.flush()
    db.add(LearnEvent(user_id=user.id, event_type="practice", kp_id=kp.id,
                      delta=10.0, correct=True, detail="练习"))
    db.add(LearnEvent(user_id=user.id, event_type="ask", kp_id=kp.id,
                      delta=2.0, correct=None, detail="提问"))
    db.commit()
    assert db.query(LearnEvent).filter(LearnEvent.correct.is_(True)).count() == 1
    assert db.query(LearnEvent).filter(LearnEvent.correct.is_(None)).count() == 1


def test_wrong_question_defaults_and_json(db, user):
    wq = WrongQuestion(user_id=user.id, stem="学习率过大会？", options=["A.收敛慢", "B.震荡"],
                       user_answer="A", correct_answer="B", knowledge_point="梯度下降",
                       difficulty="中")
    db.add(wq)
    db.commit()
    got = db.get(WrongQuestion, wq.id)
    assert got.status == "pending"
    assert got.analysis == ""
    assert got.variants == []
    got.variants = [{"题干": "变式1", "选项": ["A", "B"], "答案": "A", "解析": ""}]
    db.commit()
    assert db.get(WrongQuestion, wq.id).variants[0]["题干"] == "变式1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_models_learn.py -v`
Expected: FAIL（ImportError：app.models.learn 不存在）

- [ ] **Step 3: 实现数据模型**

`backend/app/models/learn.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习数据模型：知识点图谱/学生画像/学习事件/错题本。

设计要点（工单19）：
- 知识图谱：SQL 表存知识点与前置关系（本机未装 Neo4j，按工单16 退化方案），networkx 负责拓扑排序；
- 学生画像：profile 行 + 每知识点掌握度行（mastery 0~100，difficulty 为当前练习难度档）；
- 学习事件：画像迭代留痕（诊断/练习/提问/导入），时间衰减在服务层按 last_updated 计算；
- 错题本：答错登记 + AIGC 解析（status: pending|generated|failed）。
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class KnowledgePoint(Base):
    """知识点节点。name 与工单17 试题的"知识点"字段对齐（画像/练习按名关联）。"""

    __tablename__ = "knowledge_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class KpPrereq(Base):
    """知识点前置关系：kp_id 依赖 prereq_kp_id（先学 prereq 再学 kp）。"""

    __tablename__ = "kp_prereqs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    prereq_kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)


class StudentProfile(Base):
    """学生画像头：一行即"已初始化"（无行 = 未做诊断测试/导入）。"""

    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ProfileKp(Base):
    """学生-知识点掌握度（0~100）与当前练习难度档（易/中/难）。"""

    __tablename__ = "profile_kps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("student_profiles.id"), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[str] = mapped_column(String(10), default="易")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class LearnEvent(Base):
    """学习行为事件（画像迭代留痕）。event_type: diagnostic|practice|ask|import。"""

    __tablename__ = "learn_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    kp_id: Mapped[int] = mapped_column(ForeignKey("knowledge_points.id"), index=True)
    delta: Mapped[float] = mapped_column(Float, default=0.0)   # 掌握度增量（正负）
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # practice 用
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class WrongQuestion(Base):
    """AIGC 错题本：答错登记 + DeepSeek 生成的解析/错误原因/变式题。"""

    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    stem: Mapped[str] = mapped_column(Text)                    # 原题干
    options: Mapped[list] = mapped_column(JSON, default=list)
    user_answer: Mapped[str] = mapped_column(String(200))      # 学生错误答案
    correct_answer: Mapped[str] = mapped_column(String(200))
    knowledge_point: Mapped[str] = mapped_column(String(100), default="")
    difficulty: Mapped[str] = mapped_column(String(10), default="易")
    analysis: Mapped[str] = mapped_column(Text, default="")    # AIGC 解析
    error_reason: Mapped[str] = mapped_column(Text, default="")  # 错误原因（常见错误类型）
    variants: Mapped[list] = mapped_column(JSON, default=list)   # 变式题 [{题干,选项,答案,解析}]
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|generated|failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_models_learn.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
cd backend
git add tests/test_models_learn.py app/models/learn.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 个性化学习数据模型——知识点图谱/学生画像/学习事件/错题本"
```

---

### Task 2: 知识图谱服务（networkx 拓扑排序 + 可解释路径推荐）

**Files:**
- Create: `backend/app/services/learn_graph.py`
- Test: `backend/tests/test_learn_graph.py`

**Interfaces:**
- Consumes: `KnowledgePoint`、`KpPrereq`（Task 1）
- Produces: `build_graph(db) -> nx.DiGraph`、`topological_kps(graph) -> list[int]`、`recommend_path(mastery_map: dict[int, float], db) -> dict`（Task 6 /api/learn/path 使用；mastery_map 缺 key 视为 0 未掌握）；`MASTERY_THRESHOLD = 60.0`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_graph.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""知识图谱服务测试：建图/拓扑排序/可解释路径推荐。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint, KpPrereq
from app.services.learn_graph import (
    MASTERY_THRESHOLD, build_graph, recommend_path, topological_kps,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'graph.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _seed_chain(db):
    """线性代数 → 梯度下降 → 线性回归 的知识点链。"""
    names = ["线性代数", "梯度下降", "线性回归"]
    kps = {n: KnowledgePoint(name=n) for n in names}
    db.add_all(kps.values())
    db.flush()
    db.add(KpPrereq(kp_id=kps["梯度下降"].id, prereq_kp_id=kps["线性代数"].id))
    db.add(KpPrereq(kp_id=kps["线性回归"].id, prereq_kp_id=kps["梯度下降"].id))
    db.commit()
    return kps


def test_build_graph_and_topo(db):
    kps = _seed_chain(db)
    g = build_graph(db)
    assert set(g.nodes) == {k.id for k in kps.values()}
    assert g.nodes[kps["梯度下降"].id]["name"] == "梯度下降"
    assert list(g.successors(kps["线性代数"].id)) == [kps["梯度下降"].id]
    order = topological_kps(g)
    assert order.index(kps["线性代数"].id) < order.index(kps["梯度下降"].id) \
        < order.index(kps["线性回归"].id)


def test_recommend_path_unmastered_with_reasons(db):
    kps = _seed_chain(db)
    # 线性代数 70 已掌握；梯度下降 40 未掌握；线性回归缺记录（=0 未掌握）
    result = recommend_path(
        {kps["线性代数"].id: 70.0, kps["梯度下降"].id: 40.0}, db)
    names = [p["name"] for p in result["path"]]
    assert names == ["梯度下降", "线性回归"]
    assert result["mastered"] == 1 and result["unmastered"] == 2
    by_name = {p["name"]: p for p in result["path"]}
    # 梯度下降前置（线性代数）已掌握 → 可直接学
    assert "可直接学习" in by_name["梯度下降"]["why"]
    # 线性回归前置（梯度下降）未掌握 → 理由点名前置
    assert "前置知识点「梯度下降」" in by_name["线性回归"]["why"]
    assert by_name["线性回归"]["order"] == 2
    assert by_name["梯度下降"]["mastery"] == 40.0


def test_recommend_path_all_mastered(db):
    kps = _seed_chain(db)
    result = recommend_path({k.id: 100.0 for k in kps.values()}, db)
    assert result["path"] == []
    assert result["mastered"] == 3 and result["unmastered"] == 0


def test_topological_cycle_tolerance(db):
    """图含环时拓扑排序降级为节点 id 顺序，不抛异常（防御 seed 数据问题）。"""
    a = KnowledgePoint(name="A")
    b = KnowledgePoint(name="B")
    db.add_all([a, b])
    db.flush()
    db.add_all([KpPrereq(kp_id=a.id, prereq_kp_id=b.id),
                KpPrereq(kp_id=b.id, prereq_kp_id=a.id)])
    db.commit()
    g = build_graph(db)
    assert topological_kps(g) == sorted(g.nodes)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_graph.py -v`
Expected: FAIL（ImportError：app.services.learn_graph 不存在）

- [ ] **Step 3: 实现图谱服务**

`backend/app/services/learn_graph.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""知识图谱服务：SQL 表 → networkx 有向图，拓扑排序支撑可解释学习路径推荐。

本机未安装 Neo4j，按工单 16 退化方案用 SQL 表 + networkx 实现（不影响验收）；
图谱构建/推荐逻辑封装在本模块，未来接 Neo4j 只需替换数据来源。
"""
import logging

import networkx as nx
from sqlalchemy.orm import Session

from ..models.learn import KnowledgePoint, KpPrereq

logger = logging.getLogger("learn_graph")

MASTERY_THRESHOLD = 60.0  # 掌握度低于该阈值视为"未掌握"（推荐阈值）


def build_graph(db: Session) -> nx.DiGraph:
    """知识点前置关系 → 有向图：节点=知识点 id（带 name），边 prereq_kp_id → kp_id（先学→后学）。"""
    g = nx.DiGraph()
    for kp in db.query(KnowledgePoint).order_by(KnowledgePoint.id).all():
        g.add_node(kp.id, name=kp.name)
    for edge in db.query(KpPrereq).all():
        if edge.prereq_kp_id in g and edge.kp_id in g:
            g.add_edge(edge.prereq_kp_id, edge.kp_id)
    return g


def topological_kps(graph: nx.DiGraph) -> list[int]:
    """拓扑排序（学习顺序）。图含环时降级为节点 id 顺序并告警（seed 数据保证无环）。"""
    try:
        return list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        logger.warning("知识图谱存在环，拓扑排序降级为节点 id 顺序")
        return sorted(graph.nodes)


def recommend_path(mastery_map: dict[int, float], db: Session) -> dict:
    """推荐学习路径：未掌握知识点按拓扑序排列，逐项给出"为什么推荐学这个"。

    mastery_map: {kp_id: 当前掌握度（已含时间衰减）}；缺失视为 0（未掌握）。
    """
    graph = build_graph(db)
    order = topological_kps(graph)
    names = {nid: graph.nodes[nid]["name"] for nid in graph.nodes}
    unmastered = [nid for nid in order if mastery_map.get(nid, 0.0) < MASTERY_THRESHOLD]
    path = []
    for i, nid in enumerate(unmastered):
        missing = [p for p in graph.predecessors(nid)
                   if mastery_map.get(p, 0.0) < MASTERY_THRESHOLD]
        mastery = round(mastery_map.get(nid, 0.0), 1)
        if missing:
            why = (f"「{names[nid]}」掌握度 {mastery} 未达标，且前置知识点"
                   f"「{'」「'.join(names[m] for m in missing)}」尚未掌握，先补前置再学本知识点")
        else:
            why = f"「{names[nid]}」掌握度 {mastery} 未达标，前置知识已掌握，可直接学习"
        path.append({"kp_id": nid, "name": names[nid], "mastery": mastery,
                     "order": i + 1, "why": why})
    return {
        "path": path,
        "mastered": len(order) - len(unmastered),
        "unmastered": len(unmastered),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_graph.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
cd backend
git add tests/test_learn_graph.py app/services/learn_graph.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 知识图谱服务——networkx 拓扑排序 + 可解释路径推荐"
```

---

### Task 3: 学生画像服务（初始化 / 加权+时间衰减迭代 / 相似学生协同过滤）

**Files:**
- Create: `backend/app/services/learn_profile.py`
- Test: `backend/tests/test_learn_profile.py`

**Interfaces:**
- Consumes: `KnowledgePoint`、`StudentProfile`、`ProfileKp`、`LearnEvent`（Task 1）；`User`、`Role`（Plan A）
- Produces（Task 5/6 依赖）：
  - 常量：`DECAY_PER_DAY = 0.95`、`DELTA_PRACTICE_CORRECT = 10.0`、`DELTA_PRACTICE_WRONG = -15.0`、`DELTA_ASK = 2.0`、`MASTERY_THRESHOLD = 60.0`
  - `_now() -> datetime`（朴素 UTC）
  - `ensure_profile(user, db) -> StudentProfile`（取或建）
  - `get_or_create_kp(db, name) -> KnowledgePoint`（未知知识点自动登记孤立节点）
  - `apply_event(user, kp, delta, db, *, event_type, correct=None, detail="") -> ProfileKp`（衰减+增量+留痕）
  - `init_from_diagnostic(user, answers, db) -> dict`、`init_from_import(user, kp_names, score, db) -> dict`
  - `record_ask_events(user, question, db) -> int`（Task 6 kb hook 用）
  - `get_profile(user, db) -> dict`（雷达数据；未初始化 `initialized=False`）
  - `similar_students(user, db, top_n=3) -> list[dict]`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_profile.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""学生画像服务测试：诊断/导入初始化、时间衰减加权迭代、相似学生协同过滤。"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint, LearnEvent, ProfileKp, StudentProfile
from app.models.user import Role, User
from app.services import learn_profile

NAIVE_UTC = datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def _kp(db, name="梯度下降"):
    kp = KnowledgePoint(name=name)
    db.add(kp)
    db.commit()
    return kp


def test_decay_math(db, user):
    """2 天前的掌握度 100 → 100×0.95²=90.25。"""
    kp = _kp(db)
    profile = learn_profile.ensure_profile(user, db)
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=100.0,
                     difficulty="易", last_updated=NAIVE_UTC - timedelta(days=2)))
    db.commit()
    data = learn_profile.get_profile(user, db)
    assert abs(data["kps"][0]["mastery"] - 90.25) < 0.01


def test_apply_event_first_time_and_clamp(db, user):
    kp = _kp(db)
    row = learn_profile.apply_event(user, kp, learn_profile.DELTA_PRACTICE_CORRECT, db,
                                    event_type="practice", correct=True)
    assert row.mastery == 10.0
    # 夹取上限 100
    row = learn_profile.apply_event(user, kp, 95.0, db, event_type="practice", correct=True)
    assert row.mastery == 100.0
    db.commit()
    assert db.query(LearnEvent).filter(LearnEvent.user_id == user.id).count() == 2


def test_apply_event_decay_then_add(db, user):
    """4 天前的 80 → 80×0.95⁴≈65.16，再 +10 → 75.16。"""
    kp = _kp(db)
    profile = learn_profile.ensure_profile(user, db)
    db.add(ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=80.0,
                     difficulty="易", last_updated=NAIVE_UTC - timedelta(days=4)))
    db.commit()
    row = learn_profile.apply_event(user, kp, 10.0, db, event_type="practice", correct=True)
    assert abs(row.mastery - 75.16) < 0.01


def test_init_from_diagnostic(db, user):
    answers = [
        {"knowledge_point": "梯度下降", "correct": True},
        {"knowledge_point": "梯度下降", "correct": False},
        {"knowledge_point": "线性回归", "correct": True},
    ]
    result = learn_profile.init_from_diagnostic(user, answers, db)
    assert result == {"initialized": True, "kp_count": 2}
    data = learn_profile.get_profile(user, db)
    by_name = {k["name"]: k["mastery"] for k in data["kps"]}
    assert by_name["梯度下降"] == 50.0 and by_name["线性回归"] == 100.0
    assert db.query(LearnEvent).filter(LearnEvent.event_type == "diagnostic").count() == 2


def test_init_from_import(db, user):
    result = learn_profile.init_from_import(user, ["梯度下降", "线性回归"], 80.0, db)
    assert result == {"initialized": True, "kp_count": 2}
    data = learn_profile.get_profile(user, db)
    assert all(k["mastery"] == 80.0 for k in data["kps"])
    assert db.query(LearnEvent).filter(LearnEvent.event_type == "import").count() == 2
    # 空知识点列表 → 业务异常
    from app.core.exceptions import BizError
    with pytest.raises(BizError):
        learn_profile.init_from_import(user, [], 80.0, db)


def test_record_ask_events(db, user):
    kp1 = _kp(db, "梯度下降")
    _kp(db, "卷积神经网络")
    n = learn_profile.record_ask_events(user, "梯度下降的学习率怎么调？", db)
    assert n == 1
    events = db.query(LearnEvent).filter(LearnEvent.event_type == "ask").all()
    assert len(events) == 1 and events[0].kp_id == kp1.id
    assert abs(events[0].delta - 2.0) < 0.001
    # 不命中任何知识点 → 不产生事件
    assert learn_profile.record_ask_events(user, "今天天气怎么样", db) == 0


def test_get_profile_uninitialized(db, user):
    assert learn_profile.get_profile(user, db) == \
        {"initialized": False, "kps": [], "created_at": None}


def test_get_profile_missing_kp_is_zero(db, user):
    _kp(db, "梯度下降")
    profile = learn_profile.ensure_profile(user, db)
    db.commit()
    data = learn_profile.get_profile(user, db)
    assert data["initialized"] is True
    assert data["kps"][0]["mastery"] == 0.0


def test_get_or_create_kp(db):
    kp = learn_profile.get_or_create_kp(db, "全新知识点")
    assert kp.id is not None and kp.description.startswith("（由学习行为自动登记）")
    assert learn_profile.get_or_create_kp(db, "全新知识点").id == kp.id


def test_similar_students_cosine_and_privacy(db, user):
    other = User(username="s2", hashed_password="x", role=Role.student, real_name="王同学")
    db.add(other)
    db.commit()
    kp_a = _kp(db, "梯度下降")
    kp_b = _kp(db, "线性回归")
    p1 = StudentProfile(user_id=user.id)
    p2 = StudentProfile(user_id=other.id)
    db.add_all([p1, p2])
    db.flush()
    now = NAIVE_UTC
    db.add_all([
        ProfileKp(profile_id=p1.id, kp_id=kp_a.id, mastery=100.0, last_updated=now),
        ProfileKp(profile_id=p2.id, kp_id=kp_a.id, mastery=100.0, last_updated=now),
        ProfileKp(profile_id=p2.id, kp_id=kp_b.id, mastery=80.0, last_updated=now),
    ])
    db.commit()
    results = learn_profile.similar_students(user, db)
    assert len(results) == 1
    r = results[0]
    assert r["user_id"] == other.id and r["real_name"] == "王同学"
    # 余弦相似度 10000/(100×128.06)≈0.78
    assert abs(r["similarity"] - 0.78) < 0.01
    # 仅返回"对方掌握而我未掌握"的知识点名（不泄露对方完整画像）
    assert r["strengths"] == ["线性回归"]
    assert "mastery" not in r
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_profile.py -v`
Expected: FAIL（ImportError：app.services.learn_profile 不存在）

- [ ] **Step 3: 实现画像服务**

`backend/app/services/learn_profile.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""学生画像服务：诊断测试/历史成绩初始化、掌握度加权+时间衰减迭代、相似学生协同过滤。

画像公式（口径见工单19 文档）：
- 时间衰减：每天掌握度 ×0.95（约 7 天衰减 30%）
- 行为加权：练习答对 +10、答错 -15、助教提问命中知识点 +2
- 初始化：诊断测试每知识点正确率×100 直接赋值（不叠加）；导入成绩课程级均匀赋值
- 时间比较统一朴素 UTC（SQLite 丢 tzinfo）
"""
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.learn import KnowledgePoint, LearnEvent, ProfileKp, StudentProfile
from ..models.user import Role, User

logger = logging.getLogger("learn_profile")

DECAY_PER_DAY = 0.95          # 时间衰减系数：每天掌握度 ×0.95
DELTA_PRACTICE_CORRECT = 10.0
DELTA_PRACTICE_WRONG = -15.0
DELTA_ASK = 2.0
MASTERY_MIN = 0.0
MASTERY_MAX = 100.0
MASTERY_THRESHOLD = 60.0      # 与 learn_graph.MASTERY_THRESHOLD 一致

SECONDS_PER_DAY = 86400.0


def _now() -> datetime:
    """朴素 UTC 当前时间（SQLite 存取会丢 tzinfo，统一用朴素 UTC 比较）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decayed(mastery: float, last_updated: datetime, now: datetime) -> float:
    if last_updated.tzinfo is not None:
        last_updated = last_updated.replace(tzinfo=None)
    days = max(0.0, (now - last_updated).total_seconds() / SECONDS_PER_DAY)
    return mastery * (DECAY_PER_DAY ** days)


def _clamp(value: float) -> float:
    return max(MASTERY_MIN, min(MASTERY_MAX, value))


def ensure_profile(user: User, db: Session) -> StudentProfile:
    """取（或建）学生画像头。"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if profile is None:
        profile = StudentProfile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


def get_or_create_kp(db: Session, name: str) -> KnowledgePoint:
    """按名取知识点；试题/提问引用了图谱外的知识点时自动登记为孤立节点（容错）。"""
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.name == name).first()
    if kp is None:
        kp = KnowledgePoint(name=name, description="（由学习行为自动登记）")
        db.add(kp)
        db.flush()
    return kp


def apply_event(user: User, kp: KnowledgePoint, delta: float, db: Session, *,
                event_type: str, correct: bool | None = None, detail: str = "") -> ProfileKp:
    """掌握度更新：先时间衰减再加行为增量，夹取 [0,100]；事件留痕。"""
    profile = ensure_profile(user, db)
    row = (db.query(ProfileKp)
           .filter(ProfileKp.profile_id == profile.id, ProfileKp.kp_id == kp.id).first())
    now = _now()
    if row is None:
        row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=0.0,
                        difficulty="易", last_updated=now)
        db.add(row)
        db.flush()
    row.mastery = _clamp(_decayed(row.mastery, row.last_updated, now) + delta)
    row.last_updated = now
    profile.updated_at = now
    db.add(LearnEvent(user_id=user.id, event_type=event_type, kp_id=kp.id,
                      delta=delta, correct=correct, detail=detail[:200]))
    db.flush()
    return row


def init_from_diagnostic(user: User, answers: list[dict], db: Session) -> dict:
    """诊断测试初始化画像：answers = [{"knowledge_point": str, "correct": bool}]。

    每知识点掌握度 = 正确率 ×100 直接赋值（初始不叠加、不衰减）。
    """
    stats: dict[str, list] = {}
    for a in answers:
        stats.setdefault(a["knowledge_point"], []).append(bool(a["correct"]))
    profile = ensure_profile(user, db)
    now = _now()
    for name, results in stats.items():
        kp = get_or_create_kp(db, name)
        mastery = round(MASTERY_MAX * sum(results) / len(results), 1)
        row = (db.query(ProfileKp)
               .filter(ProfileKp.profile_id == profile.id, ProfileKp.kp_id == kp.id).first())
        if row is None:
            row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=mastery,
                            difficulty="易", last_updated=now)
            db.add(row)
        else:
            row.mastery = mastery
            row.last_updated = now
        db.add(LearnEvent(user_id=user.id, event_type="diagnostic", kp_id=kp.id,
                          delta=mastery, correct=None,
                          detail=f"诊断测试：{len(results)} 题，对 {sum(results)} 题"))
    profile.updated_at = now
    db.commit()
    return {"initialized": True, "kp_count": len(stats)}


def init_from_import(user: User, kp_names: list[str], score: float, db: Session) -> dict:
    """导入历史成绩：课程级成绩均匀初始化该课程试题涉及的知识点（口径见文档）。"""
    kp_names = sorted({n for n in kp_names if n})
    if not kp_names:
        raise BizError(400, "该课程暂无试题，无法初始化画像")
    score = _clamp(score)
    profile = ensure_profile(user, db)
    now = _now()
    for name in kp_names:
        kp = get_or_create_kp(db, name)
        row = (db.query(ProfileKp)
               .filter(ProfileKp.profile_id == profile.id, ProfileKp.kp_id == kp.id).first())
        if row is None:
            row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=score,
                            difficulty="易", last_updated=now)
            db.add(row)
        else:
            row.mastery = score
            row.last_updated = now
        db.add(LearnEvent(user_id=user.id, event_type="import", kp_id=kp.id,
                          delta=score, correct=None, detail=f"导入历史成绩 {score}"))
    profile.updated_at = now
    db.commit()
    return {"initialized": True, "kp_count": len(kp_names)}


def record_ask_events(user: User, question: str, db: Session) -> int:
    """助教提问画像联动：问题包含知识点名 → 记 +2 低权重事件（关注度激励）。"""
    hits = [kp for kp in db.query(KnowledgePoint).all() if kp.name in question]
    for kp in hits:
        apply_event(user, kp, DELTA_ASK, db, event_type="ask", detail=question[:200])
    if hits:
        db.commit()
    return len(hits)


def get_profile(user: User, db: Session) -> dict:
    """画像雷达数据：全图谱知识点 + 掌握度（无记录=0，已含时间衰减）。"""
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if profile is None:
        return {"initialized": False, "kps": [], "created_at": None}
    now = _now()
    rows = {r.kp_id: r for r in db.query(ProfileKp).filter(ProfileKp.profile_id == profile.id).all()}
    kps = []
    for kp in db.query(KnowledgePoint).order_by(KnowledgePoint.id).all():
        row = rows.get(kp.id)
        mastery = round(_decayed(row.mastery, row.last_updated, now), 1) if row else 0.0
        kps.append({"kp_id": kp.id, "name": kp.name, "mastery": mastery})
    return {"initialized": True, "kps": kps,
            "created_at": profile.created_at.replace(tzinfo=None).isoformat()}


def similar_students(user: User, db: Session, top_n: int = 3) -> list[dict]:
    """相似学生（numpy 协同过滤）：掌握度向量余弦相似度 top N。

    数据权限：仅返回姓名与"对方掌握而我未掌握"的知识点名，不返回对方完整画像。
    """
    all_kps = db.query(KnowledgePoint).order_by(KnowledgePoint.id).all()
    if not all_kps:
        return []
    now = _now()

    def vector(uid: int) -> np.ndarray:
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == uid).first()
        if profile is None:
            return np.zeros(len(all_kps))
        rows = {r.kp_id: r for r in db.query(ProfileKp).filter(ProfileKp.profile_id == profile.id).all()}
        return np.array([_decayed(rows[kp.id].mastery, rows[kp.id].last_updated, now)
                         if kp.id in rows else 0.0 for kp in all_kps])

    mine = vector(user.id)
    mine_norm = float(np.linalg.norm(mine))
    results = []
    for other in db.query(User).filter(User.role == Role.student, User.id != user.id).all():
        vec = vector(other.id)
        other_norm = float(np.linalg.norm(vec))
        sim = 0.0
        if mine_norm > 0 and other_norm > 0:
            sim = float(np.dot(mine, vec) / (mine_norm * other_norm))
        if sim <= 0:
            continue
        strengths = [all_kps[i].name for i in range(len(all_kps))
                     if vec[i] >= MASTERY_THRESHOLD and mine[i] < MASTERY_THRESHOLD]
        if strengths:
            results.append({"user_id": other.id, "real_name": other.real_name or other.username,
                            "similarity": round(sim, 2), "strengths": strengths})
    results.sort(key=lambda r: r["similarity"], reverse=True)
    return results[:top_n]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_profile.py -v`
Expected: PASS（11 passed）

- [ ] **Step 5: 提交**

```bash
cd backend
git add tests/test_learn_profile.py app/services/learn_profile.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 学生画像服务——初始化/加权时间衰减迭代/numpy 协同过滤相似学生"
```

---

### Task 4: AIGC 错题本服务（登记 + DeepSeek 解析生成 + 重新生成）

**Files:**
- Create: `backend/app/services/learn_wrongbook.py`
- Test: `backend/tests/test_learn_wrongbook.py`

**Interfaces:**
- Consumes: `WrongQuestion`（Task 1）；`LLMGateway.chat_json`、`LLMError`、`get_gateway`（Plan A）；`BizError`（Plan A）
- Produces（Task 5/6 依赖）：
  - `add_wrong_question(user, *, stem, options, user_answer, correct_answer, knowledge_point, difficulty, db, llm=None) -> WrongQuestion`（登记 + 同步生成；LLM 失败 status=failed 不抛异常）
  - `list_wrongbook(user, db) -> list[WrongQuestion]`
  - `regenerate(user, wq_id, db, llm=None) -> WrongQuestion`（仅本人；失败保持 failed 不抛异常）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_wrongbook.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""AIGC 错题本服务测试：登记/同步生成/失败保留/重新生成。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import WrongQuestion
from app.models.user import Role, User
from app.services import learn_wrongbook
from app.services.llm_gateway import LLMError

GOOD_JSON = {
    "解析": "先算梯度再更新参数。",
    "错误原因": "概念混淆：误把学习率当成迭代次数。",
    "变式题": [
        {"题干": "变式1：调整什么参数控制收敛速度？", "选项": ["A.学习率", "B.批大小"],
         "答案": "A", "解析": "学习率控制步长。"},
        {"题干": "变式2：学习率过小的后果？", "选项": ["A.收敛慢", "B.发散"],
         "答案": "A", "解析": "步长过小收敛缓慢。"},
    ],
}


class FakeLLM:
    def __init__(self, result):
        self._result = result

    def chat_json(self, messages, temperature=0.3):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'wrongbook.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def _kwargs():
    return dict(stem="学习率过大会导致什么？", options=["A.收敛慢", "B.震荡发散"],
                user_answer="A", correct_answer="B",
                knowledge_point="梯度下降", difficulty="中")


def test_add_wrong_question_generated(db, user):
    wq = learn_wrongbook.add_wrong_question(user, db=db, llm=FakeLLM(GOOD_JSON), **_kwargs())
    assert wq.status == "generated"
    assert wq.analysis == GOOD_JSON["解析"]
    assert wq.error_reason == GOOD_JSON["错误原因"]
    assert len(wq.variants) == 2
    assert wq.user_id == user.id


def test_add_wrong_question_llm_failure_keeps_record(db, user):
    """LLM 失败：错题保留（status=failed），不抛异常（接口正常返回）。"""
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(LLMError("未配置 DEEPSEEK_API_KEY")), **_kwargs())
    assert wq.status == "failed"
    assert wq.analysis == "" and wq.variants == []
    assert db.get(WrongQuestion, wq.id) is not None


def test_add_wrong_question_bad_structure_keeps_record(db, user):
    """结构不完整（缺字段/变式题不足 2 道）→ 同样保留错题并置 failed。"""
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM({"解析": "只有解析"}), **_kwargs())
    assert wq.status == "failed"
    wq2 = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM({"解析": "x", "错误原因": "y", "变式题": [{"题干": "1"}]}), **_kwargs())
    assert wq2.status == "failed"


def test_list_and_regenerate(db, user):
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(LLMError("未配置")), **_kwargs())
    assert wq.status == "failed"
    assert [w.id for w in learn_wrongbook.list_wrongbook(user, db)] == [wq.id]
    wq2 = learn_wrongbook.regenerate(user, wq.id, db, llm=FakeLLM(GOOD_JSON))
    assert wq2.status == "generated"
    assert len(wq2.variants) == 2
    # 重新生成再次失败 → 保持 failed，不抛异常
    wq3 = learn_wrongbook.regenerate(user, wq.id, db, llm=FakeLLM(LLMError("未配置")))
    assert wq3.status == "failed"


def test_regenerate_not_owner_404(db, user):
    other = User(username="s2", hashed_password="x", role=Role.student, real_name="王同学")
    db.add(other)
    db.commit()
    wq = learn_wrongbook.add_wrong_question(
        user, db=db, llm=FakeLLM(GOOD_JSON), **_kwargs())
    from app.core.exceptions import BizError
    with pytest.raises(BizError) as exc:
        learn_wrongbook.regenerate(other, wq.id, db, llm=FakeLLM(GOOD_JSON))
    assert exc.value.status_code == 404
    # 不存在同样 404
    with pytest.raises(BizError):
        learn_wrongbook.regenerate(user, 99999, db, llm=FakeLLM(GOOD_JSON))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_wrongbook.py -v`
Expected: FAIL（ImportError：app.services.learn_wrongbook 不存在）

- [ ] **Step 3: 实现错题本服务**

`backend/app/services/learn_wrongbook.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""AIGC 错题本服务：答错登记 + DeepSeek 生成（解析/错误原因/变式题）。

口径：答题提交时同步生成；LLM 失败错题保留（status=failed），接口正常返回，
前端错题本提供"重新生成"按钮。prompt 结构按验收要求：原题干+错误答案+正确答案+
知识点+常见错误类型 → 解析 + 错误原因 + 2~3 道变式题。
"""
import logging

from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.learn import WrongQuestion
from ..models.user import User
from .llm_gateway import LLMGateway, LLMError, get_gateway

logger = logging.getLogger("learn_wrongbook")

_WRONG_ANALYSIS_PROMPT = (
    "你是高职院校人工智能课程的辅导教师。学生做错了下面这道题，请帮助其掌握该知识点。\n"
    "原题干：{stem}\n选项：{options}\n学生答案：{user_answer}\n正确答案：{correct_answer}\n"
    "知识点：{knowledge_point}\n难度：{difficulty}\n"
    "请以 JSON 格式输出，键为中文："
    "解析（字符串，讲清解题思路）、错误原因（字符串，分析学生常见错误类型）、"
    "变式题（列表，2~3 道，每项含 题干/选项（列表，如 [\"A.学习率\", ...]）/答案（如 \"A\"）/解析）。"
    "变式题围绕同一知识点、不同角度，难度相近。不要输出其他内容。"
)


def _options_text(options: list) -> str:
    return "；".join(str(o) for o in (options or []))


def generate_analysis(wq: WrongQuestion, llm: LLMGateway | None = None) -> dict:
    """DeepSeek 生成错题解析：{解析, 错误原因, 变式题[2~3]}。结构不完整抛 BizError。"""
    gateway = llm or get_gateway()
    prompt = _WRONG_ANALYSIS_PROMPT.format(
        stem=wq.stem, options=_options_text(wq.options), user_answer=wq.user_answer,
        correct_answer=wq.correct_answer, knowledge_point=wq.knowledge_point,
        difficulty=wq.difficulty,
    )
    data = gateway.chat_json(
        [{"role": "system", "content": "你是教育错题辅导助手，只输出合法 JSON。"},
         {"role": "user", "content": prompt}],
        temperature=0.3,
    )
    for key in ("解析", "错误原因", "变式题"):
        if key not in data:
            raise BizError(502, f"错题解析生成结果缺少字段：{key}，请重试")
    if not isinstance(data["变式题"], list) or len(data["变式题"]) < 2:
        raise BizError(502, "错题解析生成的变式题不足 2 道，请重试")
    return data


def add_wrong_question(user: User, *, stem: str, options: list, user_answer: str,
                       correct_answer: str, knowledge_point: str, difficulty: str,
                       db: Session, llm: LLMGateway | None = None) -> WrongQuestion:
    """登记错题并同步生成 AI 解析；LLM 失败错题保留（status=failed），不抛异常。"""
    wq = WrongQuestion(user_id=user.id, stem=stem, options=options, user_answer=user_answer,
                       correct_answer=correct_answer, knowledge_point=knowledge_point,
                       difficulty=difficulty, status="pending")
    db.add(wq)
    db.flush()
    try:
        data = generate_analysis(wq, llm)
        wq.analysis = data["解析"]
        wq.error_reason = data["错误原因"]
        wq.variants = data["变式题"][:3]
        wq.status = "generated"
    except (LLMError, BizError) as exc:
        logger.warning("错题 AI 解析生成失败：%s（错题已保留）", exc)
        wq.status = "failed"
    db.commit()
    db.refresh(wq)
    return wq


def list_wrongbook(user: User, db: Session) -> list[WrongQuestion]:
    """本人错题本（倒序）。"""
    return (db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
            .order_by(WrongQuestion.id.desc()).all())


def regenerate(user: User, wq_id: int, db: Session, llm: LLMGateway | None = None) -> WrongQuestion:
    """重新生成解析（仅本人）。LLM 失败保持 failed 不抛异常（前端提示重试）。"""
    wq = db.get(WrongQuestion, wq_id)
    if wq is None or wq.user_id != user.id:
        raise BizError(404, "错题不存在")
    try:
        data = generate_analysis(wq, llm)
        wq.analysis = data["解析"]
        wq.error_reason = data["错误原因"]
        wq.variants = data["变式题"][:3]
        wq.status = "generated"
    except (LLMError, BizError) as exc:
        logger.warning("错题重新生成失败：%s", exc)
        wq.status = "failed"
    db.commit()
    db.refresh(wq)
    return wq
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_wrongbook.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
cd backend
git add tests/test_learn_wrongbook.py app/services/learn_wrongbook.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): AIGC 错题本服务——登记+同步生成解析/错误原因/变式题+重新生成"
```

---

### Task 5: 自适应练习服务（试题复用 / 难度控制 / 提交联动画像与错题本）

**Files:**
- Create: `backend/app/services/learn_practice.py`
- Test: `backend/tests/test_learn_practice.py`

**Interfaces:**
- Consumes: `Lesson`（Plan B 模型）；`ProfileKp`、`LearnEvent`（Task 1）；`learn_profile`（Task 3）；`learn_wrongbook`（Task 4）；`BizError`
- Produces（Task 6 依赖）：
  - 常量：`ACC_UP_THRESHOLD = 0.8`、`ACC_DOWN_THRESHOLD = 0.5`、`ROLLING_WINDOW = 10`、`DIFFICULTIES = ["易", "中", "难"]`
  - `collect_questions(db, *, course_id=None, kp=None, difficulty=None) -> list[dict]`（含 lesson_id 键）
  - `find_question(db, lesson_id, stem) -> dict`（含答案）
  - `diagnostic_questions(db, *, course_id=None, count=10) -> list[dict]`（不带答案）
  - `next_question(user, kp, db, *, course_id=None) -> dict`（不带答案；返回 `difficulty` 为题面难度）
  - `submit_answer(user, lesson_id, stem, answer, db, llm=None) -> dict`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_practice.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""自适应练习服务测试：试题复用/难度控制/提交联动画像与错题本。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import BizError
from app.db import Base
from app.models.learn import KnowledgePoint, LearnEvent, ProfileKp, WrongQuestion
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from app.services import learn_practice, learn_profile, learn_wrongbook
from app.services.llm_gateway import LLMError


class FakeLLM:
    def chat_json(self, messages, temperature=0.3):
        return {"解析": "思路", "错误原因": "概念混淆", "变式题": [
            {"题干": "v1", "选项": ["A", "B"], "答案": "A", "解析": ""},
            {"题干": "v2", "选项": ["A", "B"], "答案": "B", "解析": ""},
        ]}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'practice.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    u = User(username="s1", hashed_password="x", role=Role.student, real_name="李同学")
    db.add(u)
    db.commit()
    return u


def _question(stem, answer, kp="梯度下降", diff="易"):
    return {"题干": stem, "选项": ["A.a", "B.b", "C.c", "D.d"], "答案": answer,
            "解析": f"{stem} 的解析", "知识点": kp, "难度": diff}


@pytest.fixture
def seeded(db):
    """课程 + 习题集 lesson（梯度下降 易×2 中×2 难×1；线性回归 易×1）+ 月考题 lesson。"""
    course = Course(name="人工智能导论", subject="人工智能", owner_id=1)
    db.add(course)
    db.flush()
    exercises = [_question(f"梯度下降题{i}", "A", kp="梯度下降",
                           diff=["易", "易", "中", "中", "难"][i]) for i in range(5)]
    exercises.append(_question("线性回归题1", "B", kp="线性回归", diff="易"))
    lesson = Lesson(course_id=course.id, title="习题集", lesson_type="exercises",
                    content_json={"习题": exercises}, created_by=1)
    exam = Lesson(course_id=course.id, title="月考题", lesson_type="exam",
                  content_json={"试卷标题": "月考", "大题": [
                      {"题型": "选择题", "知识点": "梯度下降", "题目": [_question("月考梯度下降题", "A")]},
                      {"题型": "简答题", "知识点": "梯度下降",
                       "题目": [{"题干": "简述梯度下降（无选项）", "答案": "略", "知识点": "梯度下降"}]},
                  ]}, created_by=1)
    db.add_all([lesson, exam])
    db.commit()
    return {"course": course, "lesson": lesson, "exam": exam}


def test_collect_questions_exercises_and_exam(db, seeded):
    qs = learn_practice.collect_questions(db)
    # 习题集 6 + 月考题选择题 1（简答题无选项被过滤）
    assert len(qs) == 7
    assert all(q["lesson_id"] for q in qs)
    qs2 = learn_practice.collect_questions(db, kp="梯度下降", difficulty="难")
    assert len(qs2) == 1 and qs2[0]["题干"] == "梯度下降题4"
    qs3 = learn_practice.collect_questions(db, course_id=seeded["course"].id, kp="线性回归")
    assert [q["题干"] for q in qs3] == ["线性回归题1"]


def test_find_question(db, seeded):
    q = learn_practice.find_question(db, seeded["lesson"].id, "梯度下降题0")
    assert q["答案"] == "A" and q["知识点"] == "梯度下降"
    with pytest.raises(BizError):
        learn_practice.find_question(db, seeded["lesson"].id, "不存在的题")
    with pytest.raises(BizError):
        learn_practice.find_question(db, 99999, "梯度下降题0")


def test_diagnostic_questions_no_answer_and_coverage(db, seeded):
    """默认 10 题：易/中优先、题干去重、覆盖不同知识点、不带答案。"""
    qs = learn_practice.diagnostic_questions(db)
    assert 1 < len(qs) <= 10
    assert all("答案" not in q and "解析" not in q for q in qs)
    stems = [q["题干"] for q in qs]
    assert len(stems) == len(set(stems))
    kps = {q["知识点"] for q in qs}
    assert "线性回归" in kps  # 覆盖不同知识点（轮询取样）
    # count=1 → 只取 1 题
    qs2 = learn_practice.diagnostic_questions(db, count=1)
    assert len(qs2) == 1


def test_next_question_prefers_current_difficulty(db, user, seeded):
    # 默认画像行难度"易" → 抽易题，不带答案
    q = learn_practice.next_question(user, "梯度下降", db, course_id=seeded["course"].id)
    assert q["difficulty"] == "易"
    assert "答案" not in q and "解析" not in q
    assert q["knowledge_point"] == "梯度下降"
    # 该知识点无"易"题 → 放宽到全部难度（线性回归只有易题；改用只造难题的知识点验证）
    q2 = learn_practice.next_question(user, "线性回归", db, course_id=seeded["course"].id)
    assert q2["difficulty"] == "易"
    # 无任何题 → 404 友好提示
    with pytest.raises(BizError) as exc:
        learn_practice.next_question(user, "量子计算", db)
    assert exc.value.status_code == 404


def test_submit_correct_updates_profile_and_difficulty(db, user, seeded):
    for _ in range(5):  # 5 连对 → 正确率 1.0 > 0.8 → 升到"中"
        result = learn_practice.submit_answer(
            user, seeded["lesson"].id, "梯度下降题0", "A", db, llm=FakeLLM())
        assert result["correct"] is True
        assert result["answer"] == "A"
    acc = learn_practice._rolling_accuracy(user, db.query(KnowledgePoint)
                                           .filter(KnowledgePoint.name == "梯度下降").first().id, db)
    assert acc == 1.0
    assert result["difficulty_new"] == "中"
    row = db.query(ProfileKp).first()
    # 5×+10；相邻事件间有毫秒级时间差，衰减因子≈1，用近似断言
    assert abs(row.mastery - 50.0) < 0.01
    assert row.difficulty == "中"


def test_submit_wrong_creates_wrongbook(db, user, seeded, monkeypatch):
    monkeypatch.setattr(learn_wrongbook, "get_gateway", lambda: FakeLLM())
    result = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "B", db, llm=FakeLLM())
    assert result["correct"] is False
    assert result["wrong_question"]["status"] == "generated"
    wq = db.get(WrongQuestion, result["wrong_question"]["id"])
    assert wq.user_answer == "B" and wq.correct_answer == "A"
    assert wq.knowledge_point == "梯度下降"
    # 再次答错 → 第二条错题同样生成成功；画像 0 + (-15) 夹取到 0
    result2 = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "B", db, llm=FakeLLM())
    assert result2["wrong_question"]["status"] == "generated"
    row = db.query(ProfileKp).first()
    assert row.mastery == 0.0


def test_difficulty_down(db, user):
    kp = KnowledgePoint(name="梯度下降")
    db.add(kp)
    db.commit()
    profile = learn_profile.ensure_profile(user, db)
    row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=80.0,
                    difficulty="中", last_updated=learn_profile._now())
    db.add(row)
    db.commit()
    for _ in range(5):
        learn_profile.apply_event(user, kp, learn_profile.DELTA_PRACTICE_WRONG, db,
                                  event_type="practice", correct=False)
    acc = learn_practice._rolling_accuracy(user, kp.id, db)
    assert acc == 0.0
    assert learn_practice._adjust_difficulty(row, acc) == "易"


def test_submit_auto_registers_unknown_kp(db, user, seeded):
    """试题知识点不在图谱 → 自动登记孤立节点，画像仍更新。"""
    result = learn_practice.submit_answer(
        user, seeded["lesson"].id, "梯度下降题0", "A", db, llm=FakeLLM())
    assert result["correct"] is True
    assert db.query(KnowledgePoint).filter(KnowledgePoint.name == "梯度下降").count() == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_practice.py -v`
Expected: FAIL（ImportError：app.services.learn_practice 不存在）

- [ ] **Step 3: 实现练习服务**

`backend/app/services/learn_practice.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""自适应练习服务：复用工单 17 试题（Lesson content_json），按知识点+当前难度抽题，
正确率 >80% 升难度、<50% 降难度；答题提交联动画像与错题本。

口径（详见工单19 文档）：
- 试题来源：Lesson(lesson_type ∈ {exercises, exam}) 的 content_json，仅取含"选项"的选择题；
- 题目定位 = lesson_id + 题干全文匹配，答案/解析只在后端比对（防前端作弊）；
- GET 抽题允许建默认画像行（幂等副作用）。
"""
import logging
import random

from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.learn import KnowledgePoint, LearnEvent, ProfileKp
from ..models.prep import Lesson
from ..models.user import User
from . import learn_profile, learn_wrongbook
from .llm_gateway import LLMGateway

logger = logging.getLogger("learn_practice")

ACC_UP_THRESHOLD = 0.8     # 滚动正确率 >80% 升难度
ACC_DOWN_THRESHOLD = 0.5   # 滚动正确率 <50% 降难度
ROLLING_WINDOW = 10        # 难度判定窗口：最近 10 次练习
DIFFICULTIES = ["易", "中", "难"]


def collect_questions(db: Session, *, course_id: int | None = None,
                      kp: str | None = None, difficulty: str | None = None) -> list[dict]:
    """复用工单 17 试题：Lesson(lesson_type ∈ {exercises, exam}) 的 content_json。

    习题集：{习题: [{题干, 选项, 答案, 解析, 知识点, 难度}]}
    月考题：{试卷标题, 大题: [{题型, 知识点, 题目: [...]}]}（仅取含"选项"的选择题）
    """
    query = db.query(Lesson).filter(Lesson.lesson_type.in_(["exercises", "exam"]))
    if course_id is not None:
        query = query.filter(Lesson.course_id == course_id)
    questions = []
    for lesson in query.all():
        content = lesson.content_json or {}
        if lesson.lesson_type == "exercises":
            items = content.get("习题", [])
        else:
            items = [q for s in content.get("大题", []) for q in s.get("题目", [])]
        for q in items:
            if not isinstance(q, dict) or not q.get("题干") or not q.get("选项"):
                continue  # 简答题无选项，练习只取选择题
            if kp is not None and q.get("知识点") != kp:
                continue
            if difficulty is not None and q.get("难度") != difficulty:
                continue
            questions.append({**q, "lesson_id": lesson.id})
    return questions


def find_question(db: Session, lesson_id: int, stem: str) -> dict:
    """按 lesson_id + 题干全文定位原题（后端比对正确答案，防前端作弊）。"""
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise BizError(404, "试题不存在")
    content = lesson.content_json or {}
    if lesson.lesson_type == "exercises":
        items = content.get("习题", [])
    else:
        items = [q for s in content.get("大题", []) for q in s.get("题目", [])]
    for q in items:
        if isinstance(q, dict) and q.get("题干") == stem:
            return q
    raise BizError(404, "试题不存在（可能已被修改，请重新获取练习题）")


def diagnostic_questions(db: Session, *, course_id: int | None = None,
                         count: int = 10) -> list[dict]:
    """诊断测试抽题：易/中优先、题干去重、按知识点轮询尽量覆盖、不带答案。"""
    pool = collect_questions(db, course_id=course_id)
    easy_mid = [q for q in pool if q.get("难度") in ("易", "中")]
    pool = easy_mid or pool
    by_kp: dict[str, list[dict]] = {}
    for q in pool:
        by_kp.setdefault(q.get("知识点") or "未分类知识点", []).append(q)
    groups = sorted(by_kp.values(), key=len, reverse=True)
    picked: list[dict] = []
    seen: set[str] = set()
    idx = 0
    while len(picked) < count:
        progressed = False
        for g in groups:
            if idx < len(g) and g[idx]["题干"] not in seen:
                picked.append(g[idx])
                seen.add(g[idx]["题干"])
                progressed = True
            if len(picked) >= count:
                break
        idx += 1
        if not progressed:
            break
    return [{"lesson_id": q["lesson_id"], "stem": q["题干"], "options": q["选项"],
             "knowledge_point": q["知识点"], "difficulty": q["难度"]} for q in picked]


def _profile_row(user: User, kp: KnowledgePoint, db: Session) -> ProfileKp:
    """取（或建默认）学生-知识点画像行（GET 抽题允许幂等建行，口径见文档）。"""
    profile = learn_profile.ensure_profile(user, db)
    row = (db.query(ProfileKp)
           .filter(ProfileKp.profile_id == profile.id, ProfileKp.kp_id == kp.id).first())
    if row is None:
        row = ProfileKp(profile_id=profile.id, kp_id=kp.id, mastery=0.0,
                        difficulty="易", last_updated=learn_profile._now())
        db.add(row)
        db.flush()
    return row


def _rolling_accuracy(user: User, kp_id: int, db: Session) -> float | None:
    """最近 ROLLING_WINDOW 次练习正确率；样本不足 5 次返回 None（不调整难度）。"""
    events = (db.query(LearnEvent)
              .filter(LearnEvent.user_id == user.id, LearnEvent.kp_id == kp_id,
                      LearnEvent.event_type == "practice", LearnEvent.correct.isnot(None))
              .order_by(LearnEvent.id.desc()).limit(ROLLING_WINDOW).all())
    if len(events) < 5:
        return None
    return sum(1 for e in events if e.correct) / len(events)


def _adjust_difficulty(row: ProfileKp, acc: float) -> str:
    idx = DIFFICULTIES.index(row.difficulty)
    if acc > ACC_UP_THRESHOLD and idx < len(DIFFICULTIES) - 1:
        idx += 1
    elif acc < ACC_DOWN_THRESHOLD and idx > 0:
        idx -= 1
    row.difficulty = DIFFICULTIES[idx]
    return row.difficulty


def next_question(user: User, kp: str, db: Session, *, course_id: int | None = None) -> dict:
    """下一道练习题：按当前难度抽题（该难度无题则放宽到该知识点全部题）。"""
    kp_row = learn_profile.get_or_create_kp(db, kp)
    row = _profile_row(user, kp_row, db)
    questions = collect_questions(db, course_id=course_id, kp=kp, difficulty=row.difficulty)
    if not questions:
        questions = collect_questions(db, course_id=course_id, kp=kp)
    if not questions:
        raise BizError(404, f"知识点「{kp}」暂无练习题，请先在智能备课模块生成对应习题")
    q = random.choice(questions)
    return {"lesson_id": q["lesson_id"], "stem": q["题干"], "options": q["选项"],
            "knowledge_point": q["知识点"], "difficulty": q.get("难度", row.difficulty)}


def submit_answer(user: User, lesson_id: int, stem: str, answer: str,
                  db: Session, llm: LLMGateway | None = None) -> dict:
    """提交练习答案：后端比对 → 画像事件（对 +10/错 -15）→ 难度调整 → 错题入册+AI 解析。"""
    q = find_question(db, lesson_id, stem)
    correct = answer.strip().upper() == str(q.get("答案", "")).strip().upper()
    kp_name = q.get("知识点") or "未分类知识点"
    kp = learn_profile.get_or_create_kp(db, kp_name)
    delta = (learn_profile.DELTA_PRACTICE_CORRECT if correct
             else learn_profile.DELTA_PRACTICE_WRONG)
    learn_profile.apply_event(user, kp, delta, db, event_type="practice",
                              correct=correct, detail=f"练习：{stem[:100]}")
    row = _profile_row(user, kp, db)
    acc = _rolling_accuracy(user, kp.id, db)
    new_difficulty = _adjust_difficulty(row, acc) if acc is not None else row.difficulty
    result = {"correct": correct, "answer": q.get("答案", ""), "analysis": q.get("解析", ""),
              "knowledge_point": kp_name, "difficulty_new": new_difficulty}
    if not correct:
        wq = learn_wrongbook.add_wrong_question(
            user, stem=q["题干"], options=q.get("选项", []), user_answer=answer,
            correct_answer=str(q.get("答案", "")), knowledge_point=kp_name,
            difficulty=q.get("难度", row.difficulty), db=db, llm=llm)
        result["wrong_question"] = {"id": wq.id, "status": wq.status}
    db.commit()
    return result
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_practice.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
cd backend
git add tests/test_learn_practice.py app/services/learn_practice.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 自适应练习服务——试题复用/难度控制/提交联动画像与错题本"
```

---

### Task 6: /api/learn 路由 + 智能助教提问画像联动 + API 测试

**Files:**
- Create: `backend/app/api/learn.py`
- Modify: `backend/app/main.py`（注册路由）
- Modify: `backend/app/services/kb_service.py`（ask_stream 完成分支追加画像联动 hook）
- Create: `backend/tests/test_learn_api.py`

**Interfaces:**
- Consumes: Task 2/3/4/5 全部 Produces；`require_roles`、`get_current_user`（Plan A）；`kb_service.ask_stream`（Plan C）
- Produces: `/api/learn` 路由（前缀由 main.py 挂载）：GET courses / profile / diagnostic / path / tasks / similar / practice / wrongbook；POST diagnostic / import / practice/submit / wrongbook/{id}/regenerate

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_api.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习 API 测试：权限/诊断/导入/路径/任务/相似学生/练习/错题本/助教联动。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.db import Base
from app.main import app
from app.models.learn import KnowledgePoint, LearnEvent
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from app.services import kb_service, learn_wrongbook


class FakeWrongbookLLM:
    def chat_json(self, messages, temperature=0.3):
        return {"解析": "解题思路", "错误原因": "概念混淆", "变式题": [
            {"题干": "变式1", "选项": ["A.a", "B.b"], "答案": "B", "解析": "略"},
            {"题干": "变式2", "选项": ["A.a", "B.b"], "答案": "A", "解析": "略"},
        ]}


class FakeEmbedder:
    dim = 8

    def embed_texts(self, texts):
        return [[0.125] * self.dim for _ in texts]

    def embed_query(self, text):
        return [0.125] * self.dim


class FakeStore:
    def search(self, name, query_vector, top_k, filter_dict=None):
        return []


class FakeAskGateway:
    def chat_stream(self, messages, temperature=0.7):
        yield "助教回答片段"


def _question(stem, answer, kp="梯度下降", diff="易"):
    return {"题干": stem, "选项": ["A.a", "B.b", "C.c", "D.d"], "答案": answer,
            "解析": f"{stem} 的解析", "知识点": kp, "难度": diff}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时 DB + 用户（student/teacher）+ 课程与习题集 + 假错题 LLM。"""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[deps.get_db] = override_get_db
    monkeypatch.setattr(learn_wrongbook, "get_gateway", lambda: FakeWrongbookLLM())
    from fastapi.testclient import TestClient
    client = TestClient(app)

    from app.core.security import create_access_token, hash_password
    s = Session()
    headers = {}
    for name, role in [("teacher", Role.teacher), ("student", Role.student),
                       ("student2", Role.student)]:
        u = User(username=name, hashed_password=hash_password("p"), role=role,
                 real_name=name)
        s.add(u)
        s.commit()
        s.refresh(u)
        headers[name] = {"Authorization": f"Bearer {create_access_token(u.id, u.role.value)}"}
    teacher = s.query(User).filter(User.username == "teacher").first()
    course = Course(name="人工智能导论", subject="人工智能", owner_id=teacher.id)
    s.add(course)
    s.commit()
    qs = []
    for i in range(8):
        qs.append(_question(f"诊断梯度下降题{i}", "A",
                            kp="梯度下降" if i % 2 == 0 else "线性回归", diff="易"))
    s.add(Lesson(course_id=course.id, title="诊断习题集", lesson_type="exercises",
                 content_json={"习题": qs}, created_by=teacher.id))
    s.commit()
    yield client, headers, tmp_path, Session, course
    app.dependency_overrides.clear()


def test_learn_routes_require_student(env):
    client, headers, *_ = env
    for path in ["/api/learn/profile", "/api/learn/path", "/api/learn/wrongbook"]:
        resp = client.get(path, headers=headers["teacher"])
        assert resp.status_code == 403
        assert "权限不足" in resp.json()["detail"]
    resp = client.get("/api/learn/profile")
    assert resp.status_code == 401


def test_profile_uninitialized_then_diagnostic_flow(env):
    client, headers, *_ = env
    resp = client.get("/api/learn/profile", headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["initialized"] is False
    # 获取诊断题：不带答案
    resp = client.get("/api/learn/diagnostic", headers=headers["student"])
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert len(questions) == 8
    assert all("答案" not in q and "解析" not in q for q in questions)
    # 全部作答 A → 全对
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "A"}
               for q in questions]
    resp = client.post("/api/learn/diagnostic", json={"answers": answers},
                       headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["initialized"] is True
    profile = client.get("/api/learn/profile", headers=headers["student"]).json()
    by_name = {k["name"]: k["mastery"] for k in profile["kps"]}
    assert by_name["梯度下降"] == 100.0 and by_name["线性回归"] == 100.0
    # 全部掌握 → 路径为空
    resp = client.get("/api/learn/path", headers=headers["student"])
    assert resp.json()["path"] == []
    assert resp.json()["mastered"] == 2


def test_diagnostic_partial_and_path_tasks(env):
    client, headers, tmp_path, Session, course = env
    questions = client.get("/api/learn/diagnostic", headers=headers["student"]).json()["questions"]
    # 梯度下降题答错、线性回归题答对
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"],
                "answer": "A" if q["knowledge_point"] == "线性回归" else "B"}
               for q in questions]
    resp = client.post("/api/learn/diagnostic", json={"answers": answers},
                       headers=headers["student"])
    assert resp.status_code == 200
    path = client.get("/api/learn/path", headers=headers["student"]).json()
    assert [p["name"] for p in path["path"]] == ["梯度下降"]
    assert "可直接学习" in path["path"][0]["why"]
    tasks = client.get("/api/learn/tasks", headers=headers["student"]).json()
    assert len(tasks) == 1
    assert tasks[0]["name"] == "梯度下降" and tasks[0]["question"]["stem"]
    # 答题与题库不匹配 → 400
    bad = client.post("/api/learn/diagnostic",
                      json={"answers": [{"lesson_id": 1, "stem": "不存在", "answer": "A"}]},
                      headers=headers["student"])
    assert bad.status_code == 400


def test_import_flow(env):
    client, headers, tmp_path, Session, course = env
    resp = client.post("/api/learn/import", json={"course_id": course.id, "score": 75},
                       headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json() == {"initialized": True, "kp_count": 2}
    profile = client.get("/api/learn/profile", headers=headers["student"]).json()
    assert all(k["mastery"] == 75.0 for k in profile["kps"])
    assert client.post("/api/learn/import", json={"course_id": course.id, "score": 150},
                       headers=headers["student"]).status_code == 400
    assert client.post("/api/learn/import", json={"course_id": 99999, "score": 80},
                       headers=headers["student"]).status_code == 400


def test_practice_flow(env):
    client, headers, *_ = env
    resp = client.get("/api/learn/practice", params={"kp": "梯度下降"},
                      headers=headers["student"])
    assert resp.status_code == 200
    q = resp.json()
    assert "答案" not in q and q["difficulty"] == "易"
    # 答对
    resp = client.post("/api/learn/practice/submit",
                       json={"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "A"},
                       headers=headers["student"])
    data = resp.json()
    assert data["correct"] is True and data["analysis"]
    # 答错 → 错题入册（假 LLM 生成成功）
    resp = client.post("/api/learn/practice/submit",
                       json={"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "B"},
                       headers=headers["student"])
    data = resp.json()
    assert data["correct"] is False
    assert data["wrong_question"]["status"] == "generated"
    assert data["difficulty_new"] == "易"  # 样本不足不调整
    # 错题本列表 + 重新生成
    resp = client.get("/api/learn/wrongbook", headers=headers["student"])
    assert len(resp.json()) == 1
    wq = resp.json()[0]
    assert wq["user_answer"] == "B" and len(wq["variants"]) == 2
    resp = client.post(f"/api/learn/wrongbook/{wq['id']}/regenerate",
                       headers=headers["student"])
    assert resp.json()["status"] == "generated"
    # 他人错题不可重新生成
    resp = client.post(f"/api/learn/wrongbook/{wq['id']}/regenerate",
                       headers=headers["student2"])
    assert resp.status_code == 404


def test_similar_students_and_courses(env):
    client, headers, tmp_path, Session, course = env
    # student 诊断全对；student2 也全对 → 相似度 1.0
    questions = client.get("/api/learn/diagnostic", headers=headers["student"]).json()["questions"]
    answers = [{"lesson_id": q["lesson_id"], "stem": q["stem"], "answer": "A"}
               for q in questions]
    client.post("/api/learn/diagnostic", json={"answers": answers}, headers=headers["student"])
    client.post("/api/learn/diagnostic", json={"answers": answers}, headers=headers["student2"])
    resp = client.get("/api/learn/similar", headers=headers["student"])
    assert resp.status_code == 200
    sims = resp.json()
    assert len(sims) == 1
    assert sims[0]["real_name"] == "student2" and sims[0]["similarity"] == 1.0
    assert sims[0]["strengths"] == []  # 双方都掌握 → 无借鉴项
    resp = client.get("/api/learn/courses", headers=headers["student"])
    assert resp.json() == [{"id": course.id, "name": "人工智能导论"}]


def test_kb_ask_records_ask_event(env, monkeypatch):
    client, headers, tmp_path, Session = env
    monkeypatch.setattr(kb_service, "hybrid_retrieve", lambda *a, **k: [])
    s = Session()
    kp = KnowledgePoint(name="梯度下降", description="")
    s.add(kp)
    s.commit()
    student = s.query(User).filter(User.username == "student").first()
    gen = kb_service.ask_stream("梯度下降的学习率怎么调？", student, s,
                                embedder=FakeEmbedder(), vector_store=FakeStore(),
                                reranker=None, gateway=FakeAskGateway())
    blocks = list(gen)
    assert any("event: done" in b for b in blocks)
    events = s.query(LearnEvent).filter(LearnEvent.user_id == student.id,
                                        LearnEvent.event_type == "ask").all()
    assert len(events) == 1 and abs(events[0].delta - 2.0) < 0.001
    # 教师提问不记事件
    teacher = s.query(User).filter(User.username == "teacher").first()
    gen2 = kb_service.ask_stream("梯度下降怎么学？", teacher, s,
                                 embedder=FakeEmbedder(), vector_store=FakeStore(),
                                 reranker=None, gateway=FakeAskGateway())
    list(gen2)
    assert s.query(LearnEvent).filter(LearnEvent.user_id == teacher.id).count() == 0
    # 画像事件记录失败不影响问答流（done 仍发出）
    monkeypatch.setattr(kb_service.learn_profile, "record_ask_events",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    gen3 = kb_service.ask_stream("梯度下降怎么学？", student, s,
                                 embedder=FakeEmbedder(), vector_store=FakeStore(),
                                 reranker=None, gateway=FakeAskGateway())
    assert any("event: done" in b for b in list(gen3))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_api.py -v`
Expected: FAIL（ImportError：app.api.learn 不存在）

- [ ] **Step 3: 实现路由**

`backend/app/api/learn.py`：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""个性化学习接口：画像/诊断测试/历史成绩导入/推荐路径/今日任务/相似学生/自适应练习/错题本。

权限（设计文档 §331）：全部端点仅 student；学生仅可访问本人画像、练习记录与错题本；
相似学生仅返回姓名与"对方掌握而我未掌握"的知识点名。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..db import get_db
from ..models.prep import Course, Lesson
from ..models.user import Role, User
from ..services import learn_graph, learn_practice, learn_profile, learn_wrongbook
from .deps import require_roles

router = APIRouter()

_student = require_roles(Role.student)


class DiagnosticIn(BaseModel):
    answers: list[dict]   # [{lesson_id, stem, answer}]


class ImportIn(BaseModel):
    course_id: int
    score: float


class SubmitIn(BaseModel):
    lesson_id: int
    stem: str
    answer: str


# ---------- 课程列表（试题来源） ----------


@router.get("/courses")
def list_learn_courses(user: User = Depends(_student), db: Session = Depends(get_db)):
    """试题来源课程（含习题集/月考题的课程）：诊断测试与成绩导入的选择范围。"""
    course_ids = {row[0] for row in db.query(Lesson.course_id)
                  .filter(Lesson.lesson_type.in_(["exercises", "exam"])).all()}
    return [{"id": c.id, "name": c.name}
            for c in db.query(Course).filter(Course.id.in_(course_ids)).order_by(Course.id).all()]


# ---------- 画像 ----------


@router.get("/profile")
def profile(user: User = Depends(_student), db: Session = Depends(get_db)):
    return learn_profile.get_profile(user, db)


@router.get("/path")
def path(user: User = Depends(_student), db: Session = Depends(get_db)):
    mastery_map = {k["kp_id"]: k["mastery"] for k in learn_profile.get_profile(user, db)["kps"]}
    if not mastery_map:
        raise BizError(400, "尚未初始化画像，请先完成诊断测试或导入历史成绩")
    return learn_graph.recommend_path(mastery_map, db)


@router.get("/tasks")
def tasks(user: User = Depends(_student), db: Session = Depends(get_db)):
    """今日任务：推荐路径前 2 个未掌握知识点 + 各配一道推荐练习题。"""
    mastery_map = {k["kp_id"]: k["mastery"] for k in learn_profile.get_profile(user, db)["kps"]}
    result = learn_graph.recommend_path(mastery_map, db)
    out = []
    for item in result["path"][:2]:
        q = learn_practice.next_question(user, item["name"], db)
        out.append({"kp_id": item["kp_id"], "name": item["name"],
                    "mastery": item["mastery"], "why": item["why"], "question": q})
    return out


@router.get("/similar")
def similar(user: User = Depends(_student), db: Session = Depends(get_db)):
    return learn_profile.similar_students(user, db)


# ---------- 诊断测试 / 导入 ----------


@router.get("/diagnostic")
def diagnostic(course_id: int | None = None, user: User = Depends(_student),
               db: Session = Depends(get_db)):
    questions = learn_practice.diagnostic_questions(db, course_id=course_id)
    if not questions:
        raise BizError(404, "暂无可用试题，请先在智能备课模块生成习题")
    return {"questions": questions, "count": len(questions)}


@router.post("/diagnostic")
def submit_diagnostic(data: DiagnosticIn, user: User = Depends(_student),
                      db: Session = Depends(get_db)):
    if not data.answers:
        raise BizError(400, "答案不能为空")
    stats = []
    for a in data.answers:
        try:
            q = learn_practice.find_question(db, a["lesson_id"], a["stem"])
        except BizError:
            raise BizError(400, "答题与题库不匹配，请重新开始诊断测试")
        stats.append({
            "knowledge_point": q.get("知识点") or "未分类知识点",
            "correct": (a.get("answer") or "").strip().upper()
            == str(q.get("答案", "")).strip().upper(),
        })
    return learn_profile.init_from_diagnostic(user, stats, db)


@router.post("/import")
def import_score(data: ImportIn, user: User = Depends(_student), db: Session = Depends(get_db)):
    if not (0 <= data.score <= 100):
        raise BizError(400, "成绩需在 0~100 之间")
    kps = {q.get("知识点") for q in learn_practice.collect_questions(db, course_id=data.course_id)
           if q.get("知识点")}
    if not kps:
        raise BizError(400, "该课程暂无试题，无法初始化画像")
    return learn_profile.init_from_import(user, sorted(kps), data.score, db)


# ---------- 自适应练习 ----------


@router.get("/practice")
def practice(kp: str = Query(...), course_id: int | None = None,
             user: User = Depends(_student), db: Session = Depends(get_db)):
    if not kp.strip():
        raise BizError(400, "知识点不能为空")
    return learn_practice.next_question(user, kp.strip(), db, course_id=course_id)


@router.post("/practice/submit")
def practice_submit(data: SubmitIn, user: User = Depends(_student), db: Session = Depends(get_db)):
    if not data.answer.strip():
        raise BizError(400, "请先作答")
    return learn_practice.submit_answer(user, data.lesson_id, data.stem, data.answer, db)


# ---------- 错题本 ----------


@router.get("/wrongbook")
def wrongbook(user: User = Depends(_student), db: Session = Depends(get_db)):
    return [{"id": w.id, "stem": w.stem, "options": w.options, "user_answer": w.user_answer,
             "correct_answer": w.correct_answer, "knowledge_point": w.knowledge_point,
             "difficulty": w.difficulty, "analysis": w.analysis, "error_reason": w.error_reason,
             "variants": w.variants, "status": w.status, "created_at": w.created_at.isoformat()}
            for w in learn_wrongbook.list_wrongbook(user, db)]


@router.post("/wrongbook/{wq_id}/regenerate")
def wrongbook_regenerate(wq_id: int, user: User = Depends(_student), db: Session = Depends(get_db)):
    w = learn_wrongbook.regenerate(user, wq_id, db)
    return {"id": w.id, "analysis": w.analysis, "error_reason": w.error_reason,
            "variants": w.variants, "status": w.status}
```

- [ ] **Step 4: 注册路由与 kb 联动 hook**

`backend/app/main.py` 修改两处：

```python
from .api import auth, files, kb, learn, prep
```

```python
app.include_router(learn.router, prefix="/api/learn", tags=["learn"])
```

`backend/app/services/kb_service.py` 修改两处。顶部导入区（`from ..services.llm_gateway import ...` 之后）追加：

```python
from . import learn_profile
```

`ask_stream` 中（`yield sse("done", {})` 之前，chat_stream 循环之后）追加：

```python
        # 工单19 画像迭代联动：学生提问命中知识点 → 记低权重事件（失败不影响问答流）
        if user.role == Role.student:
            try:
                learn_profile.record_ask_events(user, question, db)
            except Exception:
                logger.exception("画像事件记录失败（问答不受影响）")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_api.py -v`
Expected: PASS（7 passed）

- [ ] **Step 6: 全量回归 + 提交**

Run: `cd backend && python -m pytest`
Expected: 既有 108 passed, 2 deselected + 本计划新增用例全部通过，无回归

```bash
cd backend
git add tests/test_learn_api.py app/api/learn.py app/main.py app/services/kb_service.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): /api/learn 路由（仅 student）+ 助教提问画像联动 + API 测试"
```

---

### Task 7: 前端个性化学习页面（画像仪表盘 / 自适应练习 / 错题本）

**Files:**
- Modify: `frontend/package.json`（echarts 依赖）
- Create: `frontend/src/api/learn.ts`
- Create: `frontend/src/views/learn/LearnView.vue`
- Modify: `frontend/src/router/index.ts`（/module/learn 路由）
- Modify: `frontend/src/views/HomeView.vue`（菜单按角色过滤）

**Interfaces:**
- Consumes: Task 6 的 /api/learn 全部端点；`useAuthStore`（Plan A）；`http`（Plan A）
- Produces: `/module/learn` 页面（替代 PlaceholderView）

- [ ] **Step 1: 安装 echarts**

Run: `cd frontend && npm install echarts@^5.6.0`
Expected: 安装成功，package.json dependencies 出现 `"echarts": "^5.6.0"`

- [ ] **Step 2: 写 API 层**

`frontend/src/api/learn.ts`：

```typescript
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
import http from './http'

export interface KpMastery { kp_id: number; name: string; mastery: number }
export interface ProfileData { initialized: boolean; kps: KpMastery[]; created_at: string | null }
export interface PathItem { kp_id: number; name: string; mastery: number; order: number; why: string }
export interface Question { lesson_id: number; stem: string; options: string[]; knowledge_point: string; difficulty: string }
export interface TaskItem { kp_id: number; name: string; mastery: number; why: string; question: Question }
export interface SimilarStudent { user_id: number; real_name: string; similarity: number; strengths: string[] }
export interface PracticeResult {
  correct: boolean; answer: string; analysis: string
  knowledge_point: string; difficulty_new: string
  wrong_question?: { id: number; status: string }
}
export interface WrongQuestionItem {
  id: number; stem: string; options: string[]; user_answer: string; correct_answer: string
  knowledge_point: string; difficulty: string; analysis: string; error_reason: string
  variants: Question[]; status: string; created_at: string
}

export const getProfile = () => http.get('/learn/profile') as Promise<ProfileData>
export const listLearnCourses = () =>
  http.get('/learn/courses') as Promise<{ id: number; name: string }[]>
export const getDiagnostic = () =>
  http.get('/learn/diagnostic') as Promise<{ questions: Question[]; count: number }>
export const submitDiagnostic = (answers: { lesson_id: number; stem: string; answer: string }[]) =>
  http.post('/learn/diagnostic', { answers }) as Promise<{ initialized: boolean; kp_count: number }>
export const importScore = (courseId: number, score: number) =>
  http.post('/learn/import', { course_id: courseId, score }) as Promise<{ initialized: boolean; kp_count: number }>
export const getPath = () =>
  http.get('/learn/path') as Promise<{ path: PathItem[]; mastered: number; unmastered: number }>
export const getTasks = () => http.get('/learn/tasks') as Promise<TaskItem[]>
export const getSimilar = () => http.get('/learn/similar') as Promise<SimilarStudent[]>
export const getPractice = (kp: string, courseId?: number) =>
  http.get('/learn/practice', { params: { kp, course_id: courseId } }) as Promise<Question>
// 答错同步生成 AI 解析（DeepSeek 调用），覆盖全局 30s 超时
export const submitPractice = (lessonId: number, stem: string, answer: string) =>
  http.post('/learn/practice/submit', { lesson_id: lessonId, stem, answer },
    { timeout: 120000 }) as Promise<PracticeResult>
export const listWrongbook = () => http.get('/learn/wrongbook') as Promise<WrongQuestionItem[]>
export const regenerateWrong = (id: number) =>
  http.post(`/learn/wrongbook/${id}/regenerate`, undefined,
    { timeout: 120000 }) as Promise<WrongQuestionItem>
```

- [ ] **Step 3: 写页面**

`frontend/src/views/learn/LearnView.vue`：

```vue
<!-- 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19) -->
<template>
  <div>
    <!-- 未初始化画像：引导 -->
    <el-card v-if="profile && !profile.initialized">
      <el-empty description="还没有学习画像，先完成诊断测试或导入历史成绩">
        <el-button type="primary" @click="startDiagnostic">开始诊断测试</el-button>
        <el-button @click="importVisible = true">导入历史成绩</el-button>
      </el-empty>
    </el-card>

    <!-- 诊断测试进行中 -->
    <el-card v-if="diagnosing">
      <template #header>
        <span>诊断测试（共 {{ diagQuestions.length }} 题）</span>
      </template>
      <el-empty v-if="!diagQuestions.length" description="暂无可用试题，请先由教师在智能备课模块生成习题" />
      <div v-for="(q, i) in diagQuestions" :key="q.stem" style="margin-bottom: 18px">
        <p><b>{{ i + 1 }}. {{ q.stem }}</b>
          <el-tag size="small" style="margin-left: 6px">{{ q.knowledge_point }}</el-tag>
          <el-tag size="small" type="info" style="margin-left: 4px">{{ q.difficulty }}</el-tag>
        </p>
        <el-radio-group v-model="diagAnswers[q.stem]">
          <el-radio v-for="opt in q.options" :key="opt" :value="opt">{{ opt }}</el-radio>
        </el-radio-group>
      </div>
      <div v-if="diagQuestions.length" style="margin-top: 16px">
        <el-button type="primary" :loading="submittingDiag" @click="onSubmitDiagnostic">提交诊断</el-button>
        <el-button @click="diagnosing = false">取消</el-button>
      </div>
    </el-card>

    <!-- 已初始化画像：三个 tab -->
    <el-tabs v-else-if="profile?.initialized" v-model="activeTab">
      <el-tab-pane label="画像仪表盘" name="dash">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card>
              <template #header>画像雷达图（知识点掌握度）</template>
              <div ref="radarEl" style="height: 340px"></div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card>
              <template #header>推荐学习路径（为什么推荐学这个）</template>
              <el-empty v-if="!path.length" description="全部知识点已掌握，继续保持！" />
              <el-timeline v-else style="padding-left: 4px">
                <el-timeline-item v-for="p in path" :key="p.kp_id" :timestamp="`第 ${p.order} 步 · 掌握度 ${p.mastery}`">
                  <b>{{ p.name }}</b>
                  <p style="color: #666; font-size: 13px; margin: 4px 0">{{ p.why }}</p>
                </el-timeline-item>
              </el-timeline>
            </el-card>
          </el-col>
        </el-row>
        <el-row :gutter="16" style="margin-top: 16px">
          <el-col :span="12">
            <el-card>
              <template #header>今日任务</template>
              <el-empty v-if="!tasks.length" description="今日暂无任务" />
              <div v-for="t in tasks" :key="t.kp_id" style="margin-bottom: 10px">
                <div style="display: flex; justify-content: space-between; align-items: center">
                  <b>{{ t.name }}</b>
                  <el-button size="small" type="primary" @click="startTaskPractice(t)">开始练习</el-button>
                </div>
                <p style="color: #666; font-size: 13px; margin: 4px 0">{{ t.why }}</p>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card>
              <template #header>相似学生（协同过滤）</template>
              <el-empty v-if="!similar.length" description="暂无相似学生数据" />
              <div v-for="s in similar" :key="s.user_id" style="margin-bottom: 10px">
                <div style="display: flex; justify-content: space-between; align-items: center">
                  <span><b>{{ s.real_name }}</b> 相似度 {{ Math.round(s.similarity * 100) }}%</span>
                  <span v-if="s.strengths.length">
                    <el-tag v-for="kp in s.strengths" :key="kp" size="small" style="margin-left: 4px">{{ kp }}</el-tag>
                  </span>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="自适应练习" name="practice">
        <el-card>
          <template #header>自适应练习（正确率 &gt;80% 升难度、&lt;50% 降难度）</template>
          <div style="display: flex; gap: 8px; align-items: center">
            <el-select v-model="practiceKp" placeholder="选择知识点" style="width: 240px">
              <el-option v-for="k in kpOptions" :key="k" :label="k" :value="k" />
            </el-select>
            <el-button type="primary" :loading="loadingQuestion" @click="onNextQuestion">开始/下一题</el-button>
          </div>
          <el-empty v-if="!currentQuestion && !result" description="选择知识点后点击开始练习" />
          <div v-if="currentQuestion" style="margin-top: 16px">
            <p><b>{{ currentQuestion.stem }}</b>
              <el-tag size="small" style="margin-left: 6px">{{ currentQuestion.knowledge_point }}</el-tag>
              <el-tag size="small" type="info" style="margin-left: 4px">{{ currentQuestion.difficulty }}</el-tag>
            </p>
            <el-radio-group v-model="selectedAnswer" :disabled="!!result">
              <el-radio v-for="opt in currentQuestion.options" :key="opt" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <div style="margin-top: 12px">
              <el-button type="primary" :loading="submitting" :disabled="!selectedAnswer || !!result"
                @click="onSubmitAnswer">提交</el-button>
            </div>
          </div>
          <el-alert v-if="result" :type="result.correct ? 'success' : 'error'" :closable="false"
            style="margin-top: 16px"
            :title="result.correct ? `回答正确！正确答案：${result.answer}` : `回答错误，正确答案：${result.answer}`">
            <p style="margin: 6px 0"><b>解析：</b>{{ result.analysis }}</p>
            <p v-if="result.wrong_question" style="margin: 6px 0">
              <b>错题本：</b>
              <span v-if="result.wrong_question.status === 'generated'">已入册并生成 AI 解析（解析+错误原因+变式题），可在错题本查看</span>
              <span v-else>已入册，AI 解析生成失败，可在错题本点击"重新生成"</span>
            </p>
            <p style="margin: 6px 0; color: #666">当前练习难度：{{ result.difficulty_new }}</p>
          </el-alert>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="错题本" name="wrongbook">
        <el-card>
          <template #header>AIGC 错题本（答错自动入册：解析 + 错误原因 + 2~3 道变式题）</template>
          <el-empty v-if="!wrongbook.length" description="还没有错题，继续加油！" />
          <el-collapse v-else>
            <el-collapse-item v-for="w in wrongbook" :key="w.id">
              <template #title>
                <span style="display: inline-flex; align-items: center; gap: 6px">
                  <b>{{ w.stem.length > 40 ? w.stem.slice(0, 40) + '…' : w.stem }}</b>
                  <el-tag size="small">{{ w.knowledge_point }}</el-tag>
                  <el-tag size="small" type="info">{{ w.difficulty }}</el-tag>
                  <el-tag size="small" :type="w.status === 'generated' ? 'success' : 'warning'">
                    {{ w.status === 'generated' ? 'AI 解析已生成' : '解析待生成' }}
                  </el-tag>
                </span>
              </template>
              <p><b>我的答案：</b>{{ w.user_answer }}　<b>正确答案：</b>{{ w.correct_answer }}</p>
              <div v-if="w.status === 'generated'">
                <p><b>AI 解析：</b>{{ w.analysis }}</p>
                <p><b>错误原因：</b>{{ w.error_reason }}</p>
                <div v-if="w.variants?.length">
                  <b>变式题：</b>
                  <div v-for="(v, i) in w.variants" :key="i" style="margin: 6px 0 6px 12px">
                    <p>{{ i + 1 }}. {{ v.题干 }}</p>
                    <p style="color: #666; font-size: 13px">
                      答案：{{ v.答案 }}　解析：{{ v.解析 }}
                    </p>
                  </div>
                </div>
              </div>
              <el-button v-if="w.status !== 'generated'" size="small" type="primary"
                :loading="regeneratingId === w.id" @click="onRegenerate(w)">重新生成</el-button>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 导入历史成绩 -->
    <el-dialog v-model="importVisible" title="导入历史成绩" width="420px">
      <el-form label-width="80px">
        <el-form-item label="课程">
          <el-select v-model="importForm.course_id" placeholder="选择课程（试题来源）" style="width: 100%">
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="成绩">
          <el-input-number v-model="importForm.score" :min="0" :max="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="onImport">导入并初始化画像</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import {
  getDiagnostic, getPath, getPractice, getProfile, getSimilar, getTasks,
  importScore, listLearnCourses, listWrongbook, regenerateWrong, submitDiagnostic,
  submitPractice,
  type PathItem, type ProfileData, type Question, type PracticeResult,
  type SimilarStudent, type TaskItem, type WrongQuestionItem,
} from '@/api/learn'

const profile = ref<ProfileData | null>(null)
const path = ref<PathItem[]>([])
const tasks = ref<TaskItem[]>([])
const similar = ref<SimilarStudent[]>([])
const wrongbook = ref<WrongQuestionItem[]>([])
const activeTab = ref('dash')

// 诊断测试
const diagnosing = ref(false)
const diagQuestions = ref<Question[]>([])
const diagAnswers = reactive<Record<string, string>>({})
const submittingDiag = ref(false)

// 导入
const importVisible = ref(false)
const courses = ref<{ id: number; name: string }[]>([])
const importForm = reactive({ course_id: undefined as number | undefined, score: 60 })
const importing = ref(false)

// 练习
const practiceKp = ref('')
const kpOptions = ref<string[]>([])
const currentQuestion = ref<Question | null>(null)
const selectedAnswer = ref('')
const result = ref<PracticeResult | null>(null)
const loadingQuestion = ref(false)
const submitting = ref(false)
const regeneratingId = ref(0)

// 雷达图（dataviz 参考盘：单系列蓝 #2a78d6、无图例、轴名二级墨色、tooltip 保留）
const radarEl = ref<HTMLDivElement | null>(null)
let radarChart: echarts.ECharts | null = null

function renderRadar() {
  if (!radarEl.value || !profile.value?.kps.length) return
  if (!radarChart) radarChart = echarts.init(radarEl.value)
  const kps = profile.value.kps
  radarChart.setOption({
    title: { text: '知识点掌握度', left: 'center', textStyle: { color: '#0b0b0b', fontSize: 14 } },
    tooltip: { trigger: 'item' },
    radar: {
      indicator: kps.map(k => ({ name: k.name, max: 100 })),
      radius: '65%',
      axisName: { color: '#52514e', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e1e0d9' } },
      splitArea: { areaStyle: { color: ['#fcfcfb', '#f4f3f0'] } },
      axisLine: { lineStyle: { color: '#e1e0d9' } },
    },
    series: [{
      type: 'radar',
      data: [{ value: kps.map(k => k.mastery), name: '掌握度' }],
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2, color: '#2a78d6' },
      itemStyle: { color: '#2a78d6' },
      areaStyle: { color: 'rgba(42, 120, 214, 0.15)' },
    }],
  })
}

async function loadDashboard() {
  profile.value = await getProfile()
  if (!profile.value.initialized) return
  const [p, t, s] = await Promise.all([getPath(), getTasks(), getSimilar()])
  path.value = p.path
  tasks.value = t
  similar.value = s
  kpOptions.value = p.path.map(x => x.name).concat(
    profile.value.kps.filter(k => !p.path.some(x => x.name === k.name)).map(k => k.name),
  )
  if (!practiceKp.value) practiceKp.value = kpOptions.value[0] || ''
  renderRadar()
}

async function loadWrongbook() {
  wrongbook.value = await listWrongbook()
}

async function startDiagnostic() {
  const data = await getDiagnostic()
  diagQuestions.value = data.questions
  diagnosing.value = true
}

async function onSubmitDiagnostic() {
  const unanswered = diagQuestions.value.find(q => !diagAnswers[q.stem])
  if (unanswered) { ElMessage.warning('还有题目未作答'); return }
  submittingDiag.value = true
  try {
    const answers = diagQuestions.value.map(q => ({
      lesson_id: q.lesson_id, stem: q.stem, answer: diagAnswers[q.stem],
    }))
    await submitDiagnostic(answers)
    ElMessage.success('画像初始化完成')
    diagnosing.value = false
    diagQuestions.value = []
    await loadDashboard()
  } finally {
    submittingDiag.value = false
  }
}

async function onImport() {
  if (!importForm.course_id) { ElMessage.warning('请选择课程'); return }
  importing.value = true
  try {
    await importScore(importForm.course_id, importForm.score)
    ElMessage.success('画像初始化完成')
    importVisible.value = false
    await loadDashboard()
  } finally {
    importing.value = false
  }
}

function startTaskPractice(t: TaskItem) {
  practiceKp.value = t.name
  activeTab.value = 'practice'
  onNextQuestion()
}

async function onNextQuestion() {
  if (!practiceKp.value) { ElMessage.warning('请先选择知识点'); return }
  loadingQuestion.value = true
  result.value = null
  selectedAnswer.value = ''
  try {
    currentQuestion.value = await getPractice(practiceKp.value)
  } catch (e) {
    currentQuestion.value = null
  } finally {
    loadingQuestion.value = false
  }
}

async function onSubmitAnswer() {
  if (!currentQuestion.value || !selectedAnswer.value) return
  submitting.value = true
  try {
    result.value = await submitPractice(
      currentQuestion.value.lesson_id, currentQuestion.value.stem, selectedAnswer.value)
    if (!result.value.correct) loadWrongbook()
  } finally {
    submitting.value = false
  }
}

async function onRegenerate(w: WrongQuestionItem) {
  regeneratingId.value = w.id
  try {
    const updated = await regenerateWrong(w.id)
    const idx = wrongbook.value.findIndex(x => x.id === w.id)
    if (idx >= 0) wrongbook.value[idx] = { ...wrongbook.value[idx], ...updated }
    ElMessage.success('AI 解析已重新生成')
  } finally {
    regeneratingId.value = 0
  }
}

onMounted(async () => {
  await loadDashboard()
  await loadWrongbook()
})
watch(profile, renderRadar)
onBeforeUnmount(() => { radarChart?.dispose(); radarChart = null })
</script>
```

- [ ] **Step 4: 路由与菜单**

`frontend/src/router/index.ts` 中 `/module/assistant` 行之后追加：

```typescript
    { path: '/module/learn', component: () => import('@/views/learn/LearnView.vue') },
```

`frontend/src/views/HomeView.vue` 菜单项改为按角色显示：

```vue
        <el-menu-item v-if="auth.user?.role === 'student'" index="/module/learn">个性化学习</el-menu-item>
```

- [ ] **Step 5: 构建验证**

Run: `cd frontend && npm run build && npx tsc --noEmit`
Expected: build 成功（允许既有 chunk 警告）；tsc 0 错误

- [ ] **Step 6: 提交**

```bash
cd frontend
git add package.json package-lock.json src/api/learn.ts src/views/learn/LearnView.vue src/router/index.ts src/views/HomeView.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 个性化学习前端页——画像雷达图/推荐路径/今日任务/相似学生/自适应练习/错题本"
```

---

### Task 8: 演示数据 seed（知识图谱 + 演示习题集）+ 工单19 测试文档 + README

**Files:**
- Modify: `backend/scripts/seed_demo_data.py`（seed_learn_demo）
- Modify: `backend/requirements.txt`（networkx、numpy 钉版）
- Create: `docs/工单19-个性化学习推荐-测试用例与结果.md`
- Modify: `README.md`（个性化学习模块说明 + 工单对照）

**Interfaces:**
- Consumes: Task 1 模型（KnowledgePoint/KpPrereq/Lesson）
- Produces: 演示数据（12 知识点 + 前置关系 + 18 题习题集，幂等）；工单19 测试文档

- [ ] **Step 1: requirements 钉版**

`backend/requirements.txt` 末尾追加：

```
networkx>=3.0
numpy>=1.26
```

- [ ] **Step 2: 扩展 seed 脚本**

`backend/scripts/seed_demo_data.py` 修改 import 区（现有 `from app.models.prep import Course, CourseFile` 补充 Lesson；新增 learn 模型导入）：

```python
from app.models.learn import KnowledgePoint, KpPrereq
from app.models.prep import Course, CourseFile, Lesson   # 原为 Course, CourseFile，补充 Lesson
```

文件末尾（`make_demo_files` 之后、`__main__` 之前）追加：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
LEARN_KPS = [
    ("Python基础", "Python 语法与常用库入门"),
    ("线性代数", "向量、矩阵运算与线性变换"),
    ("概率统计", "概率分布与统计推断基础"),
    ("梯度下降", "沿负梯度方向迭代更新参数的最优化算法"),
    ("线性回归", "拟合特征与目标间线性关系的回归模型"),
    ("逻辑回归", "对数几率模型，解决二分类问题"),
    ("决策树", "基于特征划分的树形分类模型"),
    ("神经网络", "多层神经元连接构成的学习模型"),
    ("反向传播", "链式法则逐层计算梯度的训练算法"),
    ("深度学习基础", "多层神经网络的训练与调优"),
    ("卷积神经网络", "卷积+池化提取空间特征的深度网络"),
    ("自然语言处理", "让计算机理解与生成自然语言的技术"),
]

LEARN_PREREQS = [
    ("梯度下降", "Python基础"), ("梯度下降", "线性代数"),
    ("线性回归", "梯度下降"), ("线性回归", "Python基础"),
    ("逻辑回归", "线性回归"),
    ("决策树", "概率统计"),
    ("反向传播", "梯度下降"),
    ("神经网络", "线性回归"), ("神经网络", "反向传播"),
    ("深度学习基础", "神经网络"),
    ("卷积神经网络", "深度学习基础"),
    ("自然语言处理", "深度学习基础"),
]


def _ex(stem, answer, kp, diff, analysis):
    """演示习题工厂：题干/选项/答案/解析/知识点/难度。"""
    return {"题干": stem, "选项": ["A.学习率", "B.批量大小", "C.迭代次数", "D.正则化系数"],
            "答案": answer, "解析": analysis, "知识点": kp, "难度": diff}


LEARN_EXERCISES = [
    _ex("Python 中定义函数使用的关键字是？", "A", "Python基础", "易",
        "Python 用 def 关键字定义函数（A 是虚构选项），func/function/define 均不是关键字。"),
    _ex("两个矩阵能够相乘的前提是？", "A", "线性代数", "易",
        "矩阵乘法要求左矩阵列数等于右矩阵行数。"),
    _ex("事件发生的概率取值范围是？", "A", "概率统计", "易",
        "概率取值恒在 [0,1] 区间。"),
    _ex("梯度下降算法中控制每次更新步长的参数是？", "A", "梯度下降", "易",
        "学习率控制参数每次更新的步长。"),
    _ex("梯度下降中参数更新方向是？", "A", "梯度下降", "易",
        "沿损失函数的负梯度方向迭代更新参数，损失逐步减小。"),
    _ex("学习率过大会导致什么？", "B", "梯度下降", "中",
        "学习率过大步长过大，损失会震荡甚至发散；过小则收敛缓慢。"),
    _ex("关于批量梯度下降与小批量梯度下降，说法正确的是？", "A", "梯度下降", "难",
        "批量梯度下降每步使用全部样本、计算开销大；小批量是折中方案，不保证一定更快收敛。"),
    _ex("以下哪个场景最适合线性回归？", "A", "线性回归", "易",
        "线性回归拟合连续值，典型场景是房价预测。"),
    _ex("线性回归常用的损失函数是？", "A", "线性回归", "中",
        "线性回归用均方误差（MSE）衡量预测与真实值的差距。"),
    _ex("多元线性回归中特征存在高度共线性，通常会导致？", "A", "线性回归", "难",
        "共线性使系数估计不稳定（方差大），不影响模型可训练性。"),
    _ex("逻辑回归主要用于解决什么问题？", "A", "逻辑回归", "易",
        "逻辑回归是对数几率模型，解决二分类问题。"),
    _ex("逻辑回归把线性输出映射到 0~1 区间的函数是？", "A", "逻辑回归", "中",
        "Sigmoid 函数把任意实数映射到 (0,1)，输出即概率。"),
    _ex("决策树中用于选择划分特征的主要指标是？", "A", "决策树", "易",
        "决策树按信息增益（或基尼指数）选择划分特征。"),
    _ex("以下哪个不是常用的激活函数？", "C", "神经网络", "中",
        "ReLU/Sigmoid/Tanh 都是常用激活函数；恒等函数无非线性，不常用作隐藏层激活。"),
    _ex("反向传播算法利用什么法则逐层计算梯度？", "A", "反向传播", "中",
        "反向传播利用链式法则逐层计算梯度，与梯度下降配合更新参数。"),
    _ex("深度学习中的“深度”主要指什么？", "A", "深度学习基础", "易",
        "深度指网络层数多（多层非线性变换）。"),
    _ex("卷积神经网络中池化层的主要作用是？", "A", "卷积神经网络", "中",
        "池化层降低特征维度、保留主要特征并提升平移不变性。"),
    _ex("以下哪个任务属于自然语言处理？", "A", "自然语言处理", "中",
        "情感分析是典型 NLP 任务；图像分割属 CV、语音降噪属语音、路径规划属搜索。"),
]


def seed_learn_demo(db) -> None:
    """个性化学习演示数据：知识图谱（12 知识点+前置关系）+ 演示习题集（18 题，覆盖全部知识点）。幂等。"""
    if db.query(KnowledgePoint).count() > 0:
        print("知识图谱已有数据，跳过")
    else:
        kp_by_name = {}
        for name, desc in LEARN_KPS:
            kp = KnowledgePoint(name=name, description=desc)
            db.add(kp)
            db.flush()
            kp_by_name[name] = kp.id
        for kp_name, pre_name in LEARN_PREREQS:
            db.add(KpPrereq(kp_id=kp_by_name[kp_name], prereq_kp_id=kp_by_name[pre_name]))
        db.commit()
        print("知识图谱已就绪：12 个知识点 + 前置关系")
    course = db.query(Course).filter(Course.name == "人工智能导论").first()
    if course is not None:
        exists = (db.query(Lesson).filter(Lesson.title == "个性化学习演示习题",
                                          Lesson.course_id == course.id).first())
        if exists is None:
            db.add(Lesson(course_id=course.id, title="个性化学习演示习题",
                          lesson_type="exercises", content_json={"习题": LEARN_EXERCISES},
                          version=1, created_by=course.owner_id))
            db.commit()
            print("个性化学习演示习题集已就绪：18 题（覆盖全部知识点）")
```

`__main__` 中 `seed_kb_demo(db)` 之后追加：

```python
        seed_learn_demo(db)
```

- [ ] **Step 3: 跑 seed（幂等验证）**

Run（HF 离线，本机 huggingface 不可达；kb seed 已有数据会跳过）：
```
cd backend && HF_HUB_OFFLINE=1 python -m scripts.seed_demo_data
```
Expected: 输出"知识图谱已就绪…"与"个性化学习演示习题集已就绪…"；**再跑一次**，输出"知识图谱已有数据，跳过"且不重复建习题（幂等 ✓）

- [ ] **Step 4: 写工单19 测试文档**

`docs/工单19-个性化学习推荐-测试用例与结果.md`（先建骨架与用例清单，实测结果跑完全量后回填"实测结果"列）：

```markdown
# 工单 19 个性化学习推荐：测试用例与结果

**测试范围**：诊断测试与初始画像 / 画像仪表盘数据 / 知识图谱路径推荐 / 自适应练习 / AIGC 错题本 / 画像持续迭代 / 相似学生推荐 / 权限隔离。

**测试环境**：Windows 11 + Python（FastAPI 测试客户端）+ SQLite 临时库 + 假 LLM/向量替身（单测层不依赖 DeepSeek 与 bge-m3）；浏览器人工验证在 http://localhost:5173（后端 8000）。

## 一、用例清单

| 编号 | 用例 | 预期结果 | 实测结果 |
|---|---|---|---|
| 1 | 非学生角色访问 /api/learn/* | 403"权限不足" | 待回填 |
| 2 | 未登录访问 /api/learn/profile | 401 | 待回填 |
| 3 | 学生访问他人错题（regenerate） | 404 错题不存在 | 待回填 |
| 4 | 相似学生仅返回姓名+知识点名 | 不含对方掌握度明细 | 待回填 |
| 5 | 获取诊断测试题 | 默认≤10 题、易/中优先、不带答案、题干去重 | 待回填 |
| 6 | 提交诊断测试 | 每知识点掌握度=正确率×100，画像初始化 | 待回填 |
| 7 | 诊断答题与题库不匹配 | 400 友好提示 | 待回填 |
| 8 | 导入历史成绩 | 课程知识点均匀初始化=成绩值 | 待回填 |
| 9 | 成绩超 0~100 / 课程无试题 | 400 友好提示 | 待回填 |
| 10 | 未初始化画像查询 | initialized=False | 待回填 |
| 11 | 画像雷达数据 | 全图谱知识点，无记录=0，含时间衰减 | 待回填 |
| 12 | 练习答对/答错画像增量 | +10 / -15，夹取 [0,100] | 待回填 |
| 13 | 助教提问命中知识点 | +2 事件；失败不影响问答流 | 待回填 |
| 14 | 时间衰减 | 每天 ×0.95 | 待回填 |
| 15 | 知识图谱拓扑排序 | 前置知识点先于后置 | 待回填 |
| 16 | 推荐学习路径 | 未掌握按拓扑序+可解释理由 | 待回填 |
| 17 | 全部掌握 | 路径为空、mastered 计数正确 | 待回填 |
| 18 | 图谱含环 | 降级节点 id 顺序不报错 | 待回填 |
| 19 | 自适应练习抽题 | 按当前难度抽题、不带答案 | 待回填 |
| 20 | 该难度无题 | 放宽到该知识点全部题 | 待回填 |
| 21 | 练习提交判分 | 后端按 lesson_id+题干比对答案 | 待回填 |
| 22 | 正确率>80% | 难度升档 | 待回填 |
| 23 | 正确率<50% | 难度降档 | 待回填 |
| 24 | 答错入错题本 | 自动入册+AI 解析生成（假 LLM） | 待回填 |
| 25 | LLM 失败 | 错题保留 status=failed，接口不报错 | 待回填 |
| 26 | 错题本列表/重新生成 | 仅本人；重新生成更新解析 | 待回填 |
| 27 | 相似学生推荐 | 余弦相似度 top3 + 借鉴知识点 | 待回填 |
| 28 | 今日任务 | 推荐路径前 2 项+各配练习题 | 待回填 |
| 29 | 前端构建 | npm run build 通过、tsc 0 错误 | 待回填 |
| 30 | 浏览器人工验收 | 菜单按角色显示/诊断→仪表盘/练习/错题本全流程 | 人工验收 |

## 二、口径说明

1. **知识图谱后端**：本机未安装 Neo4j，按工单 16 退化方案用 SQL 表 + networkx 实现（"不影响验收"）；graph 服务封装数据来源，未来可无痛切 Neo4j。
2. **试题复用**：工单 17 试题存于 Lesson（lesson_type=exercises/exam）的 content_json，练习/诊断仅取含"选项"的选择题；Exercise 表空置不用。
3. **答案不出后端**：练习与诊断按 lesson_id+题干全文定位原题，后端比对正确答案（防前端作弊）。
4. **错题生成时机**：答题提交时同步生成（约 5~20s）；LLM 失败错题保留（status=failed），接口正常返回，错题本可"重新生成"。
5. **导入历史成绩口径**：课程级成绩 0~100 均匀初始化该课程试题涉及的知识点（非逐知识点成绩）。
6. **GET 抽题副作用**：GET /api/learn/practice 会幂等创建默认画像行（mastery=0、难度易），不产生事件。
7. **画像公式**：时间衰减每天 ×0.95；练习答对 +10、答错 -15、提问 +2；未掌握阈值 60；难度档 易/中/难，滚动最近 10 次正确率（样本不足 5 不调整）>0.8 升档、<0.5 降档。
8. **相似学生隐私**：仅返回姓名与"对方掌握而我未掌握"的知识点名，不返回对方完整画像（设计文档 §331）。
9. **诊断测试口径**：默认 10 题（不足取全部）、易/中优先、题干去重、轮询覆盖知识点；初始画像=每知识点正确率×100 直接赋值。

## 三、测试结果汇总

（回填：`cd backend && python -m pytest` 全量结果，如 "全量 XXX passed, N deselected（Xs）"）

## 附：验收标准对照（完成标准 Plan D）

| 验收标准（工单19 §2.2.4） | 实现 | 验证方式 |
|---|---|---|
| 诊断测试与初始画像（复用工单17试题或导入历史成绩） | /api/learn/diagnostic + /import | 用例 5~9 |
| 画像仪表盘（雷达图+推荐路径+今日任务） | /module/learn 仪表盘 tab | 用例 10/11/16/28/30 |
| 知识图谱路径推荐（未掌握+前置拓扑排序+可解释） | learn_graph 服务 + /api/learn/path | 用例 15~17 |
| 自适应练习（>80% 升难度、<50% 降难度） | learn_practice 服务 | 用例 19~23 |
| AIGC 错题本（解析+错误原因+2~3 变式题） | learn_wrongbook 服务 | 用例 24~26 |
| 画像持续迭代（加权+时间衰减，答题/助教提问） | learn_profile 服务 + kb 联动 | 用例 12~14 |
| （加分）相似学生推荐（numpy 协同过滤） | learn_profile.similar_students | 用例 4/27 |
```

- [ ] **Step 5: README 更新**

`README.md` 的 `## 智能助教（工单 18）` 节之后插入：

```markdown
## 个性化学习（工单 19）

- **学习画像**：学生首次登录完成诊断测试（复用备课模块试题）或导入历史成绩 → 初始画像；画像随练习答题、助教提问持续迭代（加权 + 时间衰减：每天掌握度 ×0.95；答对 +10 / 答错 -15 / 提问 +2）。
- **知识图谱路径推荐**：知识点前置关系拓扑排序（SQL 表 + networkx，本机未装 Neo4j 按工单16 退化方案，不影响验收），未掌握知识点带"为什么推荐学这个"解释。
- **画像仪表盘**：掌握度雷达图（ECharts）+ 推荐学习路径 + 今日任务 + 相似学生（numpy 协同过滤）。
- **自适应练习**：按当前难度抽题（易/中/难），滚动正确率 >80% 升难度、<50% 降难度。
- **AIGC 错题本**：答错自动入册，DeepSeek 生成解析 + 错误原因 + 2~3 道变式题（提交时同步生成；失败错题保留，可在错题本"重新生成"）。
- 演示：student/student123 → 个性化学习 → 诊断测试 → 仪表盘/练习/错题本（图谱与习题由 seed 预置；生成类功能需 DEEPSEEK_API_KEY）。
- 口径说明（课程级成绩导入、试题复用选择题、GET 抽题建默认画像行等）见 `docs/工单19-个性化学习推荐-测试用例与结果.md`。
```

工单对照表追加一行：

```markdown
| 19 | 个性化学习推荐 | ✅ docs/工单19-个性化学习推荐-测试用例与结果.md |
```

- [ ] **Step 6: 全量回归 + 回填文档实测结果**

Run: `cd backend && python -m pytest`
Expected: 全部通过（108 既有 + 36 新增 = 144 passed, 2 deselected，实际数以输出为准）

把真实结果回填进文档"三、测试结果汇总"与用例清单"实测结果"列（全为 ✅/通过），并 `git add` 文档。

- [ ] **Step 7: 提交**

```bash
git add backend/requirements.txt backend/scripts/seed_demo_data.py docs/工单19-个性化学习推荐-测试用例与结果.md README.md
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 工单19 演示数据 seed（图谱+习题集）+ 测试用例文档 + README"
```

---

## 完成标准（Plan D）

- [ ] 后端全量 pytest 通过（既有用例无回归 + 本计划新增用例全过）
- [ ] 前端 `npm run build` 通过 + `npx tsc --noEmit` 0 错误
- [ ] seed 幂等：连跑两次第二次全跳过
- [ ] 工单19 测试用例文档完成（用例清单 + 口径说明 + 实测结果 + 验收标准对照）
- [ ] README 含个性化学习模块说明与工单对照
- [ ] 浏览器人工验收（本机 5173）：student/student123 登录 → 个性化学习 → 诊断测试 → 仪表盘（雷达图/路径/今日任务/相似学生）→ 自适应练习（难度升降）→ 错题本（AI 解析+变式题）全流程；teacher 登录不显示个性化学习菜单
