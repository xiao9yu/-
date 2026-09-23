# 个性化学习多方向与题库扩充（Plan G）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 个性化学习从单一「人工智能导论」方向扩展为 3 个学习方向（人工智能导论 / 数据结构与算法 / 机器学习），每方向 72 道手工种子题（12 知识点 × 易2/中2/难2），并打通题目三通道（月考题自动入池 / 知识库出题 / 手工种子）。

**Architecture:** 知识点表加 course_id 课程隔离（多方向同名知识点互不影响），画像/路径/任务/错题本接口按课程过滤；备课新增 `kb_exercises` 生成类型（知识库 RAG → LLM 出题 → 校验 → 追加进课程习题集 lesson）；前端 LearnView 加学习方向选择器联动全部面板，备课页加「知识库出题」入口。

**Tech Stack:** FastAPI + SQLAlchemy（SQLite）｜Vue3 + Element Plus ｜seed 幂等脚本 ｜既有 RAG（hybrid_retrieve）/ LLM 网关复用

## Global Constraints

- 提交身份 `git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local"`，**只在 master 直提**（2026-09-22 收尾日全天直提先例）；commit footer 必须带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- **绝不 `git add -A`**：显式路径提交；仓库根有无关未跟踪文件（实训日报-七天.md 等），vite.config.ts 的本机 8002 代理补丁**不提交**。
- pytest 从 `backend/` 跑、**不传 `--basetemp`**；本机退出码不可信，**判读看逐用例输出**（`pytest -v > out.txt` 后数 PASSED/FAILED）。基线 **295 passed, 2 deselected**，47 条 warnings 为既有基线噪声。
- 前端验证：`cd frontend && npm run build && npx tsc --noEmit`（无单测基建）。
- UI 中文文案、Element Plus 图标，**禁 emoji**；样式沿用既有设计 token（main.css 变量）。
- 子代理**不指定 model**（Anthropic 402 余额问题，继承主会话模型）。
- 习题 schema（与既有 `_ex` 工厂一致）：`{题干, 选项[4 个含前缀字母], 答案(A~D 字母), 解析, 知识点, 难度(易|中|难)}`；**每知识点每难度恰好 2 题**；题干在同一方向内唯一。
- 种子题内容**逐字按本计划落库，不得改写题干/选项/答案**（内容已审校）。
- 知识库出题检索走公共库+私有库混合检索（与问答同路径 `hybrid_retrieve`）；测试按既有约定注入假嵌入/假向量库或 monkeypatch。
- 部署顺序（本机旧库升级）：停后端 → `cd backend && python -m scripts.seed_demo_data`（执行 ALTER 迁移+回填+数据）→ 重启后端 → 前端热更新。
- 真实 DeepSeek key 只在 gitignored backend/.env；输出中掩码。
- 每个子代理派发合同：读任务简报、TDD RED-GREEN（先写测试并记录失败输出）、提交前跑覆盖测试并记录输出、报告写入报告文件。

---

### Task 1: 知识点课程隔离 + 旧库迁移 + 学习接口方向贯穿

**Files:**
- Modify: `backend/app/models/learn.py`（KnowledgePoint）
- Modify: `backend/app/services/learn_profile.py`
- Modify: `backend/app/services/learn_graph.py`
- Modify: `backend/app/services/learn_practice.py`
- Modify: `backend/app/services/learn_wrongbook.py`
- Modify: `backend/app/api/learn.py`
- Modify: `backend/scripts/seed_demo_data.py`（migrate_learn_schema + main 调用）
- Test: `backend/tests/test_learn_migration.py`（新建）、`backend/tests/test_learn_practice.py`、`backend/tests/test_learn_profile.py`、`backend/tests/test_learn_graph.py`、`backend/tests/test_learn_api.py`（追加用例）

**Interfaces:**
- Consumes: `models/learn.py` 现有 KnowledgePoint/ProfileKp/LearnEvent/WrongQuestion；`models/prep.py` 的 Course/Lesson；各测试文件既有 `db`/`user`/`env` 夹具（test_learn_practice.py、test_learn_profile.py、test_learn_graph.py 各自有 `db` fixture，test_learn_api.py 用 `env` fixture 产出 (client, headers, tmp_path, Session, course)）。
- Produces（后续任务依赖的精确签名）：
  - `KnowledgePoint.course_id: int | None`（FK courses.id，nullable，index）+ 表级 `UniqueConstraint("course_id", "name", name="uq_kp_course_name")`
  - `learn_profile.get_or_create_kp(db, name, course_id=None)`
  - `learn_profile.get_profile(user, db, course_id=None)`
  - `learn_profile.init_from_diagnostic(user, answers, db)`（answers 条目带 `course_id` 可选键）
  - `learn_profile.init_from_import(user, kp_names, score, db, course_id=None)`
  - `learn_graph.build_graph(db, course_id=None)`、`learn_graph.recommend_path(mastery_map, db, course_id=None)`
  - `learn_practice.next_question(user, kp, db, *, course_id=None, prev_stem=None)`
  - `learn_wrongbook.list_wrongbook(user, db, course_id=None)`
  - `scripts.seed_demo_data.migrate_learn_schema(db)`（幂等）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_learn_migration.py` 新建：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
"""Plan G 知识点课程隔离与旧库迁移测试：同名知识点分课程共存、旧库加列回填、唯一约束重建。"""
import sqlalchemy as sa
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint
from app.models.prep import Course
from app.models.user import Role, User


@pytest.fixture
def db(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


def test_kp_same_name_allowed_in_different_courses(db):
    """同一知识点名在不同课程下互不冲突；同课程同名违反唯一约束。"""
    teacher = User(username="t", hashed_password="x", role=Role.teacher)
    db.add(teacher)
    db.flush()
    c1 = Course(name="课程甲", subject="x", owner_id=teacher.id)
    c2 = Course(name="课程乙", subject="x", owner_id=teacher.id)
    db.add_all([c1, c2])
    db.flush()
    db.add(KnowledgePoint(name="决策树", course_id=c1.id))
    db.add(KnowledgePoint(name="决策树", course_id=c2.id))
    db.commit()  # 不同课程同名合法
    db.add(KnowledgePoint(name="决策树", course_id=c1.id))
    with pytest.raises(Exception):  # IntegrityError：同课程同名撞唯一约束
        db.commit()


def _legacy_db(tmp_path):
    """构造 Plan G 之前的旧库：knowledge_points 无 course_id 列、name 全局唯一索引。"""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE courses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "name VARCHAR(100))"))
        conn.execute(text("INSERT INTO courses (name) VALUES ('人工智能导论')"))
        conn.execute(text("CREATE TABLE knowledge_points ("
                          "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                          "name VARCHAR(100), description TEXT, created_at DATETIME)"))
        conn.execute(text("CREATE UNIQUE INDEX ix_knowledge_points_name "
                          "ON knowledge_points (name)"))
        conn.execute(text("INSERT INTO knowledge_points (name) VALUES ('梯度下降')"))
    return engine


def test_migrate_learn_schema_backfills_and_reindexes(tmp_path):
    """旧库 → 迁移后：加列、回填 AI 课程、移除旧 name 唯一索引、重建 (course_id, name) 唯一索引；幂等。"""
    from scripts import seed_demo_data
    engine = _legacy_db(tmp_path)
    Session = sessionmaker(bind=engine)
    db = Session()
    seed_demo_data.migrate_learn_schema(db)
    cols = {c["name"] for c in sa.inspect(engine).get_columns("knowledge_points")}
    assert "course_id" in cols
    row = db.execute(text("SELECT kp.name, c.name FROM knowledge_points kp "
                          "JOIN courses c ON kp.course_id = c.id")).fetchone()
    assert tuple(row) == ("梯度下降", "人工智能导论")  # 旧知识点回填 AI 课程
    idx = {r[1]: bool(r[2]) for r in db.execute(text("PRAGMA index_list(knowledge_points)"))}
    assert idx.get("uq_kp_course_name") is True        # 新唯一索引存在
    assert "ix_knowledge_points_name" not in idx       # 旧 name 唯一索引已移除
    seed_demo_data.migrate_learn_schema(db)            # 幂等：再跑一遍不报错
```

`backend/tests/test_learn_practice.py` 末尾追加：

```python
def test_next_question_prev_stem_avoids_immediate_repeat(db, user):
    """prev_stem 非空且候选池 >1 时，下一题不与上一题同题干（解决"下一题还是同一道"）。"""
    course = Course(name="课程", subject="x", owner_id=1)
    db.add(course)
    db.flush()
    lesson = Lesson(course_id=course.id, title="习题集", lesson_type="exercises",
                    content_json={"习题": [
                        _question("题目甲", "A", kp="知识点A"),
                        _question("题目乙", "A", kp="知识点A"),
                    ]}, created_by=1)
    db.add(lesson)
    db.commit()
    q1 = learn_practice.next_question(user, "知识点A", db, course_id=course.id,
                                      prev_stem="题目甲")
    assert q1["stem"] == "题目乙"
    # 排除后只剩 1 题时回退全池（允许重复，防无题可出）
    q2 = learn_practice.next_question(user, "知识点A", db, course_id=course.id,
                                      prev_stem="题目乙")
    assert q2["stem"] in ["题目甲", "题目乙"]
```

`backend/tests/test_learn_profile.py` 末尾追加：

```python
def test_profile_course_scoped_and_per_direction_init(db, user):
    """画像按课程过滤：方向 A 初始化不影响方向 B；kps 只含本课程知识点。"""
    from app.models.prep import Course
    ca = Course(name="课程A", subject="x", owner_id=1)
    cb = Course(name="课程B", subject="x", owner_id=1)
    db.add_all([ca, cb])
    db.flush()
    learn_profile.init_from_import(user, ["知识点A"], 60, db, course_id=ca.id)
    pa = learn_profile.get_profile(user, db, course_id=ca.id)
    pb = learn_profile.get_profile(user, db, course_id=cb.id)
    assert pa["initialized"] is True
    assert [k["name"] for k in pa["kps"]] == ["知识点A"]
    assert pb["initialized"] is False  # B 方向未初始化
```

`backend/tests/test_learn_graph.py` 末尾追加：

```python
def test_path_course_scoped(db):
    """推荐路径只在指定课程图谱内拓扑排序，不混入其他课程知识点。"""
    from app.models.prep import Course
    ca = Course(name="课程A", subject="x", owner_id=1)
    cb = Course(name="课程B", subject="x", owner_id=1)
    db.add_all([ca, cb])
    db.flush()
    k1 = KnowledgePoint(name="前置", course_id=ca.id)
    k2 = KnowledgePoint(name="后继", course_id=ca.id)
    k3 = KnowledgePoint(name="异课", course_id=cb.id)
    db.add_all([k1, k2, k3])
    db.flush()
    db.add(KpPrereq(kp_id=k2.id, prereq_kp_id=k1.id))
    db.commit()
    r = recommend_path({}, db, course_id=ca.id)
    names = [p["name"] for p in r["path"]]
    assert set(names) == {"前置", "后继"}   # 异课知识点不出现
    assert names == ["前置", "后继"]        # 拓扑序：前置先学
```

`backend/tests/test_learn_api.py` 末尾追加（复用该文件 `env` 夹具，`User`/`Course` 已 import；`WrongQuestion` 用函数内 import）：

```python
def test_diagnostic_course_scoped(env):
    client, headers, *_ = env
    # 指定其他课程 → 无试题 404
    resp = client.get("/api/learn/diagnostic?course_id=999999", headers=headers["student"])
    assert resp.status_code == 404


def test_practice_prev_stem(env):
    client, headers, _, _, course = env
    url = (f"/api/learn/practice?kp=梯度下降&course_id={course.id}"
           f"&prev_stem=诊断梯度下降题0")
    resp = client.get(url, headers=headers["student"])
    assert resp.status_code == 200
    assert resp.json()["stem"] != "诊断梯度下降题0"


def test_wrongbook_course_filter(env):
    client, headers, _, Session, course = env
    from app.models.learn import KnowledgePoint, WrongQuestion
    s = Session()
    student = s.query(User).filter(User.username == "student").first()
    course_b = Course(name="课程B", subject="x", owner_id=1)
    s.add(course_b)
    s.flush()
    s.add_all([KnowledgePoint(name="决策树", course_id=course.id),
               KnowledgePoint(name="决策树", course_id=course_b.id)])
    s.flush()
    s.add_all([
        WrongQuestion(user_id=student.id, stem="错题A", user_answer="B",
                      correct_answer="A", knowledge_point="决策树"),
        WrongQuestion(user_id=student.id, stem="错题B", user_answer="B",
                      correct_answer="A", knowledge_point="聚类"),
    ])
    s.commit()
    resp = client.get(f"/api/learn/wrongbook?course_id={course.id}",
                      headers=headers["student"])
    assert resp.status_code == 200
    assert [w["stem"] for w in resp.json()] == ["错题A"]
    s.close()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_learn_migration.py tests/test_learn_practice.py::test_next_question_prev_stem_avoids_immediate_repeat tests/test_learn_profile.py::test_profile_course_scoped_and_per_direction_init tests/test_learn_graph.py::test_path_course_scoped tests/test_learn_api.py::test_diagnostic_course_scoped tests/test_learn_api.py::test_practice_prev_stem tests/test_learn_api.py::test_wrongbook_course_filter -v`
Expected: 全部 FAIL（`course_id` 列不存在 / `migrate_learn_schema` 不存在 / 参数不接受 / 旧行为不满足断言）。记录失败输出为 RED 证据。

- [ ] **Step 3: 实现**

`backend/app/models/learn.py` —— import 行补 `UniqueConstraint`，KnowledgePoint 改为：

```python
class KnowledgePoint(Base):
    """知识点节点。name 与工单17 试题的"知识点"字段对齐（画像/练习按名关联）。

    Plan G：新增 course_id 课程隔离（多学习方向）；同名知识点在不同课程互不影响。
    唯一约束为表级 (course_id, name)；旧库迁移见 scripts/seed_demo_data.py 的
    migrate_learn_schema（加列 + 回填 + 重建唯一索引）。course_id 为空 = 旧数据/未分类兜底。
    """

    __tablename__ = "knowledge_points"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_kp_course_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
```

`backend/app/services/learn_profile.py` —— 替换 4 个函数（其余不动，record_ask_events/similar_students 保持全局）：

```python
def get_or_create_kp(db: Session, name: str, course_id: int | None = None) -> KnowledgePoint:
    """按 (课程, 名) 取知识点；试题/提问引用了图谱外的知识点时自动登记为孤立节点（容错）。

    Plan G：course_id 非空时按课程隔离查找（多方向同名知识点互不影响）；空 = 全局兜底
    （旧调用/未分类场景，兼容旧数据）。
    """
    query = db.query(KnowledgePoint).filter(KnowledgePoint.name == name)
    if course_id is not None:
        query = query.filter(KnowledgePoint.course_id == course_id)
    kp = query.first()
    if kp is None:
        kp = KnowledgePoint(name=name, course_id=course_id, description="（由学习行为自动登记）")
        db.add(kp)
        db.flush()
    return kp


def init_from_diagnostic(user: User, answers: list[dict], db: Session) -> dict:
    """诊断测试初始化画像：answers = [{"knowledge_point": str, "correct": bool, "course_id"?: int}]。

    每知识点掌握度 = 正确率 ×100 直接赋值（初始不叠加、不衰减）。course_id 用于
    多方向同名知识点隔离（Plan G）。
    """
    stats: dict[tuple, list] = {}
    for a in answers:
        stats.setdefault((a["knowledge_point"], a.get("course_id")), []).append(bool(a["correct"]))
    profile = ensure_profile(user, db)
    now = _now()
    for (name, cid), results in stats.items():
        kp = get_or_create_kp(db, name, cid)
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


def init_from_import(user: User, kp_names: list[str], score: float, db: Session,
                     course_id: int | None = None) -> dict:
    """导入历史成绩：课程级成绩均匀初始化该课程试题涉及的知识点（口径见文档）。

    Plan G：course_id 用于同名知识点课程隔离（该课程试题的知识点归属该课程图谱）。
    """
    kp_names = sorted({n for n in kp_names if n})
    if not kp_names:
        raise BizError(400, "该课程暂无试题，无法初始化画像")
    score = _clamp(score)
    profile = ensure_profile(user, db)
    now = _now()
    for name in kp_names:
        kp = get_or_create_kp(db, name, course_id)
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


def get_profile(user: User, db: Session, course_id: int | None = None) -> dict:
    """画像雷达数据：知识点 + 掌握度（无记录=0，已含时间衰减）。

    Plan G：course_id 非空时只返回该课程知识点，且"是否已初始化"只看该课程内的
    diagnostic/import 事件（方向独立画像）；空 = 全部课程（旧调用兼容）。

    初始化判定：存在 diagnostic/import 事件才算已初始化（评审修复）——
    仅练习/提问事件也会产生画像行，但按模型文档语义"未做诊断测试/导入"不算初始化，
    否则学生跳过诊断引导直接看到全零雷达。
    """
    profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
    if profile is None:
        return {"initialized": False, "kps": [], "created_at": None}
    kp_query = db.query(KnowledgePoint)
    if course_id is not None:
        kp_query = kp_query.filter(KnowledgePoint.course_id == course_id)
    kps = kp_query.order_by(KnowledgePoint.id).all()
    init_query = (db.query(LearnEvent)
                  .filter(LearnEvent.user_id == user.id,
                          LearnEvent.event_type.in_(["diagnostic", "import"])))
    if course_id is not None:
        init_query = init_query.filter(LearnEvent.kp_id.in_([k.id for k in kps] or [0]))
    if init_query.count() == 0:
        return {"initialized": False, "kps": [], "created_at": None}
    now = _now()
    rows = {r.kp_id: r for r in db.query(ProfileKp).filter(ProfileKp.profile_id == profile.id).all()}
    out = []
    for kp in kps:
        row = rows.get(kp.id)
        mastery = round(_decayed(row.mastery, row.last_updated, now), 2) if row else 0.0
        out.append({"kp_id": kp.id, "name": kp.name, "mastery": mastery})
    return {"initialized": True, "kps": out,
            "created_at": profile.created_at.replace(tzinfo=None).isoformat()}
```

`backend/app/services/learn_graph.py` —— build_graph 与 recommend_path 加课程过滤（其余不动）：

```python
def build_graph(db: Session, course_id: int | None = None) -> nx.DiGraph:
    """知识点前置关系 → 有向图：节点=知识点 id（带 name），边 prereq_kp_id → kp_id（先学→后学）。

    Plan G：course_id 非空时只取该课程知识点与内部边（方向独立图谱）。
    """
    g = nx.DiGraph()
    kp_query = db.query(KnowledgePoint)
    if course_id is not None:
        kp_query = kp_query.filter(KnowledgePoint.course_id == course_id)
    for kp in kp_query.order_by(KnowledgePoint.id).all():
        g.add_node(kp.id, name=kp.name)
    for edge in db.query(KpPrereq).all():
        if edge.prereq_kp_id in g and edge.kp_id in g:
            g.add_edge(edge.prereq_kp_id, edge.kp_id)
    return g


def recommend_path(mastery_map: dict[int, float], db: Session,
                   course_id: int | None = None) -> dict:
    """推荐学习路径：未掌握知识点按拓扑序排列，逐项给出"为什么推荐学这个"。

    mastery_map: {kp_id: 当前掌握度（已含时间衰减）}；缺失视为 0（未掌握）。
    course_id: 非空时只在指定课程图谱内推荐（Plan G 方向化）。
    """
    graph = build_graph(db, course_id=course_id)
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

`backend/app/services/learn_practice.py` —— 替换 next_question、改 submit_answer 的知识点解析：

```python
def next_question(user: User, kp: str, db: Session, *, course_id: int | None = None,
                  prev_stem: str | None = None) -> dict:
    """下一道练习题：按当前难度抽题（该难度无题则放宽到该知识点全部题）。

    Plan G：course_id 用于知识点课程隔离与抽题范围；prev_stem 非空且候选池 >1 时
    排除与上一题同题干的题（解决"下一题还是同一道"）。
    """
    kp_row = learn_profile.get_or_create_kp(db, kp, course_id)
    row = _profile_row(user, kp_row, db)
    questions = collect_questions(db, course_id=course_id, kp=kp, difficulty=row.difficulty)
    if not questions:
        questions = collect_questions(db, course_id=course_id, kp=kp)
    if not questions:
        raise BizError(404, f"知识点「{kp}」暂无练习题，请先在智能备课模块生成对应习题")
    if prev_stem and len(questions) > 1:
        pool = [q for q in questions if q["题干"] != prev_stem] or questions
    else:
        pool = questions
    q = random.choice(pool)
    return {"lesson_id": q["lesson_id"], "stem": q["题干"], "options": q["选项"],
            "knowledge_point": q["知识点"], "difficulty": q.get("难度", row.difficulty)}
```

submit_answer 中把：

```python
    kp_name = q.get("知识点") or "未分类知识点"
    kp = learn_profile.get_or_create_kp(db, kp_name)
```

改为：

```python
    kp_name = q.get("知识点") or "未分类知识点"
    lesson = db.get(Lesson, lesson_id)
    kp = learn_profile.get_or_create_kp(db, kp_name,
                                        lesson.course_id if lesson is not None else None)
```

（函数其余部分不动。）

`backend/app/services/learn_wrongbook.py` —— import 行改为 `from ..models.learn import KnowledgePoint, WrongQuestion`，list_wrongbook 改为：

```python
def list_wrongbook(user: User, db: Session, course_id: int | None = None) -> list[WrongQuestion]:
    """本人错题本（倒序）。Plan G：course_id 非空时只返回该课程知识点对应的错题。"""
    query = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if course_id is not None:
        names = [kp.name for kp in db.query(KnowledgePoint)
                 .filter(KnowledgePoint.course_id == course_id).all()]
        query = query.filter(WrongQuestion.knowledge_point.in_(names))
    return query.order_by(WrongQuestion.id.desc()).all()
```

`backend/app/api/learn.py` —— 五个端点加 course_id、practice 加 prev_stem、submit_diagnostic 统计带课程、import_score 透传课程：

```python
@router.get("/profile")
def profile(course_id: int | None = None, user: User = Depends(_student),
            db: Session = Depends(get_db)):
    return learn_profile.get_profile(user, db, course_id=course_id)


@router.get("/path")
def path(course_id: int | None = None, user: User = Depends(_student),
         db: Session = Depends(get_db)):
    mastery_map = {k["kp_id"]: k["mastery"]
                   for k in learn_profile.get_profile(user, db, course_id=course_id)["kps"]}
    if not mastery_map:
        raise BizError(400, "尚未初始化画像，请先完成诊断测试或导入历史成绩")
    return learn_graph.recommend_path(mastery_map, db, course_id=course_id)


@router.get("/tasks")
def tasks(course_id: int | None = None, user: User = Depends(_student),
          db: Session = Depends(get_db)):
    """今日任务：推荐路径前 2 个未掌握知识点 + 各配一道推荐练习题。"""
    mastery_map = {k["kp_id"]: k["mastery"]
                   for k in learn_profile.get_profile(user, db, course_id=course_id)["kps"]}
    result = learn_graph.recommend_path(mastery_map, db, course_id=course_id)
    out = []
    for item in result["path"][:2]:
        q = learn_practice.next_question(user, item["name"], db, course_id=course_id)
        out.append({"kp_id": item["kp_id"], "name": item["name"],
                    "mastery": item["mastery"], "why": item["why"], "question": q})
    return out
```

submit_diagnostic 的 stats 追加带课程（替换现有循环内 stats.append 部分）：

```python
    stats = []
    for a in data.answers:
        # a.get 兜底畸形条目（缺 lesson_id/stem）：找不到题走 BizError→400，而非 KeyError→500
        try:
            q = learn_practice.find_question(db, a.get("lesson_id"), a.get("stem") or "")
        except BizError:
            raise BizError(400, "答题与题库不匹配，请重新开始诊断测试")
        lesson = db.get(Lesson, a.get("lesson_id"))
        stats.append({
            "knowledge_point": q.get("知识点") or "未分类知识点",
            "correct": learn_practice.check_answer(q, a.get("answer")),
            "course_id": lesson.course_id if lesson is not None else None,
        })
```

import_score 改为：

```python
    return learn_profile.init_from_import(user, sorted(kps), data.score, db,
                                          course_id=data.course_id)
```

practice 与 wrongbook 改为：

```python
@router.get("/practice")
def practice(kp: str = Query(...), course_id: int | None = None,
             prev_stem: str | None = None,
             user: User = Depends(_student), db: Session = Depends(get_db)):
    if not kp.strip():
        raise BizError(400, "知识点不能为空")
    return learn_practice.next_question(user, kp.strip(), db,
                                        course_id=course_id, prev_stem=prev_stem)
```

```python
@router.get("/wrongbook")
def wrongbook(course_id: int | None = None, user: User = Depends(_student),
              db: Session = Depends(get_db)):
    return [{"id": w.id, "stem": w.stem, "options": w.options, "user_answer": w.user_answer,
             "correct_answer": w.correct_answer, "knowledge_point": w.knowledge_point,
             "difficulty": w.difficulty, "analysis": w.analysis, "error_reason": w.error_reason,
             "variants": w.variants, "status": w.status, "created_at": w.created_at.isoformat()}
            for w in learn_wrongbook.list_wrongbook(user, db, course_id=course_id)]
```

`backend/scripts/seed_demo_data.py` —— 加迁移函数（纯 SQL，不依赖 Course 模型，旧库 courses 表字段不全也能跑）：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
def migrate_learn_schema(db) -> None:
    """Plan G 旧库迁移（幂等）：knowledge_points 加 course_id 列 → 回填「人工智能导论」→
    移除旧 name 唯一索引、重建 (course_id, name) 唯一索引。新库（create_all 建表）自动跳过。"""
    from sqlalchemy import inspect, text
    engine = db.get_bind()
    cols = {c["name"] for c in inspect(engine).get_columns("knowledge_points")}
    if "course_id" not in cols:
        db.execute(text("ALTER TABLE knowledge_points "
                        "ADD COLUMN course_id INTEGER REFERENCES courses(id)"))
        db.commit()
    db.execute(text("UPDATE knowledge_points SET course_id = "
                    "(SELECT id FROM courses WHERE name = '人工智能导论') "
                    "WHERE course_id IS NULL"))
    db.commit()
    idx = {r[1]: bool(r[2]) for r in db.execute(text("PRAGMA index_list(knowledge_points)"))}
    if idx.get("ix_knowledge_points_name"):   # 旧库的 name 全局唯一索引
        db.execute(text("DROP INDEX ix_knowledge_points_name"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_kp_course_name "
                    "ON knowledge_points (course_id, name)"))
    db.commit()
```

`__main__` 中在 `Base.metadata.create_all(engine)` 之后、`seed_users(db)` 之前加：

```python
        migrate_learn_schema(db)   # Plan G 旧库升级（幂等，新库自动跳过）
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_learn_migration.py tests/test_learn_practice.py tests/test_learn_profile.py tests/test_learn_graph.py tests/test_learn_api.py -v > out.txt 2>&1`
Expected: 新用例全 PASS；既有用例不破（既有测试不传 course_id = 全局兼容路径）。
再跑全量：`cd backend && python -m pytest -q > out_full.txt 2>&1` → 数 PASSED 应 ≥ 295 + 新增 8 条；FAILED = 0。

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/learn.py backend/app/services/learn_profile.py backend/app/services/learn_graph.py backend/app/services/learn_practice.py backend/app/services/learn_wrongbook.py backend/app/api/learn.py backend/scripts/seed_demo_data.py backend/tests/test_learn_migration.py backend/tests/test_learn_practice.py backend/tests/test_learn_profile.py backend/tests/test_learn_graph.py backend/tests/test_learn_api.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn): 知识点课程隔离+旧库迁移+学习接口方向贯穿（Plan G Task 1）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

（后续任务提交命令同此身份与 footer，不再重复。）

---

### Task 2: 数据结构与算法方向（数据模块 + seed 集成重构）

**Files:**
- Create: `backend/scripts/seed_learn_bank.py`
- Modify: `backend/scripts/seed_demo_data.py`（LEARN_* 移除、seed_learn_demo 重构、seed_kb_demo 按标题幂等）
- Test: `backend/tests/test_seed_learn_bank.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 `KnowledgePoint.course_id`；`Course`/`Lesson`/`User` 模型；`kb_service.add_document`。
- Produces（Task 3/4 依赖）：
  - `seed_learn_bank._ex(stem, options, answer, kp, diff, analysis) -> dict`
  - `seed_learn_bank._seed_direction(db, course, kps, prereqs, exercises, lesson_title) -> dict`
  - `seed_learn_bank.seed_learn_directions(db) -> dict`
  - `seed_learn_bank.seed_kb_direction_docs(db, upload_dir="./uploads") -> list[str]`
  - 数据常量：`AI_KPS`、`AI_PREREQS`、`AI_EXERCISES`、`DS_KPS`、`DS_PREREQS`、`DS_EXERCISES`、`DS_KB_DOC`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_seed_learn_bank.py` 新建（此时模块不存在，全部 FAIL）：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
"""Plan G 题库数据测试：每方向 72 题、题档分布、幂等落库、答案与选项结构、知识文档覆盖。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.learn import KnowledgePoint, KpPrereq
from app.models.prep import Course, Lesson
from app.models.user import Role, User
from scripts.seed_learn_bank import (
    AI_EXERCISES, AI_KPS, AI_PREREQS, DS_EXERCISES, DS_KB_DOC, DS_KPS, DS_PREREQS,
    _seed_direction,
)
# 注意：ML_* 常量在 Task 3 才定义，本任务的 import 行不含 ML_*（Task 3 再扩展该行）。


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seedbank.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def course(db):
    teacher = User(username="t", hashed_password="x", role=Role.teacher)
    db.add(teacher)
    db.flush()
    c = Course(name="数据结构与算法", subject="数据结构与算法", owner_id=teacher.id)
    db.add(c)
    db.commit()
    return c


def _distribution(exercises):
    dist: dict[tuple, int] = {}
    for q in exercises:
        dist[(q["知识点"], q["难度"])] = dist.get((q["知识点"], q["难度"]), 0) + 1
    return dist


def test_ds_direction_72_questions_distribution():
    """DS 方向：12 知识点 × 易2/中2/难2 = 72 题。"""
    assert len(DS_EXERCISES) == 72
    assert {k for k, _ in DS_KPS} == {q["知识点"] for q in DS_EXERCISES}
    dist = _distribution(DS_EXERCISES)
    assert all(count == 2 for count in dist.values())
    assert len(dist) == 36  # 12 知识点 × 3 难度


def test_ds_questions_wellformed():
    """每题：4 个带字母前缀的选项、答案在 A~D、题干方向内唯一、解析非空。"""
    stems = [q["题干"] for q in DS_EXERCISES]
    assert len(stems) == len(set(stems))
    for q in DS_EXERCISES:
        assert len(q["选项"]) == 4
        assert all(o[:2] in {f"{c}." for c in "ABCD"} for o in q["选项"])
        assert q["答案"] in "ABCD"
        assert q["解析"].strip() and q["难度"] in ("易", "中", "难")


def test_seed_direction_idempotent(db, course):
    info = _seed_direction(db, course, DS_KPS, DS_PREREQS, DS_EXERCISES,
                           "数据结构与算法演示习题")
    assert info["exercises"] == 72
    assert db.query(KnowledgePoint).filter(
        KnowledgePoint.course_id == course.id).count() == 12
    assert db.query(KpPrereq).count() == 12
    lesson = db.query(Lesson).filter(Lesson.course_id == course.id).first()
    assert lesson is not None and len(lesson.content_json["习题"]) == 72
    _seed_direction(db, course, DS_KPS, DS_PREREQS, DS_EXERCISES,
                    "数据结构与算法演示习题")
    assert db.query(KnowledgePoint).count() == 12   # 不重复建知识点
    assert db.query(KpPrereq).count() == 12         # 不重复建边
    assert db.query(Lesson).count() == 1            # 不重复建 lesson


def test_ds_kb_doc_covers_all_kps():
    for name, _ in DS_KPS:
        assert name in DS_KB_DOC
```

（跨课程同名知识点共存用例依赖 ML 方向数据，见 Task 3 追加；本任务 4 条用例。）

（Task 3/4 追加的 `test_ml_*`、`test_ai_*` 见对应任务；本文件此处只放 DS 用例。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py -v`
Expected: ImportError（模块不存在）→ 记为 RED 证据。

- [ ] **Step 3: 创建数据模块（DS 部分 + AI 迁移）**

`backend/scripts/seed_learn_bank.py` 新建，完整内容如下（本任务写入骨架、AI 数据、DS 数据与函数；ML 常量在 Task 3 追加）：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
"""Plan G 学习方向题库数据模块：3 个学习方向的图谱、216 道手工种子题与演示知识文档。

被 scripts.seed_demo_data（cd backend && python -m scripts.seed_demo_data）与
tests/test_seed_learn_bank.py 共同导入（scripts/ 为命名空间包，backend 为运行根目录）。
"""
import io

from sqlalchemy.orm import Session

from app.models.learn import KnowledgePoint, KpPrereq
from app.models.prep import Lesson


def _ex(stem, options, answer, kp, diff, analysis):
    """习题工厂：题干/选项/答案/解析/知识点/难度（与工单17 试题 schema 一致）。"""
    return {"题干": stem, "选项": options, "答案": answer, "解析": analysis, "知识点": kp, "难度": diff}


def _seed_direction(db: Session, course, kps, prereqs, exercises, lesson_title) -> dict:
    """按课程幂等落库：知识点（(course_id, name) 判存在）→ 前置关系 → 习题集 lesson（upsert）。

    lesson 已存在但题数不同（如 AI 方向 18→72）时整体更新 content_json。
    """
    existing = {(k.name, k.course_id) for k in db.query(KnowledgePoint).all()}
    kp_ids = {}
    for name, desc in kps:
        if (name, course.id) not in existing:
            kp = KnowledgePoint(name=name, description=desc, course_id=course.id)
            db.add(kp)
            db.flush()
            existing.add((name, course.id))
            kp_ids[name] = kp.id
        else:
            kp_ids[name] = (db.query(KnowledgePoint)
                            .filter(KnowledgePoint.name == name,
                                    KnowledgePoint.course_id == course.id)
                            .first().id)
    edge_keys = {(e.kp_id, e.prereq_kp_id) for e in db.query(KpPrereq).all()}
    for kp_name, pre_name in prereqs:
        key = (kp_ids[kp_name], kp_ids[pre_name])
        if key not in edge_keys:
            db.add(KpPrereq(kp_id=key[0], prereq_kp_id=key[1]))
            edge_keys.add(key)
    lesson = (db.query(Lesson).filter(Lesson.course_id == course.id,
                                      Lesson.title == lesson_title).first())
    updated = False
    if lesson is None:
        lesson = Lesson(course_id=course.id, title=lesson_title, lesson_type="exercises",
                        content_json={"习题": exercises}, version=1,
                        created_by=course.owner_id)
        db.add(lesson)
        updated = True
    elif len((lesson.content_json or {}).get("习题", [])) != len(exercises):
        lesson.content_json = {"习题": exercises}
        updated = True
    db.commit()
    return {"kps": len(kps), "prereqs": len(prereqs), "exercises": len(exercises),
            "lesson_updated": updated}


# ---------------- 人工智能导论方向（既有 18 题，Task 4 补齐至 72） ----------------

AI_KPS = [
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

AI_PREREQS = [
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

AI_EXERCISES = [
    _ex("Python 中定义函数使用的关键字是？",
        ["A.def", "B.func", "C.function", "D.define"],
        "A", "Python基础", "易",
        "Python 用 def 关键字定义函数；func、function、define 均不是关键字。"),
    _ex("两个矩阵能够相乘的前提是？",
        ["A.左矩阵的列数等于右矩阵的行数", "B.两个矩阵的行数相等",
         "C.两个矩阵的列数相等", "D.两个矩阵都是方阵"],
        "A", "线性代数", "易",
        "矩阵乘法要求左矩阵列数等于右矩阵行数。"),
    _ex("事件发生的概率取值范围是？",
        ["A.[0,1]", "B.(-1,1)", "C.(0,+∞)", "D.(-∞,+∞)"],
        "A", "概率统计", "易",
        "概率取值恒在 [0,1] 区间。"),
    _ex("梯度下降算法中控制每次更新步长的参数是？",
        ["A.学习率", "B.批量大小", "C.迭代次数", "D.正则化系数"],
        "A", "梯度下降", "易",
        "学习率控制参数每次更新的步长。"),
    _ex("梯度下降中参数更新方向是？",
        ["A.损失函数的负梯度方向", "B.损失函数的正梯度方向",
         "C.与梯度垂直的方向", "D.随机方向"],
        "A", "梯度下降", "易",
        "沿损失函数的负梯度方向迭代更新参数，损失逐步减小。"),
    _ex("学习率过大会导致什么？",
        ["A.收敛速度变慢", "B.损失函数震荡甚至发散",
         "C.模型一定欠拟合", "D.梯度一定消失"],
        "B", "梯度下降", "中",
        "学习率过大步长过大，损失会震荡甚至发散；过小则收敛缓慢。"),
    _ex("关于批量梯度下降与小批量梯度下降，说法正确的是？",
        ["A.批量梯度下降每步使用全部样本，计算开销大", "B.小批量梯度下降每步使用全部样本",
         "C.批量梯度下降每步只使用一个样本", "D.两者每步使用的样本数量相同"],
        "A", "梯度下降", "难",
        "批量梯度下降每步使用全部样本、计算开销大；小批量是折中方案，不保证一定更快收敛。"),
    _ex("以下哪个场景最适合线性回归？",
        ["A.预测房价", "B.图像分类", "C.文本情感分析", "D.语音识别"],
        "A", "线性回归", "易",
        "线性回归拟合连续值，典型场景是房价预测。"),
    _ex("线性回归常用的损失函数是？",
        ["A.均方误差（MSE）", "B.交叉熵损失", "C.Hinge 损失", "D.对数似然损失"],
        "A", "线性回归", "中",
        "线性回归用均方误差（MSE）衡量预测与真实值的差距。"),
    _ex("多元线性回归中特征存在高度共线性，通常会导致？",
        ["A.回归系数估计不稳定", "B.模型无法训练",
         "C.预测结果恒为常数", "D.特征自动被剔除"],
        "A", "线性回归", "难",
        "共线性使系数估计不稳定（方差大），不影响模型可训练性。"),
    _ex("逻辑回归主要用于解决什么问题？",
        ["A.二分类问题", "B.连续值回归预测", "C.聚类问题", "D.数据降维"],
        "A", "逻辑回归", "易",
        "逻辑回归是对数几率模型，解决二分类问题。"),
    _ex("逻辑回归把线性输出映射到 0~1 区间的函数是？",
        ["A.Sigmoid 函数", "B.ReLU 函数", "C.Tanh 函数", "D.Softplus 函数"],
        "A", "逻辑回归", "中",
        "Sigmoid 函数把任意实数映射到 (0,1)，输出即概率。"),
    _ex("决策树中用于选择划分特征的主要指标是？",
        ["A.信息增益（或基尼指数）", "B.梯度大小", "C.样本数量", "D.特征维度"],
        "A", "决策树", "易",
        "决策树按信息增益（或基尼指数）选择划分特征。"),
    _ex("以下哪个不是常用的激活函数？",
        ["A.ReLU", "B.Sigmoid", "C.恒等函数", "D.Tanh"],
        "C", "神经网络", "中",
        "ReLU/Sigmoid/Tanh 都是常用激活函数；恒等函数无非线性，不常用作隐藏层激活。"),
    _ex("反向传播算法利用什么法则逐层计算梯度？",
        ["A.链式法则", "B.贝叶斯公式", "C.泰勒公式", "D.牛顿-莱布尼茨公式"],
        "A", "反向传播", "中",
        "反向传播利用链式法则逐层计算梯度，与梯度下降配合更新参数。"),
    _ex("深度学习中的“深度”主要指什么？",
        ["A.网络层数多", "B.训练数据量大", "C.模型参数精度高", "D.训练时间久"],
        "A", "深度学习基础", "易",
        "深度指网络层数多（多层非线性变换）。"),
    _ex("卷积神经网络中池化层的主要作用是？",
        ["A.降低特征维度并增强平移不变性", "B.增加特征图数量",
         "C.引入非线性激活", "D.计算损失函数"],
        "A", "卷积神经网络", "中",
        "池化层降低特征维度、保留主要特征并提升平移不变性。"),
    _ex("以下哪个任务属于自然语言处理？",
        ["A.情感分析", "B.图像分割", "C.语音降噪", "D.路径规划"],
        "A", "自然语言处理", "中",
        "情感分析是典型 NLP 任务；图像分割属 CV、语音降噪属语音、路径规划属搜索。"),
]

# ---------------- 数据结构与算法方向 ----------------

DS_KPS = [
    ("数据结构基础", "数据结构基本概念与算法评价"),
    ("线性表", "顺序表与链表的基本操作"),
    ("栈与队列", "受限线性表：LIFO 与 FIFO"),
    ("串与数组", "字符串匹配与数组存储"),
    ("树与二叉树", "树的定义、性质与遍历"),
    ("图", "图的存储与遍历"),
    ("查找", "顺序/折半/分块/哈希查找"),
    ("排序", "常见排序算法与复杂度"),
    ("哈希表", "哈希函数与冲突处理"),
    ("算法复杂度分析", "时间复杂度与空间复杂度"),
    ("递归与分治", "递归思想与分治算法"),
    ("贪心与动态规划", "局部最优与最优子结构"),
]

DS_PREREQS = [
    ("线性表", "数据结构基础"),
    ("栈与队列", "线性表"),
    ("串与数组", "线性表"),
    ("树与二叉树", "数据结构基础"),
    ("图", "树与二叉树"),
    ("查找", "线性表"),
    ("哈希表", "查找"),
    ("排序", "线性表"),
    ("排序", "算法复杂度分析"),
    ("算法复杂度分析", "数据结构基础"),
    ("递归与分治", "树与二叉树"),
    ("贪心与动态规划", "递归与分治"),
]

DS_EXERCISES = [
    _ex("数据的逻辑结构不包括？",
        ["A.线性结构", "B.树形结构", "C.图状结构", "D.存储结构"],
        "D", "数据结构基础", "易",
        "逻辑结构包括线性、树形、图状与集合结构；存储结构（顺序/链式）是物理层面的。"),
    _ex("算法的时间复杂度主要衡量？",
        ["A.执行时间随问题规模增长的趋势", "B.程序运行的具体秒数",
         "C.代码行数", "D.变量个数"],
        "A", "数据结构基础", "易",
        "大 O 记号描述增长趋势，与机器无关。"),
    _ex("下列哪个属于数据的物理（存储）结构？",
        ["A.顺序存储", "B.线性表", "C.树", "D.图"],
        "A", "数据结构基础", "中",
        "顺序存储/链式存储是物理结构；线性表、树、图是逻辑结构。"),
    _ex("与所使用的计算机无关的是数据的什么结构？",
        ["A.逻辑结构", "B.存储结构", "C.物理结构", "D.运算实现"],
        "A", "数据结构基础", "中",
        "逻辑结构只描述数据元素间的关系，独立于机器；存储结构依赖机器。"),
    _ex("下列时间复杂度从小到大排列正确的是？",
        ["A.O(1)<O(logn)<O(n)<O(nlogn)<O(n²)",
         "B.O(1)<O(n)<O(logn)<O(n²)",
         "C.O(logn)<O(1)<O(n)<O(n²)",
         "D.O(n)<O(1)<O(logn)<O(nlogn)"],
        "A", "数据结构基础", "难",
        "常数<对数<线性<线性对数<平方，是常见复杂度大小顺序。"),
    _ex("下列哪个不是算法的特性？",
        ["A.无限性", "B.有穷性", "C.确定性", "D.可行性"],
        "A", "数据结构基础", "难",
        "算法五大特性为有穷性、确定性、可行性、输入、输出；无限性违背有穷性。"),
    _ex("关于线性表，下列说法正确的是？",
        ["A.是 n 个数据元素的有限序列，可以为空", "B.数据元素必须是数字",
         "C.只能顺序存储", "D.长度必须固定"],
        "A", "线性表", "易",
        "线性表是有限序列，n=0 为空表；元素类型不限，可顺序或链式存储。"),
    _ex("顺序表中存取第 i 个元素的时间复杂度是？",
        ["A.O(1)", "B.O(n)", "C.O(logn)", "D.O(n²)"],
        "A", "线性表", "易",
        "顺序表支持随机存取，按下标计算地址直接访问。"),
    _ex("长度为 n 的顺序表在第 i 个位置（1≤i≤n+1）插入元素，需移动元素的个数是？",
        ["A.n-i+1", "B.n-i", "C.i", "D.n-i-1"],
        "A", "线性表", "中",
        "第 i 个位置起共 n-i+1 个元素需依次后移。"),
    _ex("单链表中删除指针 p 所指结点的后继结点，正确的操作是？",
        ["A.p->next = p->next->next", "B.p = p->next",
         "C.p->next = p", "D.p->next->next = p"],
        "A", "线性表", "中",
        "跳过被删结点，把 p 的指针直接指向后继的后继。"),
    _ex("单链表中，若 p 指向某非尾结点且只有 p 指针（无头指针），删除 p 所指结点通常的做法是？",
        ["A.把后继结点数据复制到 p，再删除后继结点", "B.直接释放 p 的存储",
         "C.从头遍历找到前驱再删除", "D.无法删除"],
        "A", "线性表", "难",
        "无法直接找到前驱，用“复制数据+删除后继”实现等价删除。"),
    _ex("与单链表相比，双向链表多占用存储空间换来的主要好处是？",
        ["A.能快速找到结点的前驱", "B.能存储更多数据",
         "C.提高内存利用率", "D.自动排序"],
        "A", "线性表", "难",
        "双向链表每个结点多一个前驱指针，向前查找 O(1)。"),
    _ex("栈的特点是？",
        ["A.先进后出", "B.先进先出", "C.随机进出", "D.只能进不能出"],
        "A", "栈与队列", "易",
        "栈仅允许在栈顶插入删除，后进先出（LIFO）。"),
    _ex("队列的特点是？",
        ["A.先进先出", "B.先进后出", "C.随机进出", "D.只能出不能进"],
        "A", "栈与队列", "易",
        "队列在队尾插入、队头删除，先进先出（FIFO）。"),
    _ex("入栈序列为 1,2,3，下列哪个不可能是出栈序列？",
        ["A.1,2,3", "B.2,1,3", "C.3,2,1", "D.3,1,2"],
        "D", "栈与队列", "中",
        "3 先出栈时 1、2 已在栈中且 1 在下 2 在上，只能先出 2 再出 1。"),
    _ex("循环队列牺牲一个存储单元时，判断队满的条件是？",
        ["A.(rear+1)%MaxSize==front", "B.rear==front",
         "C.rear==MaxSize", "D.front==0"],
        "A", "栈与队列", "中",
        "尾指针加一取模等于头指针即队满；rear==front 是队空。"),
    _ex("用数组 A[0..n-1] 实现循环队列，front 指向队头、rear 指向队尾下一位置，队列中元素个数是？",
        ["A.(rear-front+n)%n", "B.rear-front",
         "C.(front-rear+n)%n", "D.n-1"],
        "A", "栈与队列", "难",
        "循环队列元素数用取模差计算，处理 rear<front 的回绕。"),
    _ex("后缀表达式 3 4 + 5 * 的值是？",
        ["A.35", "B.23", "C.27", "D.17"],
        "A", "栈与队列", "难",
        "后缀式按栈求值：(3+4)*5=35。"),
    _ex("串是一种特殊的线性表，其数据元素只能是？",
        ["A.字符", "B.数字", "C.单词", "D.结点"],
        "A", "串与数组", "易",
        "串是由零个或多个字符组成的有限序列。"),
    _ex("二维数组在内存中通常如何存储？",
        ["A.按行或按列的顺序连续存储", "B.树形结构存储",
         "C.随机散列存储", "D.只能按行存储"],
        "A", "串与数组", "易",
        "数组元素地址连续，按行优先或列优先顺序存放。"),
    _ex("串的长度是指？",
        ["A.串中字符的个数", "B.串占用的字节数",
         "C.串中空格的个数", "D.串的存储地址"],
        "A", "串与数组", "中",
        "串长为字符个数，空串长度为 0。"),
    _ex("KMP 模式匹配算法中，next[1]（下标从 1 开始）的值是？",
        ["A.0", "B.1", "C.2", "D.-1"],
        "A", "串与数组", "中",
        "KMP 约定第一个字符失配时模式串整体后移，next[1]=0。"),
    _ex("稀疏矩阵常用的压缩存储方法是？",
        ["A.三元组顺序表", "B.二维数组", "C.邻接矩阵", "D.哈希表"],
        "A", "串与数组", "难",
        "只存非零元的（行，列，值）三元组，大幅节省空间。"),
    _ex("KMP 算法相对朴素匹配的主要优势是？",
        ["A.主串指针不回溯", "B.模式串不用预处理",
         "C.一定比朴素匹配快", "D.不需要存储 next 数组"],
        "A", "串与数组", "难",
        "利用 next 数组在失配时只移动模式串，主串指针不回溯，最坏 O(n+m)。"),
    _ex("非空树有几个根结点？",
        ["A.1 个", "B.0 个", "C.至少 2 个", "D.与层数相同"],
        "A", "树与二叉树", "易",
        "非空树有且仅有一个根结点。"),
    _ex("二叉树第 i 层（i≥1）最多有多少个结点？",
        ["A.2^(i-1)", "B.2^i", "C.2i", "D.i²"],
        "A", "树与二叉树", "易",
        "每层结点数最多翻倍，第 i 层最多 2^(i-1)。"),
    _ex("深度为 k 的完全二叉树至少有多少个结点？",
        ["A.2^(k-1)", "B.2^k-1", "C.2^k", "D.k"],
        "A", "树与二叉树", "中",
        "完全二叉树前 k-1 层满，第 k 层至少 1 个结点。"),
    _ex("含 n 个结点的二叉树用二叉链表存储，共有多少个空指针域？",
        ["A.n+1", "B.n", "C.n-1", "D.2n"],
        "A", "树与二叉树", "中",
        "2n 个指针域中 n-1 个非空（对应 n-1 条边），空指针 n+1 个。"),
    _ex("前序序列与后序序列完全相同的二叉树是？",
        ["A.只有根结点的二叉树", "B.完全二叉树", "C.满二叉树", "D.左斜树"],
        "A", "树与二叉树", "难",
        "前序为“根左右”、后序为“左右根”，仅当无左右子树（单根）时相同。"),
    _ex("具有 n 个结点的完全二叉树的深度是？",
        ["A.⌊log₂n⌋+1", "B.log₂n", "C.⌊log₂n⌋", "D.n"],
        "A", "树与二叉树", "难",
        "深度为 k 的完全二叉树结点数在 [2^(k-1), 2^k-1]，故 k=⌊log₂n⌋+1。"),
    _ex("图由哪两部分组成？",
        ["A.顶点和边", "B.结点和指针", "C.数组和链表", "D.根和叶子"],
        "A", "图", "易",
        "图 G=(V,E)，V 是顶点集、E 是边集。"),
    _ex("无向图中顶点的度是指？",
        ["A.与该顶点相连的边的条数", "B.入边数",
         "C.出边数", "D.图中边总数"],
        "A", "图", "易",
        "无向图不区分方向，度为相连边数。"),
    _ex("n 个顶点的无向完全图有多少条边？",
        ["A.n(n-1)/2", "B.n(n-1)", "C.n²/2", "D.n-1"],
        "A", "图", "中",
        "每对顶点一条边，C(n,2)=n(n-1)/2。"),
    _ex("图的广度优先遍历使用的数据结构是？",
        ["A.队列", "B.栈", "C.二叉树", "D.哈希表"],
        "A", "图", "中",
        "BFS 按层展开用队列；DFS 用栈或递归。"),
    _ex("具有 n 个顶点的连通图至少有几条边？",
        ["A.n-1", "B.n", "C.n+1", "D.n(n-1)/2"],
        "A", "图", "难",
        "n 个顶点连通最少构成一棵树，n-1 条边。"),
    _ex("有向图中所有顶点的入度之和与出度之和的关系是？",
        ["A.相等（都等于边数）", "B.入度之和大",
         "C.出度之和大", "D.不确定"],
        "A", "图", "难",
        "每条边贡献一个入度与一个出度，两者都等于边数。"),
    _ex("顺序查找（线性查找）的平均查找长度为？",
        ["A.(n+1)/2", "B.n", "C.logn", "D.n/4"],
        "A", "查找", "易",
        "等概率下比较次数为 1~n 的平均。"),
    _ex("折半查找要求数据表必须是？",
        ["A.有序的顺序表", "B.有序的单链表",
         "C.无序的顺序表", "D.任意表"],
        "A", "查找", "易",
        "折半需按下标随机访问中间元素，故要求顺序存储且有序。"),
    _ex("对 11 个元素的有序表折半查找，查找失败时最多比较几次？",
        ["A.4", "B.3", "C.11", "D.5"],
        "A", "查找", "中",
        "判定树深度 ⌊log₂11⌋+1=4。"),
    _ex("折半查找的平均时间复杂度是？",
        ["A.O(logn)", "B.O(n)", "C.O(nlogn)", "D.O(1)"],
        "A", "查找", "中",
        "每次排除一半，最多 ⌊log₂n⌋+1 次比较。"),
    _ex("在含 100 个元素的有序表中折半查找，最多比较几次能找到目标？",
        ["A.7", "B.6", "C.100", "D.10"],
        "A", "查找", "难",
        "⌊log₂100⌋+1=7。"),
    _ex("分块查找（块内与索引均顺序查找）的平均查找长度约为？",
        ["A.(s+n/s)/2+1", "B.s+n/s", "C.(s+n/s)/2", "D.2s"],
        "A", "查找", "难",
        "块内 ASL=(s+1)/2、索引 ASL=(n/s+1)/2，合计 (s+n/s)/2+1，s≈√n 时最小。"),
    _ex("冒泡排序每一趟结束时，什么元素会到达最终位置？",
        ["A.当前未排序部分的最大（或最小）元素", "B.随机一个元素",
         "C.最小元素总是排最前", "D.所有元素"],
        "A", "排序", "易",
        "相邻比较交换使极值“冒泡”到一端。"),
    _ex("直接插入排序的基本思想是？",
        ["A.把未排序元素插入已排序序列的合适位置", "B.两两交换相邻元素",
         "C.递归划分", "D.构建堆"],
        "A", "排序", "易",
        "维护有序前缀，逐个插入。"),
    _ex("快速排序的平均时间复杂度是？",
        ["A.O(nlogn)", "B.O(n)", "C.O(n²)", "D.O(logn)"],
        "A", "排序", "中",
        "平均每次划分接近对半，递归深度 logn。"),
    _ex("下列排序算法中平均性能最好（同为 O(nlogn) 中常数最小）的通常是？",
        ["A.快速排序", "B.冒泡排序", "C.直接插入排序", "D.简单选择排序"],
        "A", "排序", "中",
        "快排平均 O(nlogn) 且常数小；其余三个为 O(n²)。"),
    _ex("以 5 为基准对序列 5,2,7,1,3 做一趟快速排序（挖坑法，升序），结果可能是？",
        ["A.3,1,2,5,7", "B.1,2,3,5,7", "C.3,2,1,5,7", "D.2,1,3,5,7"],
        "A", "排序", "难",
        "一趟后基准落在最终位置，左边全小于 5：3,1,2,5,7。"),
    _ex("下列排序算法中最坏情况时间复杂度为 O(n²) 的是？",
        ["A.快速排序", "B.堆排序", "C.归并排序", "D.基数排序"],
        "A", "排序", "难",
        "快排最坏（如有序序列取端点基准）O(n²)；堆排与归并最坏 O(nlogn)。"),
    _ex("哈希表查找的平均时间复杂度是？",
        ["A.O(1)", "B.O(n)", "C.O(logn)", "D.O(n²)"],
        "A", "哈希表", "易",
        "理想情况下哈希函数直接定位地址。"),
    _ex("哈希函数的作用是？",
        ["A.把关键字映射到存储地址", "B.给关键字排序",
         "C.加密数据", "D.压缩文件"],
        "A", "哈希表", "易",
        "哈希函数建立关键字与存储地址的映射。"),
    _ex("两个不同关键字映射到同一地址的现象称为？",
        ["A.冲突", "B.溢出", "C.堆积", "D.碰撞检测"],
        "A", "哈希表", "中",
        "冲突即不同关键字哈希值相同；堆积是线性探测的次生聚集。"),
    _ex("下列哪个不是处理哈希冲突的常用方法？",
        ["A.排序法", "B.开放定址法", "C.链地址法", "D.再哈希法"],
        "A", "哈希表", "中",
        "冲突处理有开放定址、链地址、再哈希、公共溢出区；排序法与冲突无关。"),
    _ex("表长为 11 的哈希表，H(key)=key%11，依次插入 23 和 34，下列说法正确的是？",
        ["A.两关键字发生冲突（地址都是 1）", "B.23 地址为 1、34 地址为 0",
         "C.都映射到 0", "D.不发生冲突"],
        "A", "哈希表", "难",
        "23%11=1，34%11=1，映射同一地址发生冲突。"),
    _ex("装填因子 α 对哈希表查找效率的影响是？",
        ["A.α 越大平均查找长度越大", "B.α 越大查找越快",
         "C.α 与查找效率无关", "D.α 必须大于 1"],
        "A", "哈希表", "难",
        "α=记录数/表长，越满冲突越多，ASL 越大。"),
    _ex("for(i=1;i<=n;i++) 单层循环的时间复杂度是？",
        ["A.O(n)", "B.O(n²)", "C.O(1)", "D.O(logn)"],
        "A", "算法复杂度分析", "易",
        "循环体执行 n 次。"),
    _ex("常数阶时间复杂度记为？",
        ["A.O(1)", "B.O(n)", "C.O(0)", "D.O(cn)"],
        "A", "算法复杂度分析", "易",
        "执行次数与 n 无关的算法记为 O(1)。"),
    _ex("for(i=1;i<=n;i++) for(j=1;j<=n;j++) 双重循环的时间复杂度是？",
        ["A.O(n²)", "B.O(n)", "C.O(n³)", "D.O(logn)"],
        "A", "算法复杂度分析", "中",
        "外层 n 次、内层 n 次，共 n² 次。"),
    _ex("for(i=1;i<=n;i*=2) 循环的时间复杂度是？",
        ["A.O(logn)", "B.O(n)", "C.O(nlogn)", "D.O(1)"],
        "A", "算法复杂度分析", "中",
        "i 每次乘 2，循环次数约 log₂n。"),
    _ex("递归式 T(n)=2T(n/2)+n 的时间复杂度是？",
        ["A.O(nlogn)", "B.O(n)", "C.O(n²)", "D.O(logn)"],
        "A", "算法复杂度分析", "难",
        "主定理情形二，每层总开销 n、共 logn 层，如归并排序。"),
    _ex("代码 for(i=1;i<=n;i++) for(j=1;j<=i;j++) x++; 的时间复杂度是？",
        ["A.O(n²)", "B.O(n)", "C.O(n³)", "D.O(nlogn)"],
        "A", "算法复杂度分析", "难",
        "执行次数 1+2+...+n=n(n+1)/2，为 O(n²)。"),
    _ex("递归函数必须包含？",
        ["A.递归出口（终止条件）", "B.循环语句", "C.数组参数", "D.指针参数"],
        "A", "递归与分治", "易",
        "没有出口会无限递归导致栈溢出。"),
    _ex("分治法的基本步骤是？",
        ["A.分解、求解、合并", "B.查找、插入、删除", "C.入栈、出栈", "D.加密、解密"],
        "A", "递归与分治", "易",
        "把问题分解为子问题、递归求解再合并。"),
    _ex("用递归计算 n!，递归出口是？",
        ["A.n 为 0 或 1 时返回 1", "B.n 为 0 时返回 0",
         "C.n 大于 1 时返回 1", "D.不存在出口"],
        "A", "递归与分治", "中",
        "0!=1!=1 是终止条件，n!=n×(n-1)!。"),
    _ex("归并排序体现的算法思想是？",
        ["A.分治法", "B.贪心法", "C.回溯法", "D.动态规划"],
        "A", "递归与分治", "中",
        "先二分分解、排序子序列再合并，典型分治。"),
    _ex("朴素递归计算斐波那契数列 fib(n)=fib(n-1)+fib(n-2) 的时间复杂度是？",
        ["A.O(2^n)", "B.O(n²)", "C.O(nlogn)", "D.O(logn)"],
        "A", "递归与分治", "难",
        "递归树近似满二叉树，结点数约 2^n，大量重复计算。"),
    _ex("汉诺塔 n 层盘子最少需要移动多少次？",
        ["A.2^n-1", "B.2^n", "C.n²", "D.n!"],
        "A", "递归与分治", "难",
        "T(n)=2T(n-1)+1，解为 2^n-1。"),
    _ex("贪心算法的核心思想是？",
        ["A.每一步都选择当前看来最优的方案", "B.穷举所有方案",
         "C.随机选择", "D.从结果往前推"],
        "A", "贪心与动态规划", "易",
        "贪心做局部最优选择，不回溯。"),
    _ex("动态规划适用于具有什么性质的问题？",
        ["A.最优子结构和重叠子问题", "B.只有一种解",
         "C.数据量极小", "D.只能求最大值"],
        "A", "贪心与动态规划", "易",
        "最优解含子问题最优解（最优子结构），且子问题被反复求解（重叠）。"),
    _ex("用贪心法找零钱能得到最优解的前提是？",
        ["A.面额系统满足贪心选择性质（如人民币 1,5,10,20,50,100）", "B.任何面额系统都可以",
         "C.只有一种面额", "D.面额越大越好"],
        "A", "贪心与动态规划", "中",
        "满足贪心选择性质的面额（如人民币）贪心最优；否则可能不是最优。"),
    _ex("0-1 背包问题与完全背包问题的区别是？",
        ["A.0-1 背包每件物品只能选一次，完全背包可选无限次", "B.完全背包不能选物品",
         "C.0-1 背包容量无限", "D.没有区别"],
        "A", "贪心与动态规划", "中",
        "0-1 背包每件取或不取；完全背包每件可取任意件。"),
    _ex("0-1 背包问题能用贪心法保证得到最优解吗？",
        ["A.不能，需用动态规划", "B.能，按单位价值排序即可",
         "C.能，按重量排序即可", "D.能，随机选取即可"],
        "A", "贪心与动态规划", "难",
        "0-1 背包不具备贪心选择性质，需动态规划。"),
    _ex("动态规划求解最长公共子序列时，dp[i][j] 通常表示？",
        ["A.序列 X 前 i 个与序列 Y 前 j 个字符的最长公共子序列长度", "B.X 的第 i 个字符",
         "C.Y 的长度", "D.两个序列的总长度"],
        "A", "贪心与动态规划", "难",
        "dp 表按前缀长度递推，dp[m][n] 即所求。"),
]

DS_KB_DOC = """# 数据结构与算法知识库

## 一、数据结构基础
数据结构研究数据元素之间的逻辑关系与存储方式。逻辑结构分为线性结构、树形结构、图状结构与集合结构；物理结构（存储结构）主要有顺序存储与链式存储。算法具有有穷性、确定性、可行性、输入与输出五个特性，评价算法主要看时间复杂度与空间复杂度，常用大 O 记号描述增长趋势。

## 二、线性表
线性表是 n 个数据元素的有限序列，n=0 时为空表。顺序表用连续存储单元存储，支持 O(1) 随机存取，插入删除需移动元素；链表用指针连接结点，插入删除只需修改指针，但访问第 i 个元素需从头遍历。单链表每个结点含数据域与指针域；双向链表每个结点多一个指向前驱的指针。

## 三、栈与队列
栈是仅允许在一端插入删除的线性表，特点是先进后出（LIFO）；入栈序列固定时出栈序列有多种可能，但栈顶元素出栈前其下元素顺序保持逆序。队列是允许在一端插入、另一端删除的线性表，特点是先进先出（FIFO）。循环队列用取模运算把数组首尾相连，牺牲一个单元区分队空与队满：(rear+1)%MaxSize==front 为队满。栈常用于表达式求值（中缀转后缀）、递归模拟；队列常用于广度优先遍历。

## 四、串与数组
串是由零个或多个字符组成的有限序列，是特殊的线性表，数据元素只能是字符。串的长度是字符个数；空串是长度为 0 的串。二维数组按行优先或列优先顺序存储，元素地址可按下标公式计算。稀疏矩阵非零元素很少，常用三元组顺序表压缩存储以节省空间。KMP 算法利用 next 数组避免主串指针回溯，实现高效的模式匹配。

## 五、树与二叉树
树是 n（n≥0）个结点的有限集合，非空树有且仅有一个根结点。二叉树每个结点最多两棵子树，第 i 层最多 2^(i-1) 个结点，深度为 k 的二叉树最多 2^k-1 个结点。具有 n 个结点的完全二叉树深度为 ⌊log₂n⌋+1。二叉链表存储 n 个结点共有 2n 个指针域，其中 n+1 个为空。二叉树遍历分前序（根左右）、中序（左根右）、后序（左右根）与层序。

## 六、图
图由顶点集与边集组成。无向图中顶点的度是与该顶点相连的边数，全部顶点度数之和等于边数的 2 倍；有向图分入度与出度，入度之和等于出度之和等于边数。n 个顶点的无向完全图有 n(n-1)/2 条边。图的遍历有深度优先（借助栈或递归）与广度优先（借助队列）。连通图任意两顶点可达，n 个顶点的连通图至少 n-1 条边。

## 七、查找
顺序查找按顺序逐个比较，平均查找长度 (n+1)/2。折半查找仅适用于有序的顺序表，每次与中间元素比较排除一半，时间复杂度 O(logn)。分块查找先查索引确定所在块，再在块内顺序查找。哈希查找通过哈希函数把关键字映射到存储地址，平均查找长度与装填因子有关，α 越大冲突越多。

## 八、排序
冒泡排序每趟把当前未排序部分的最大（小）元素移到最终位置，时间复杂度 O(n²)。直接插入排序把未排序元素插入已排序序列的合适位置，基本有序时接近 O(n)。快速排序选取基准元素一趟划分后基准落在最终位置，平均 O(nlogn)、最坏 O(n²)（如已有序序列取端点基准）。堆排序与归并排序最坏也为 O(nlogn)。

## 九、哈希表
哈希函数把关键字映射到存储地址，理想情况下查找时间复杂度 O(1)。不同关键字映射到同一地址称为冲突；处理冲突常用开放定址法（线性探测等）与链地址法。线性探测可能造成堆积（非同义词争夺同一后继地址），降低查找效率。装填因子 α = 表中记录数/表长，α 越大平均查找长度越大。

## 十、算法复杂度分析
时间复杂度描述算法执行时间随问题规模 n 的增长趋势：单层循环 O(n)，两层嵌套循环 O(n²)，每次规模减半的循环 O(logn)，分治合并类如 T(n)=2T(n/2)+n 为 O(nlogn)。空间复杂度描述额外存储空间随规模的增长。分析时只保留最高阶项并忽略系数。

## 十一、递归与分治
递归函数直接或间接调用自身，必须包含递归出口（终止条件），否则无限递归导致栈溢出。递归树可分析时间复杂度，如朴素斐波那契递归 fib(n)=fib(n-1)+fib(n-2) 为 O(2^n)。分治法将问题分解为子问题、递归求解再合并结果，归并排序、快速排序是典型分治算法。汉诺塔 n 层盘子最少移动 2^n-1 次。

## 十二、贪心与动态规划
贪心算法每一步都选择当前看来最优的方案，适合具有贪心选择性质的问题（如人民币面额找零），但不保证全局最优。动态规划适用于具有最优子结构与重叠子问题的优化问题，自底向上填表求解，如 0-1 背包、最长公共子序列；0-1 背包每件物品只能选一次，贪心法不能保证最优解。
"""


# ---------------- 方向落库与知识库文档 ----------------

def seed_learn_directions(db: Session) -> dict:
    """3 个方向的图谱与 216 题（幂等）。AI 方向沿用既有课程与 lesson 标题。"""
    from app.models.prep import Course
    from app.models.user import User
    teacher = db.query(User).filter(User.username == "teacher").first()
    out = {}
    for course_name, kps, prereqs, exercises, title in [
        ("人工智能导论", AI_KPS, AI_PREREQS, AI_EXERCISES, "个性化学习演示习题"),
        ("数据结构与算法", DS_KPS, DS_PREREQS, DS_EXERCISES, "数据结构与算法演示习题"),
        ("机器学习", ML_KPS, ML_PREREQS, ML_EXERCISES, "机器学习演示习题"),
    ]:
        course = db.query(Course).filter(Course.name == course_name).first()
        if course is None:
            course = Course(
                name=course_name,
                subject="人工智能" if course_name == "人工智能导论" else course_name,
                description="高职课程（演示数据，Plan G 学习方向）",
                owner_id=teacher.id if teacher else 1)
            db.add(course)
            db.flush()
        out[course_name] = _seed_direction(db, course, kps, prereqs, exercises, title)
    return out


def seed_kb_direction_docs(db: Session, upload_dir: str = "./uploads") -> list[str]:
    """两个新方向的演示知识文档入公共库（幂等：按标题判存在）。bge-m3 不可用则跳过并提示。"""
    from app.models.kb import KbDocument
    from app.models.user import User
    from app.services import kb_service
    from app.services.embeddings import EmbedderError
    from fastapi import UploadFile
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        return []
    done = []
    for title, text in [("数据结构与算法知识库.md", DS_KB_DOC),
                        ("机器学习知识库.md", ML_KB_DOC)]:
        if db.query(KbDocument).filter(KbDocument.title == title).first() is not None:
            continue
        file = UploadFile(filename=title, file=io.BytesIO(text.encode("utf-8")))
        try:
            doc = kb_service.add_document(file, "public", admin, upload_dir, db)
            done.append(f"{doc.title}（{doc.chunk_count} 块）")
        except EmbedderError as exc:
            print(f"bge-m3 不可用，跳过知识库演示文档 {title}：{exc}")
    return done
```

- [ ] **Step 4: 重构 seed_demo_data.py**

（1）删除原 `LEARN_KPS`、`LEARN_PREREQS`、`_ex`、`LEARN_EXERCISES` 四个定义（约第 189~306 行区块），以及原 `seed_learn_demo` 函数，替换为：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
def seed_learn_demo(db) -> None:
    """个性化学习演示数据（Plan G）：3 个学习方向图谱 + 216 道手工种子题。幂等。"""
    from scripts.seed_learn_bank import seed_learn_directions
    result = seed_learn_directions(db)
    for name, info in result.items():
        print(f"学习方向「{name}」：{info['kps']} 知识点 + "
              f"{info['prereqs']} 前置关系 + {info['exercises']} 题")
```

（注意：文件头部 `from app.models.learn import KnowledgePoint, KpPrereq` 若重构后不再被引用则一并删除；`Lesson` import 仍被 seed_prep_demo/seed_kb_demo 使用，保留。）

（2）`seed_kb_demo` 幂等判断从"任何 ready 公共文档"改为**按标题**，并在 PDF 之后追加新方向 .md 文档：

```python
def seed_kb_demo(db, upload_dir="./uploads"):
    """公共库演示文档：AI 知识库 PDF + 两个新方向 .md 文档。幂等：按标题判存在。"""
    from app.models.kb import KbDocument
    from scripts.seed_learn_bank import seed_kb_direction_docs
    exists = db.query(KbDocument).filter(KbDocument.title == "人工智能导论知识库.pdf").first()
    if exists is None:
        from app.models.user import User
        admin = db.query(User).filter(User.username == "admin").first()
        if admin is None:
            print("admin 不存在，跳过公共库演示数据")
        else:
            pdf_path = Path(tempfile.gettempdir()) / "kb_demo_人工智能导论知识库.pdf"
            _build_kb_demo_pdf(pdf_path)
            from app.services import kb_service
            from app.services.embeddings import EmbedderError
            from fastapi import UploadFile
            with open(pdf_path, "rb") as f:
                file = UploadFile(filename="人工智能导论知识库.pdf", file=f)
                try:
                    doc = kb_service.add_document(file, "public", admin, upload_dir, db)
                    print(f"公共库演示文档已入库：{doc.title}（{doc.chunk_count} 块）")
                except EmbedderError as exc:
                    print(f"bge-m3 不可用，跳过公共库演示数据：{exc}")
    else:
        print("公共库演示文档「人工智能导论知识库.pdf」已存在，跳过")
    for line in seed_kb_direction_docs(db, upload_dir):
        print(f"公共库演示文档已入库：{line}")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py -v`
Expected: 全 PASS。
再跑全量：`cd backend && python -m pytest -q > out_full.txt 2>&1` → 既有 295 不破（seed_demo_data 重构后无测试引用 LEARN_*，已 grep 确认）。

- [ ] **Step 6: 提交**

```bash
git add backend/scripts/seed_learn_bank.py backend/scripts/seed_demo_data.py backend/tests/test_seed_learn_bank.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(seed): 学习方向题库数据模块+数据结构与算法方向 72 题+seed 重构（Plan G Task 2）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 机器学习方向（12 知识点 + 前置 + 72 题 + 知识文档）

**Files:**
- Modify: `backend/scripts/seed_learn_bank.py`（追加 ML_KPS/ML_PREREQS/ML_EXERCISES/ML_KB_DOC）
- Test: `backend/tests/test_seed_learn_bank.py`（追加 ML 用例）

**Interfaces:**
- Consumes: Task 2 的 `seed_learn_bank` 模块与 `_seed_direction`/`seed_learn_directions`/`seed_kb_direction_docs`（ML 常量已在其列表中被引用——本任务把它们定义出来）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_seed_learn_bank.py` 末尾追加：

```python
def test_ml_direction_72_questions_distribution():
    """ML 方向：12 知识点 × 易2/中2/难2 = 72 题。"""
    assert len(ML_EXERCISES) == 72
    assert {k for k, _ in ML_KPS} == {q["知识点"] for q in ML_EXERCISES}
    dist = _distribution(ML_EXERCISES)
    assert all(count == 2 for count in dist.values())
    assert len(dist) == 36


def test_ml_questions_wellformed():
    stems = [q["题干"] for q in ML_EXERCISES]
    assert len(stems) == len(set(stems))
    for q in ML_EXERCISES:
        assert len(q["选项"]) == 4
        assert all(o[:2] in {f"{c}." for c in "ABCD"} for o in q["选项"])
        assert q["答案"] in "ABCD"
        assert q["解析"].strip() and q["难度"] in ("易", "中", "难")


def test_ml_kb_doc_covers_all_kps():
    for name, _ in ML_KPS:
        assert name in ML_KB_DOC
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py::test_ml_direction_72_questions_distribution tests/test_seed_learn_bank.py::test_ml_questions_wellformed tests/test_seed_learn_bank.py::test_ml_kb_doc_covers_all_kps -v`
Expected: ImportError（ML_KPS 未定义）→ RED 证据。

- [ ] **Step 3: 在 `DS_KB_DOC` 定义之后、`seed_learn_directions` 之前插入 ML 数据（逐字）**

```python
# ---------------- 机器学习方向 ----------------

ML_KPS = [
    ("机器学习基础", "机器学习基本概念与数据集划分"),
    ("监督学习", "带标签数据的分类与回归"),
    ("无监督学习", "无标签数据的聚类与降维"),
    ("线性回归", "拟合连续值的线性模型"),
    ("逻辑回归", "Sigmoid 映射的二分类模型"),
    ("决策树", "按特征划分的树形分类模型"),
    ("集成学习", "Bagging/Boosting 组合模型"),
    ("聚类分析", "K-Means 等无监督分群"),
    ("降维", "PCA 等特征压缩方法"),
    ("模型评估", "准确率/精确率/召回率/F1"),
    ("过拟合与正则化", "泛化能力与 L1/L2/早停"),
    ("特征工程", "特征变换、选择与构造"),
]

ML_PREREQS = [
    ("监督学习", "机器学习基础"),
    ("无监督学习", "机器学习基础"),
    ("线性回归", "监督学习"),
    ("逻辑回归", "线性回归"),
    ("决策树", "监督学习"),
    ("集成学习", "决策树"),
    ("聚类分析", "无监督学习"),
    ("降维", "机器学习基础"),
    ("模型评估", "机器学习基础"),
    ("过拟合与正则化", "线性回归"),
    ("特征工程", "机器学习基础"),
]

ML_EXERCISES = [
    _ex("机器学习的核心是？",
        ["A.从数据中自动学习规律", "B.人工编写所有规则",
         "C.只做算术运算", "D.仅存储数据"],
        "A", "机器学习基础", "易",
        "机器学习让计算机从数据中学习，无需人工编写全部规则。"),
    _ex("机器学习中训练集的作用是？",
        ["A.用于学习模型参数", "B.用于最终评估模型",
         "C.用于部署上线", "D.展示给用户"],
        "A", "机器学习基础", "易",
        "训练集拟合参数；测试集评估；验证集调超参。"),
    _ex("下列哪个属于监督学习任务？",
        ["A.垃圾邮件分类", "B.客户聚类", "C.数据降维", "D.关联规则挖掘"],
        "A", "机器学习基础", "中",
        "分类有标签监督；聚类/降维/关联规则属无监督。"),
    _ex("测试集的作用是？",
        ["A.评估模型的泛化能力", "B.训练模型参数",
         "C.调整超参数", "D.清洗数据"],
        "A", "机器学习基础", "中",
        "测试集不参与训练与调参，只做最终评估。"),
    _ex("训练误差远小于测试误差通常说明？",
        ["A.模型过拟合", "B.模型欠拟合",
         "C.训练数据太少", "D.模型表现完美"],
        "A", "机器学习基础", "难",
        "过拟合时模型记住训练细节，泛化差。"),
    _ex("交叉验证的主要目的是？",
        ["A.更可靠地评估模型性能", "B.加快训练速度",
         "C.减少数据量", "D.增加特征数量"],
        "A", "机器学习基础", "难",
        "多次划分训练/验证取平均，评估更稳定。"),
    _ex("监督学习使用的训练数据特点是？",
        ["A.带标签", "B.无标签",
         "C.只有特征没有结果", "D.随机噪声"],
        "A", "监督学习", "易",
        "监督学习依赖带标签数据学习输入到输出的映射。"),
    _ex("分类问题的输出是？",
        ["A.离散类别", "B.连续数值",
         "C.任意曲线", "D.概率密度函数"],
        "A", "监督学习", "易",
        "分类输出离散类别，回归输出连续值。"),
    _ex("回归问题与分类问题的主要区别是？",
        ["A.回归输出连续值，分类输出离散类别", "B.回归输出类别",
         "C.分类输出连续值", "D.没有区别"],
        "A", "监督学习", "中",
        "输出类型（连续/离散）是两者的本质区别。"),
    _ex("监督学习的一般流程第一步是？",
        ["A.收集并标注数据", "B.直接部署模型",
         "C.调整超参数", "D.写测试报告"],
        "A", "监督学习", "中",
        "没有标注数据就无法训练监督模型。"),
    _ex("模型训练集准确率 99%、测试集 60%，最可能的原因是？",
        ["A.过拟合", "B.欠拟合",
         "C.数据未标注", "D.学习率太低"],
        "A", "监督学习", "难",
        "训练与测试差距大是过拟合的典型信号。"),
    _ex("正负样本比例 1:99 的数据集上，把所有样本都预测为多数类的模型准确率约？",
        ["A.99%，但几乎识别不了少数类", "B.50%",
         "C.0%", "D.与类别比例无关"],
        "A", "监督学习", "难",
        "准确率被多数类主导，需看精确率/召回率。"),
    _ex("无监督学习使用的数据是？",
        ["A.无标签数据", "B.带标签数据",
         "C.人工标注数据", "D.测试数据"],
        "A", "无监督学习", "易",
        "无监督学习从无标签数据中发现结构。"),
    _ex("聚类分析属于？",
        ["A.无监督学习", "B.监督学习",
         "C.强化学习", "D.都不属于"],
        "A", "无监督学习", "易",
        "聚类不需要标签，属无监督学习。"),
    _ex("下列哪个是无监督学习的典型任务？",
        ["A.客户分群", "B.房价预测",
         "C.垃圾邮件识别", "D.语音转文字"],
        "A", "无监督学习", "中",
        "分群即聚类；其余为监督任务。"),
    _ex("降维的主要目的之一是？",
        ["A.减少特征数量、便于可视化", "B.增加特征数量",
         "C.让模型更复杂", "D.提高标签质量"],
        "A", "无监督学习", "中",
        "降维压缩特征空间，去除冗余。"),
    _ex("无监督学习与监督学习的根本区别是？",
        ["A.训练数据是否有标签", "B.模型是否复杂",
         "C.是否使用神经网络", "D.是否需要 GPU"],
        "A", "无监督学习", "难",
        "是否有标签决定学习范式，与模型复杂度无关。"),
    _ex("主成分分析（PCA）属于？",
        ["A.无监督降维", "B.监督分类",
         "C.回归分析", "D.强化学习"],
        "A", "无监督学习", "难",
        "PCA 只利用特征本身找主方向，无需标签。"),
    _ex("一元线性回归拟合的是？",
        ["A.一条直线", "B.一条任意曲线",
         "C.一个圆", "D.多个平面"],
        "A", "线性回归", "易",
        "一元线性回归拟合一条直线。"),
    _ex("线性回归常用的损失函数是？",
        ["A.均方误差", "B.交叉熵",
         "C.0-1 损失", "D.合页损失"],
        "A", "线性回归", "易",
        "回归常用 MSE 衡量预测与真实值的差距。"),
    _ex("梯度下降中学习率的作用是？",
        ["A.控制每次参数更新的步长", "B.决定迭代总次数",
         "C.控制模型层数", "D.决定数据顺序"],
        "A", "线性回归", "中",
        "学习率控制每步更新幅度。"),
    _ex("线性回归模型 y=wx+b 中 w 的含义是？",
        ["A.斜率（特征权重）", "B.截距",
         "C.误差", "D.样本数量"],
        "A", "线性回归", "中",
        "w 是特征权重（斜率），b 是截距。"),
    _ex("学习率过大可能导致？",
        ["A.损失震荡甚至发散", "B.收敛速度一定更快",
         "C.模型一定更准确", "D.没有任何影响"],
        "A", "线性回归", "难",
        "步长过大越过最优点，损失震荡发散。"),
    _ex("多元线性回归特征高度相关（多重共线性）会导致？",
        ["A.系数估计不稳定", "B.模型一定更准确",
         "C.样本自动增加", "D.没有影响"],
        "A", "线性回归", "难",
        "共线性使系数方差增大、估计不稳定。"),
    _ex("逻辑回归主要用于解决什么问题？",
        ["A.二分类", "B.聚类",
         "C.降维", "D.图像生成"],
        "A", "逻辑回归", "易",
        "逻辑回归是经典二分类模型。"),
    _ex("逻辑回归把线性输出映射到 0~1 区间的函数是？",
        ["A.Sigmoid", "B.ReLU",
         "C.Tanh", "D.Softplus"],
        "A", "逻辑回归", "易",
        "Sigmoid 把任意实数映射到 (0,1)，输出即概率。"),
    _ex("逻辑回归输出值 0.8 的含义是？",
        ["A.样本属于正类的概率为 0.8", "B.属于负类的概率为 0.8",
         "C.损失值", "D.特征权重"],
        "A", "逻辑回归", "中",
        "逻辑回归输出正类概率。"),
    _ex("逻辑回归常用的损失函数是？",
        ["A.交叉熵损失", "B.均方误差",
         "C.绝对值误差", "D.0-1 损失"],
        "A", "逻辑回归", "中",
        "分类任务用交叉熵（对数损失）。"),
    _ex("逻辑回归的决策边界是？",
        ["A.线性（超平面）", "B.圆形",
         "C.任意曲线", "D.不存在"],
        "A", "逻辑回归", "难",
        "逻辑回归是线性分类器，边界为线性超平面。"),
    _ex("逻辑回归中的正则化参数主要作用是？",
        ["A.控制模型复杂度、防止过拟合", "B.增加特征",
         "C.提高学习率", "D.改变输出范围"],
        "A", "逻辑回归", "难",
        "正则化惩罚过大权重，控制复杂度。"),
    _ex("决策树的每个内部结点表示？",
        ["A.对一个特征的判断", "B.最终分类结果",
         "C.数据样本", "D.损失值"],
        "A", "决策树", "易",
        "内部结点做特征判断，叶结点给出结果。"),
    _ex("决策树的叶结点表示？",
        ["A.分类结果", "B.特征判断",
         "C.根结点", "D.训练过程"],
        "A", "决策树", "易",
        "叶结点输出类别。"),
    _ex("ID3 算法选择划分特征的标准是？",
        ["A.信息增益", "B.信息增益率",
         "C.基尼指数", "D.随机选择"],
        "A", "决策树", "中",
        "ID3 用信息增益；C4.5 用增益率；CART 用基尼指数。"),
    _ex("CART 分类树选择特征的标准是？",
        ["A.基尼指数", "B.信息增益",
         "C.信息增益率", "D.随机选择"],
        "A", "决策树", "中",
        "CART 用基尼指数衡量不纯度。"),
    _ex("决策树过拟合的常见表现是？",
        ["A.树过深、训练精度高而测试精度低", "B.树太浅",
         "C.训练精度低", "D.从不分裂"],
        "A", "决策树", "难",
        "树过深记住训练噪声，泛化差。"),
    _ex("决策树剪枝的作用是？",
        ["A.降低过拟合风险", "B.增加过拟合",
         "C.增加树的深度", "D.提高训练精度"],
        "A", "决策树", "难",
        "剪枝简化树结构，提升泛化。"),
    _ex("集成学习的基本思想是？",
        ["A.组合多个模型提升整体性能", "B.只使用单个模型",
         "C.减少模型数量", "D.不进行训练"],
        "A", "集成学习", "易",
        "多个弱学习器组合成强学习器。"),
    _ex("随机森林属于哪种集成方法？",
        ["A.Bagging", "B.Boosting",
         "C.Stacking", "D.都不属于"],
        "A", "集成学习", "易",
        "随机森林=Bagging+决策树。"),
    _ex("Bagging 中每个基学习器的训练集是？",
        ["A.有放回抽样得到的子集（Bootstrap）", "B.完全相同的全集",
         "C.测试集", "D.空集"],
        "A", "集成学习", "中",
        "Bootstrap 抽样制造样本差异。"),
    _ex("Boosting 训练基学习器的特点是？",
        ["A.串行训练、关注被错分的样本", "B.并行训练",
         "C.完全独立", "D.只用第一个模型"],
        "A", "集成学习", "中",
        "Boosting 串行纠错，降低偏差。"),
    _ex("随机森林相比单棵决策树的主要优点是？",
        ["A.方差更低、泛化能力更好", "B.一定更快",
         "C.不需要数据", "D.永远 100% 准确"],
        "A", "集成学习", "难",
        "多树投票平滑单树方差。"),
    _ex("AdaBoost 中样本权重的变化规律是？",
        ["A.被错分样本权重增大", "B.被错分样本权重减小",
         "C.权重不变", "D.随机变化"],
        "A", "集成学习", "难",
        "错分样本权重增大，后续模型重点学习。"),
    _ex("K-Means 中的 K 表示？",
        ["A.簇的个数", "B.迭代次数",
         "C.特征数量", "D.样本数量"],
        "A", "聚类分析", "易",
        "K 是预设的簇个数。"),
    _ex("K-Means 的质心是指？",
        ["A.簇内样本的均值", "B.随机样本",
         "C.第一个样本", "D.最后一个样本"],
        "A", "聚类分析", "易",
        "质心为簇内样本均值。"),
    _ex("K-Means 的迭代过程是？",
        ["A.分配样本到最近质心→重新计算质心，反复直到稳定", "B.只计算一次",
         "C.随机打乱样本", "D.梯度下降求导"],
        "A", "聚类分析", "中",
        "分配与更新交替直至收敛。"),
    _ex("K-Means 的结果对什么比较敏感？",
        ["A.初始质心的选择", "B.特征名称",
         "C.样本标签", "D.数据文件路径"],
        "A", "聚类分析", "中",
        "初始质心不同可能收敛到不同局部最优。"),
    _ex("确定聚类数 K 的常用方法是？",
        ["A.肘部法（观察 SSE 随 K 变化的拐点）", "B.随便猜",
         "C.越大越好", "D.永远取 2"],
        "A", "聚类分析", "难",
        "SSE 下降变缓的拐点即合适 K。"),
    _ex("K-Means 不适合处理哪种数据分布？",
        ["A.非凸形状（如环形）的簇", "B.球形簇",
         "C.大小相近的簇", "D.密度均匀的簇"],
        "A", "聚类分析", "难",
        "K-Means 按距离均值划分，偏好凸形球状簇。"),
    _ex("降维是指？",
        ["A.减少特征数量", "B.减少样本数量",
         "C.减少类别数量", "D.减少模型层数"],
        "A", "降维", "易",
        "降维压缩特征空间。"),
    _ex("PCA 的目标是？",
        ["A.找到方差最大的投影方向", "B.找到均值最大的方向",
         "C.随机投影", "D.增加特征"],
        "A", "降维", "易",
        "方差大保留信息多。"),
    _ex("PCA 得到的主成分之间的关系是？",
        ["A.相互正交（不相关）", "B.完全相同",
         "C.线性相关", "D.随机"],
        "A", "降维", "中",
        "主成分两两正交，信息不重叠。"),
    _ex("下列哪个不是降维的好处？",
        ["A.增加模型参数量", "B.减少计算量",
         "C.去除冗余特征", "D.便于可视化"],
        "A", "降维", "中",
        "降维减少参数量而非增加。"),
    _ex("对量纲不同的特征做 PCA 之前通常需要？",
        ["A.标准化（去均值、除标准差）", "B.随机打乱",
         "C.删除所有特征", "D.加密数据"],
        "A", "降维", "难",
        "PCA 对方差敏感，量纲不同会使大方差特征主导。"),
    _ex("第一个主成分对应的是？",
        ["A.数据方差最大的方向", "B.方差最小的方向",
         "C.任意方向", "D.均值方向"],
        "A", "降维", "难",
        "第一主成分保留最大方差。"),
    _ex("二分类中准确率的定义是？",
        ["A.预测正确的样本数/总样本数", "B.正类正确数",
         "C.负类错误数", "D.错误样本数"],
        "A", "模型评估", "易",
        "准确率=正确预测/总样本。"),
    _ex("混淆矩阵中 TP 表示？",
        ["A.正类被预测为正类", "B.正类被预测为负类",
         "C.负类被预测为正类", "D.负类被预测为负类"],
        "A", "模型评估", "易",
        "TP=True Positive 真正例。"),
    _ex("精确率（Precision）的公式是？",
        ["A.TP/(TP+FP)", "B.TP/(TP+FN)",
         "C.TN/(TN+FP)", "D.(TP+TN)/总数"],
        "A", "模型评估", "中",
        "精确率=预测为正的样本中真正例占比。"),
    _ex("召回率（Recall）的公式是？",
        ["A.TP/(TP+FN)", "B.TP/(TP+FP)",
         "C.TN/(TN+FN)", "D.FP/(FP+TN)"],
        "A", "模型评估", "中",
        "召回率=真实正例中被找出的占比。"),
    _ex("F1 分数是？",
        ["A.精确率与召回率的调和平均", "B.两者的算术平均",
         "C.准确率", "D.召回率的一半"],
        "A", "模型评估", "难",
        "F1=2PR/(P+R)，兼顾精确率与召回率。"),
    _ex("数据严重不平衡时仅用准确率评估的缺点是？",
        ["A.多数类主导、掩盖少数类识别能力", "B.结果总是偏低",
         "C.无法计算", "D.没有任何缺点"],
        "A", "模型评估", "难",
        "不平衡下应参考精确率/召回率/F1。"),
    _ex("过拟合是指？",
        ["A.模型过度学习训练数据、泛化能力差", "B.模型学得太少",
         "C.数据太多", "D.训练太慢"],
        "A", "过拟合与正则化", "易",
        "过拟合记住噪声，测试表现差。"),
    _ex("欠拟合是指？",
        ["A.模型未能充分学习数据规律", "B.模型过度学习",
         "C.数据缺失", "D.模型太大"],
        "A", "过拟合与正则化", "易",
        "欠拟合训练与测试表现都差。"),
    _ex("L2 正则化的作用是？",
        ["A.限制权重大小、防止过拟合", "B.增加权重",
         "C.删除特征", "D.加快数据读取"],
        "A", "过拟合与正则化", "中",
        "L2 惩罚大权重，使权重平滑缩小。"),
    _ex("下列哪个不是缓解过拟合的方法？",
        ["A.继续增大模型复杂度", "B.增加训练数据",
         "C.正则化", "D.早停"],
        "A", "过拟合与正则化", "中",
        "增大复杂度会加重过拟合。"),
    _ex("L1 与 L2 正则化的主要区别是？",
        ["A.L1 可产生稀疏权重（特征选择），L2 使权重平滑缩小", "B.完全一样",
         "C.L1 更慢", "D.L2 会删除模型"],
        "A", "过拟合与正则化", "难",
        "L1 的尖角解使部分权重为 0。"),
    _ex("早停（Early Stopping）的思想是？",
        ["A.验证集误差开始上升时停止训练", "B.训练误差为 0 时停止",
         "C.第一轮就停止", "D.永不停止"],
        "A", "过拟合与正则化", "难",
        "验证误差回升即过拟合信号，及时停止。"),
    _ex("特征工程是指？",
        ["A.对原始数据进行变换、选择与构造，提升模型效果", "B.修改模型结构",
         "C.调整学习率", "D.部署模型"],
        "A", "特征工程", "易",
        "特征工程直接决定模型效果上限。"),
    _ex("独热编码（One-Hot）主要用于处理什么特征？",
        ["A.类别特征", "B.连续数值特征",
         "C.时间特征", "D.图像特征"],
        "A", "特征工程", "易",
        "One-Hot 把类别扩为 0/1 向量。"),
    _ex("特征缩放（标准化/归一化）对哪个模型尤其重要？",
        ["A.K 近邻等基于距离的模型", "B.决策树",
         "C.规则模型", "D.所有模型都不需要"],
        "A", "特征工程", "中",
        "距离模型对量纲敏感；决策树对单调缩放不敏感。"),
    _ex("数据标准化常用的方法是？",
        ["A.(x-均值)/标准差", "B.x+1",
         "C.x²", "D.取对数后乘 2"],
        "A", "特征工程", "中",
        "标准化使特征均值为 0、方差为 1。"),
    _ex("特征选择的主要目的是？",
        ["A.去除无关/冗余特征、降低维度", "B.增加特征数量",
         "C.让模型更复杂", "D.提高标签质量"],
        "A", "特征工程", "难",
        "特征选择减少噪声与计算量。"),
    _ex("训练集和测试集的特征缩放应该？",
        ["A.用训练集统计量统一缩放", "B.各自独立缩放",
         "C.只缩放测试集", "D.不做缩放"],
        "A", "特征工程", "难",
        "测试集须用训练集算出的均值/标准差，否则数据泄漏。"),
]

ML_KB_DOC = """# 机器学习知识库

## 一、机器学习基础
机器学习让计算机从数据中自动学习规律，无需人工编写全部规则。数据集通常划分为训练集、验证集与测试集：训练集拟合模型参数，验证集调整超参数，测试集只做最终评估。交叉验证通过多次划分取平均，得到更可靠的性能估计；训练误差远小于测试误差通常意味着过拟合。

## 二、监督学习
监督学习使用带标签的数据训练模型，典型任务包括分类（输出离散类别，如垃圾邮件识别）与回归（输出连续数值，如房价预测）。一般流程为收集标注数据、划分数据集、训练模型、评估调优。正负样本严重不平衡时，仅看准确率会掩盖少数类的识别能力。

## 三、无监督学习
无监督学习使用无标签数据，从数据本身发现结构，典型任务包括聚类（如客户分群）与降维（如主成分分析 PCA）。与监督学习的根本区别在于训练数据是否有标签。

## 四、线性回归
线性回归拟合特征与目标值之间的线性关系，常用均方误差（MSE）作为损失函数。梯度下降通过迭代更新参数逼近最优解，学习率控制每步更新的步长：过大会震荡发散，过小则收敛缓慢。多元回归中特征高度相关（多重共线性）会使系数估计不稳定。

## 五、逻辑回归
逻辑回归虽名为"回归"，实际是用于二分类的线性分类模型。它用 Sigmoid 函数把线性输出映射到 (0,1) 区间作为概率，常用交叉熵作为损失函数。输出 0.8 表示样本属于正类的概率为 0.8；阈值 0.5 时低于阈值判为负类。逻辑回归无法直接解决线性不可分问题，需借助特征变换。

## 六、决策树
决策树是树形结构的分类模型：内部结点表示对一个特征的判断，叶结点表示分类结果。ID3 用信息增益选择划分特征（偏好取值较多的特征），C4.5 用信息增益率修正，CART 用基尼指数。信息熵衡量数据集的不确定性，信息增益=划分前熵-划分后条件熵。树过深容易过拟合，剪枝可降低过拟合风险；连续特征通过寻找最优切分点离散化处理。

## 七、集成学习
集成学习组合多个基学习器提升整体性能。Bagging（如随机森林）用 Bootstrap 有放回抽样训练多个独立模型，降低方差；Boosting（如 AdaBoost）串行训练，被错分的样本权重增大，让后续模型重点学习难例。随机森林相比单棵决策树方差更低、泛化能力更好。

## 八、聚类分析
K-Means 是最常用的聚类算法，K 表示簇的个数。它反复执行"把样本分配到最近的质心→重新计算质心"直到稳定，质心是簇内样本的均值。K-Means 对初始质心选择敏感，适合凸形（如球形）簇，不适合环形等非凸分布；肘部法（观察 SSE 随 K 变化的拐点）可帮助确定聚类数。

## 九、降维
降维减少特征数量，可降低计算量、去除冗余并便于可视化。PCA 寻找数据方差最大的投影方向作为主成分，各主成分相互正交；第一主成分对应方差最大的方向。PCA 对方差敏感，量纲不同的特征应先标准化（去均值、除标准差）。

## 十、模型评估
混淆矩阵记录 TP（正类预测为正类）、FP、TN、FN 四类结果。精确率=TP/(TP+FP)，召回率=TP/(TP+FN)，准确率=预测正确数/总数。F1 分数是精确率与召回率的调和平均，兼顾两者。数据严重不平衡时，准确率被多数类主导，应参考精确率、召回率与 F1。

## 十一、过拟合与正则化
过拟合指模型过度学习训练数据、泛化能力差；欠拟合指模型未能充分学习数据规律。缓解过拟合的方法包括增加训练数据、正则化、早停、简化模型等；继续增大模型复杂度会加重过拟合。L1 正则化可产生稀疏权重（特征选择），L2 正则化使权重平滑缩小。早停在验证集误差开始上升时停止训练。

## 十二、特征工程
特征工程对原始数据进行变换、选择与构造以提升模型效果。独热编码处理类别特征；标准化（(x-均值)/标准差）对 K 近邻等基于距离的模型尤其重要，决策树对单调缩放不敏感。特征选择去除无关与冗余特征；训练集和测试集须用训练集统计量统一缩放，防止数据泄漏。
"""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py -v`
Expected: 全 PASS（DS 用例不破 + ML 新用例过）。

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/seed_learn_bank.py backend/tests/test_seed_learn_bank.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(seed): 机器学习方向图谱与 72 题+知识库演示文档（Plan G Task 3）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: AI 方向补齐 72 题 + 月考题自动入池钉测试

**Files:**
- Modify: `backend/scripts/seed_learn_bank.py`（AI_EXERCISES 追加 54 题）
- Test: `backend/tests/test_seed_learn_bank.py`（追加 AI 用例）、`backend/tests/test_learn_practice.py`（追加月考题入池用例）

**Interfaces:**
- Consumes: Task 2/3 的数据模块与测试夹具；Task 1 的 collect_questions/diagnostic_questions（月考题入池链路）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_seed_learn_bank.py` 末尾追加：

```python
def test_ai_direction_72_questions_distribution():
    """AI 方向补齐后：12 知识点 × 易2/中2/难2 = 72 题。"""
    assert len(AI_EXERCISES) == 72
    assert {k for k, _ in AI_KPS} == {q["知识点"] for q in AI_EXERCISES}
    dist = _distribution(AI_EXERCISES)
    assert all(count == 2 for count in dist.values())
    assert len(dist) == 36


def test_ai_questions_wellformed():
    stems = [q["题干"] for q in AI_EXERCISES]
    assert len(stems) == len(set(stems))
    for q in AI_EXERCISES:
        assert len(q["选项"]) == 4
        assert all(o[:2] in {f"{c}." for c in "ABCD"} for o in q["选项"])
        assert q["答案"] in "ABCD"
        assert q["解析"].strip() and q["难度"] in ("易", "中", "难")
```

`backend/tests/test_learn_practice.py` 末尾追加：

```python
def test_monthly_exam_questions_auto_enter_practice_pool(db, seeded):
    """三通道①：月考题选择题自动入练习池（既有链路钉住，简答题被过滤）。"""
    qs = learn_practice.collect_questions(db, course_id=seeded["course"].id)
    assert "月考梯度下降题" in [q["题干"] for q in qs]
    diag = learn_practice.diagnostic_questions(db, course_id=seeded["course"].id)
    assert any(q["stem"] == "月考梯度下降题" for q in diag)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py::test_ai_direction_72_questions_distribution tests/test_learn_practice.py::test_monthly_exam_questions_auto_enter_practice_pool -v`
Expected: `test_ai_*` FAIL（AI 仅 18 题）；月考题用例应直接 PASS（既有链路，属钉住验证）——若 FAIL 则先查实现回归再继续。

- [ ] **Step 3: AI_EXERCISES 追加 54 题**

在 `seed_learn_bank.py` 的 `AI_EXERCISES` 列表末尾（`_ex("以下哪个任务属于自然语言处理？", ...)` 条目之后、`]` 之前）逐字追加：

```python
    # ---- Plan G 补齐：每知识点补至 易2/中2/难2（+54 题） ----
    _ex("Python 中向列表 [1,2,3] 末尾追加元素 4，正确的方法是？",
        ["A.[1,2,3].append(4)", "B.[1,2,3].add(4)", "C.[1,2,3].push(4)", "D.[1,2,3].insert(4)"],
        "A", "Python基础", "易",
        "列表用 append 在末尾追加元素，结果为 [1,2,3,4]。"),
    _ex("Python 中 dict.get(key) 在键不存在时返回？",
        ["A.None（或指定默认值）", "B.抛出 KeyError", "C.0", "D.空字符串"],
        "A", "Python基础", "中",
        "get 是安全取值，缺键返回 None 或传入的默认值；d[key] 才会抛 KeyError。"),
    _ex("Python 中遍历字典键值对的方法是？",
        ["A.d.items()", "B.d.keys()", "C.d.values()", "D.d.get()"],
        "A", "Python基础", "中",
        "items() 返回 (键, 值) 元组列表。"),
    _ex("下面代码输出是？print([i*i for i in range(3) if i % 2 == 0])",
        ["A.[0,4]", "B.[0,1,4]", "C.[1,4]", "D.[4]"],
        "A", "Python基础", "难",
        "range(3)=0,1,2，筛出偶数 0、2，平方得 [0,4]。"),
    _ex("Python 中可变参数 *args 在函数内部是什么类型？",
        ["A.元组", "B.列表", "C.字典", "D.集合"],
        "A", "Python基础", "难",
        "*args 打包成元组；**kwargs 打包成字典。"),
    _ex("单位矩阵的特点是？",
        ["A.主对角线元素为 1，其余为 0", "B.所有元素为 1",
         "C.所有元素为 0", "D.主对角线为 0"],
        "A", "线性代数", "易",
        "单位矩阵主对角线为 1，其余为 0，记作 I。"),
    _ex("2×3 矩阵与 3×4 矩阵相乘，结果矩阵的形状是？",
        ["A.2×4", "B.3×3", "C.2×3", "D.3×4"],
        "A", "线性代数", "中",
        "结果行数=左矩阵行数、列数=右矩阵列数。"),
    _ex("两个矩阵能够相加的前提是？",
        ["A.形状完全相同", "B.都是方阵", "C.列数相等", "D.行数相等"],
        "A", "线性代数", "中",
        "矩阵加法按元素对应相加，形状必须相同。"),
    _ex("矩阵 A 的逆矩阵 A⁻¹ 满足？",
        ["A.A·A⁻¹ = I（单位矩阵）", "B.A·A⁻¹ = A",
         "C.A·A⁻¹ = 0", "D.恒不存在"],
        "A", "线性代数", "难",
        "逆矩阵满足 A·A⁻¹=A⁻¹·A=I；奇异矩阵无逆。"),
    _ex("两个向量的点积（内积）结果是？",
        ["A.标量", "B.向量", "C.矩阵", "D.张量"],
        "A", "线性代数", "难",
        "点积逐元素相乘再求和，结果是标量。"),
    _ex("掷一枚均匀骰子，出现 6 的概率是？",
        ["A.1/6", "B.1/2", "C.1/3", "D.1"],
        "A", "概率统计", "易",
        "6 个等可能面，出现 6 的概率 1/6。"),
    _ex("随机变量的期望 E[X] 表示？",
        ["A.长期平均取值", "B.最大值", "C.最小值", "D.方差"],
        "A", "概率统计", "中",
        "期望是随机变量的加权平均（长期平均）。"),
    _ex("方差衡量的是？",
        ["A.数据的离散程度", "B.数据的中心位置",
         "C.数据个数", "D.数据的最大值"],
        "A", "概率统计", "中",
        "方差/标准差衡量数据偏离均值的程度。"),
    _ex("事件 A、B 相互独立，P(A)=0.5，P(B)=0.4，则 P(A∩B)=？",
        ["A.0.2", "B.0.9", "C.0.5", "D.0.4"],
        "A", "概率统计", "难",
        "独立事件同时发生概率相乘：0.5×0.4=0.2。"),
    _ex("正态分布 N(μ, σ²) 的均值是？",
        ["A.μ", "B.σ", "C.σ²", "D.0"],
        "A", "概率统计", "难",
        "N(μ, σ²) 中 μ 为均值、σ² 为方差。"),
    _ex("梯度下降与梯度上升的关系是？",
        ["A.梯度下降沿负梯度方向极小化损失，梯度上升沿正梯度方向极大化目标", "B.两者完全相同",
         "C.梯度上升不做迭代", "D.梯度下降只能用于线性模型"],
        "A", "梯度下降", "中",
        "两者方向相反、目标相反，都是迭代更新。"),
    _ex("为什么负梯度方向是函数值下降最快的方向？",
        ["A.方向导数在负梯度方向取最小值", "B.梯度就是随机方向",
         "C.与梯度无关", "D.负梯度方向一定指向全局最优点"],
        "A", "梯度下降", "难",
        "方向导数=|∇f|cosθ，θ=π（负梯度）时最小；不保证指向全局最优点。"),
    _ex("线性回归预测的目标变量是？",
        ["A.连续数值", "B.离散类别", "C.文本", "D.图像"],
        "A", "线性回归", "易",
        "线性回归输出连续数值。"),
    _ex("梯度下降法与最小二乘法求解线性回归的区别是？",
        ["A.梯度下降是迭代近似求解，最小二乘可直接解析求解（需矩阵可逆）", "B.两者完全相同",
         "C.最小二乘更慢", "D.梯度下降不需要数据"],
        "A", "线性回归", "中",
        "最小二乘有闭式解但需矩阵可逆；梯度下降通用迭代。"),
    _ex("均方误差（MSE）作为损失函数的特点是？",
        ["A.对大误差惩罚更重（平方放大）", "B.对误差不敏感",
         "C.只能用于分类", "D.输出恒为负数"],
        "A", "线性回归", "难",
        "平方项使大误差贡献更大，对离群点敏感。"),
    _ex("逻辑回归是哪种类型的模型？",
        ["A.线性分类模型", "B.非线性回归模型", "C.聚类模型", "D.生成模型"],
        "A", "逻辑回归", "易",
        "逻辑回归是线性分类模型（判别模型）。"),
    _ex("逻辑回归输出概率 0.8 的含义是？",
        ["A.样本属于正类的概率为 0.8", "B.样本属于负类的概率为 0.8",
         "C.损失值", "D.特征权重"],
        "A", "逻辑回归", "中",
        "逻辑回归输出正类概率。"),
    _ex("二分类逻辑回归阈值取 0.5 时，输出概率 0.3 的样本被判为？",
        ["A.负类", "B.正类", "C.无法判断", "D.两类都算"],
        "A", "逻辑回归", "难",
        "0.3 < 0.5，判为负类。"),
    _ex("逻辑回归无法直接解决的问题是？",
        ["A.线性不可分的分类问题（需特征变换）", "B.二分类问题",
         "C.输出概率的问题", "D.线性可分问题"],
        "A", "逻辑回归", "难",
        "线性分类器需要特征变换才能处理线性不可分数据。"),
    _ex("决策树模型的结构是？",
        ["A.树形结构", "B.线性结构", "C.图状结构", "D.栈结构"],
        "A", "决策树", "易",
        "决策树是树形结构：内部结点判断、叶结点给结果。"),
    _ex("信息熵衡量的是？",
        ["A.数据集的不确定性", "B.数据的均值",
         "C.数据的方差", "D.样本数量"],
        "A", "决策树", "中",
        "熵越大不确定性越大。"),
    _ex("信息增益的计算方式是？",
        ["A.划分前熵 - 划分后条件熵", "B.熵 + 条件熵",
         "C.熵 × 2", "D.样本数之差"],
        "A", "决策树", "中",
        "信息增益=熵减，表示不确定性下降幅度。"),
    _ex("ID3 的信息增益在选择特征时偏好？",
        ["A.取值较多的特征", "B.取值最少的特征",
         "C.连续特征", "D.无关特征"],
        "A", "决策树", "难",
        "取值多易把数据分碎、增益虚高，C4.5 用增益率修正。"),
    _ex("决策树处理连续特征的方法是？",
        ["A.将其离散化（寻找最优切分点）", "B.无法处理",
         "C.直接忽略", "D.编码为随机数"],
        "A", "决策树", "难",
        "连续特征按候选切分点二分离散化处理。"),
    _ex("神经网络的基本组成单元是？",
        ["A.神经元", "B.像素", "C.字符", "D.文件"],
        "A", "神经网络", "易",
        "神经元是网络基本单元。"),
    _ex("神经网络相邻层之间通过什么连接？",
        ["A.权重（可学习参数）", "B.文件", "C.字符串", "D.随机数"],
        "A", "神经网络", "易",
        "层间连接带可学习权重。"),
    _ex("前向传播的作用是？",
        ["A.从输入逐层计算得到输出", "B.更新权重",
         "C.计算梯度", "D.初始化参数"],
        "A", "神经网络", "中",
        "前向传播计算输出；反向传播计算梯度。"),
    _ex("隐藏层使用 ReLU 激活函数的主要优点是？",
        ["A.缓解梯度消失、计算简单", "B.输出有界",
         "C.保证收敛", "D.不需要数据"],
        "A", "神经网络", "难",
        "ReLU 正区间梯度恒为 1，缓解梯度消失。"),
    _ex("多层神经网络必须使用非线性激活函数的原因是？",
        ["A.否则多层网络等价于单层线性变换", "B.激活函数能加快训练",
         "C.可以减少参数", "D.防止过拟合"],
        "A", "神经网络", "难",
        "线性变换复合仍是线性，深度失去意义。"),
    _ex("反向传播算法的作用是？",
        ["A.计算损失对各参数的梯度", "B.计算网络输出",
         "C.归一化数据", "D.选择激活函数"],
        "A", "反向传播", "易",
        "反向传播求梯度，梯度下降做更新。"),
    _ex("反向传播是在哪个阶段进行的？",
        ["A.训练阶段", "B.推理（预测）阶段",
         "C.部署阶段", "D.数据收集阶段"],
        "A", "反向传播", "易",
        "只有训练阶段才需要计算梯度。"),
    _ex("反向传播中梯度从哪层向哪层传播？",
        ["A.从输出层向输入层", "B.从输入层向输出层",
         "C.随机传播", "D.只在输出层"],
        "A", "反向传播", "中",
        "链式法则从输出层逐层回传到输入层。"),
    _ex("梯度消失问题通常发生在？",
        ["A.深层网络中梯度逐层缩小趋近于 0", "B.浅层网络",
         "C.输出层", "D.数据预处理阶段"],
        "A", "反向传播", "难",
        "梯度逐层连乘变小，浅层参数几乎不更新。"),
    _ex("学习率调度（衰减）的目的是？",
        ["A.训练后期减小步长、帮助收敛", "B.增大梯度",
         "C.增加参数量", "D.删除网络层"],
        "A", "反向传播", "难",
        "后期小步长便于收敛到更优解。"),
    _ex("深度学习与浅层学习的主要区别是？",
        ["A.网络层数更深、能自动提取特征", "B.数据更少",
         "C.不需要训练", "D.只使用决策树"],
        "A", "深度学习基础", "易",
        "深层网络自动学习层次化特征。"),
    _ex("Epoch（轮次）是指？",
        ["A.全部训练数据完整过一遍", "B.一个样本过一遍",
         "C.一个 batch 过一遍", "D.一次预测"],
        "A", "深度学习基础", "中",
        "Epoch=完整遍历训练集一次。"),
    _ex("Batch Size 是指？",
        ["A.每次迭代使用的样本数", "B.总样本数",
         "C.模型层数", "D.学习率"],
        "A", "深度学习基础", "中",
        "Batch Size 是每个批次的样本数。"),
    _ex("GPU 训练深度学习模型快的根本原因是？",
        ["A.大规模并行矩阵运算能力强", "B.时钟频率高",
         "C.内存大", "D.不需要梯度下降"],
        "A", "深度学习基础", "难",
        "深度学习核心是矩阵运算，GPU 并行核多。"),
    _ex("训练集、验证集、测试集的标准用法是？",
        ["A.训练集训练、验证集调超参、测试集最终评估", "B.全部混用",
         "C.只用训练集", "D.只用测试集"],
        "A", "深度学习基础", "难",
        "三集分工不同，混用会导致评估失真。"),
    _ex("CNN 中的卷积层主要用于？",
        ["A.提取局部特征", "B.输出类别",
         "C.存储数据", "D.排序"],
        "A", "卷积神经网络", "易",
        "卷积层提取局部特征。"),
    _ex("CNN 主要擅长处理什么类型的数据？",
        ["A.图像", "B.纯文本词频统计",
         "C.一维时序趋势", "D.关系型表格"],
        "A", "卷积神经网络", "易",
        "卷积核滑动扫描空间结构，图像是其主战场。"),
    _ex("卷积核（滤波器）的作用是？",
        ["A.在输入上滑动检测局部模式", "B.随机打乱数据",
         "C.全连接所有像素", "D.删除数据"],
        "A", "卷积神经网络", "中",
        "卷积核滑动做局部加权，检测边缘/纹理等模式。"),
    _ex("相比全连接层，卷积层的两大特性是？",
        ["A.局部连接与权值共享", "B.全局连接与独立权重",
         "C.随机连接", "D.没有参数"],
        "A", "卷积神经网络", "难",
        "局部连接与权值共享大幅减少参数量。"),
    _ex("图像分类 CNN 的典型结构顺序是？",
        ["A.卷积→激活→池化…→全连接→softmax", "B.全连接→卷积",
         "C.池化→全连接→卷积", "D.softmax→卷积"],
        "A", "卷积神经网络", "难",
        "卷积提取特征、全连接汇总、softmax 输出类别概率。"),
    _ex("NLP 中的分词是指？",
        ["A.把句子切分为词语", "B.把词切分为字母",
         "C.把段落合并", "D.翻译句子"],
        "A", "自然语言处理", "易",
        "分词是中文 NLP 的基础预处理。"),
    _ex("词向量（Word Embedding）的作用是？",
        ["A.把词语表示为稠密数值向量", "B.把词变成图片",
         "C.删除停用词", "D.标注词性"],
        "A", "自然语言处理", "易",
        "词向量把词映射为可计算的稠密向量。"),
    _ex("文本分类任务的输入和输出是？",
        ["A.输入一段文本，输出类别标签", "B.输入图片，输出文本",
         "C.输入音频，输出文字", "D.输入表格，输出数字"],
        "A", "自然语言处理", "中",
        "文本分类是输入文本输出类别的监督任务。"),
    _ex("用余弦相似度比较词向量时，两个向量夹角越小，余弦值？",
        ["A.越大（越接近 1）", "B.越小", "C.恒为 0", "D.恒为负"],
        "A", "自然语言处理", "难",
        "cosθ 随夹角减小趋近 1，表示语义越相似。"),
    _ex("经典序列模型 RNN 的特点是？",
        ["A.具有循环连接、可处理变长序列", "B.只能看一个词",
         "C.不能处理文本", "D.与 CNN 完全相同"],
        "A", "自然语言处理", "难",
        "RNN 的循环连接让它按顺序处理变长序列。"),
```

（共 54 条：Python基础 5、线性代数 5、概率统计 5、梯度下降 2、线性回归 3、逻辑回归 4、决策树 5、神经网络 5、反向传播 5、深度学习基础 5、卷积神经网络 5、自然语言处理 5。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_seed_learn_bank.py tests/test_learn_practice.py -v`
Expected: 全 PASS（AI 72 题分布 + 月考题入池）。
再跑全量：`cd backend && python -m pytest -q > out_full.txt 2>&1` → FAILED = 0。

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/seed_learn_bank.py backend/tests/test_seed_learn_bank.py backend/tests/test_learn_practice.py
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(seed): AI 方向补齐至 72 题+月考题自动入池链路钉测试（Plan G Task 4）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 知识库出题（生成服务 + 备课 API + 备课前端入口）

**Files:**
- Modify: `backend/app/services/kb_service.py`（retrieve_chunks）
- Modify: `backend/app/services/prep_generator.py`（_KB_EXERCISES_PROMPT + generate_kb_exercises）
- Modify: `backend/app/api/prep.py`（GenerateIn.difficulty、kb_exercises 分支 + _generate_kb_exercises）
- Modify: `frontend/src/views/prep/PrepCourseView.vue`
- Test: `backend/tests/test_prep_kb_exercises.py`（新建）

**Interfaces:**
- Consumes: Task 1 的课程/Lesson 模型；既有 `kb_service._load_collections`/`hybrid_retrieve`（`app.services.rag`）；`prep_generator._call_json/validate_exercises`；`api/prep.py` 的 `_get_course/_snapshot`；前端 `api/prep.ts` 的 `generateContent`。
- Produces:
  - `kb_service.retrieve_chunks(user, query, db, *, top_k=8, vector_store=None, embedder=None, reranker=None) -> list`（hit 含 `.chunk`，`.chunk` 有 `.text`/`.source`）
  - `prep_generator.generate_kb_exercises(course_name, subject, chapter, knowledge_points, count, difficulty, kb_material, llm=None) -> dict`
  - `POST /api/prep/courses/{id}/generate` 支持 `type=kb_exercises`，响应 `{type, content, lesson:{lesson_id, title, added, total}}`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_prep_kb_exercises.py` 新建：

```python
# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17 扩展：知识库出题)
"""知识库出题测试：prompt 组装/结构校验/生成即入学习题库/检索空手 404/LLM 失败 502。"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import BizError
from app.services import kb_service, prep_generator
from app.services.llm_gateway import LLMError

EXERCISES_KB = {
    "习题": [
        {"题干": "知识库出题演示题1", "选项": ["A.甲", "B.乙", "C.丙", "D.丁"],
         "答案": "A", "解析": "解析1", "知识点": "线性表", "难度": "易"},
        {"题干": "知识库出题演示题2", "选项": ["A.甲", "B.乙", "C.丙", "D.丁"],
         "答案": "B", "解析": "解析2", "知识点": "栈与队列", "难度": "中"},
    ]
}


class _FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, messages, temperature=0.3):
        self.calls.append({"messages": messages, "temperature": temperature})
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _FakeHit:
    def __init__(self, text, source="数据结构与算法知识库.md"):
        self.chunk = SimpleNamespace(text=text, source=source, page=1)


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


def test_generate_kb_exercises_prompt_and_temperature():
    llm = _FakeLLM(EXERCISES_KB)
    result = prep_generator.generate_kb_exercises(
        course_name="数据结构与算法", subject="数据结构与算法", chapter="第3章",
        knowledge_points=["线性表", "栈与队列"], count=2, difficulty="中",
        kb_material="【资料】线性表是有限序列。", llm=llm)
    assert result == EXERCISES_KB
    prep_generator.validate_exercises(result)  # 结构校验通过
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "数据结构与算法" in prompt and "线性表" in prompt
    assert "题目数量：2 道" in prompt and "难度：中" in prompt
    assert "线性表是有限序列" in prompt and "仅依据" in prompt
    assert llm.calls[0]["temperature"] == 0.3


def test_generate_kb_exercises_validation_missing_keys():
    llm = _FakeLLM({"习题": [{"题干": "只有题干"}]})
    result = prep_generator.generate_kb_exercises(
        "课程", "学科", "章", ["知识点"], 1, "", "资料", llm=llm)
    with pytest.raises(BizError):
        prep_generator.validate_exercises(result)


def test_kb_exercises_generate_saves_to_lesson(client, monkeypatch):
    """生成即入学习题库：自动落 exercises lesson；同题干重复生成去重。"""
    headers = _register_login(client, "t_kb", "teacher")
    course = _create_course(client, headers, name="数据结构与算法")
    llm = _FakeLLM(EXERCISES_KB)
    monkeypatch.setattr(prep_generator, "get_gateway", lambda: llm)
    monkeypatch.setattr(kb_service, "retrieve_chunks",
                        lambda *a, **kw: [_FakeHit("线性表是有限序列。"),
                                          _FakeHit("栈是先进后出。")])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "chapter": "第3章",
                             "knowledge_points": ["线性表"], "count": 2, "difficulty": "中"},
                       headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "kb_exercises"
    assert body["lesson"]["added"] == 2 and body["lesson"]["total"] == 2
    lessons = client.get(f"/api/prep/courses/{course['id']}/lessons",
                         headers=headers).json()
    assert len(lessons) == 1
    assert lessons[0]["title"] == "数据结构与算法知识库生成习题"
    assert lessons[0]["lesson_type"] == "exercises"
    assert len(lessons[0]["content_json"]["习题"]) == 2
    # 再次生成同批题：同题干去重，不重复追加
    resp2 = client.post(f"/api/prep/courses/{course['id']}/generate",
                        json={"type": "kb_exercises", "knowledge_points": ["线性表"],
                              "count": 2, "difficulty": ""},
                        headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["lesson"]["added"] == 0
    assert resp2.json()["lesson"]["total"] == 2


def test_kb_exercises_no_hits_404(client, monkeypatch):
    headers = _register_login(client, "t_kb2", "teacher")
    course = _create_course(client, headers)
    monkeypatch.setattr(kb_service, "retrieve_chunks", lambda *a, **kw: [])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "knowledge_points": ["梯度下降"]},
                       headers=headers)
    assert resp.status_code == 404
    assert "知识库" in resp.json()["detail"]


def test_kb_exercises_llm_error_502(client, monkeypatch):
    headers = _register_login(client, "t_kb3", "teacher")
    course = _create_course(client, headers)
    monkeypatch.setattr(prep_generator, "get_gateway",
                        lambda: _FakeLLM(LLMError("密钥未配置")))
    monkeypatch.setattr(kb_service, "retrieve_chunks",
                        lambda *a, **kw: [_FakeHit("资料")])
    resp = client.post(f"/api/prep/courses/{course['id']}/generate",
                       json={"type": "kb_exercises", "knowledge_points": ["线性表"]},
                       headers=headers)
    assert resp.status_code == 502
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_prep_kb_exercises.py -v`
Expected: FAIL（generate_kb_exercises 不存在 / API 400 不支持类型）→ RED 证据。

- [ ] **Step 3: 实现**

`backend/app/services/kb_service.py` —— 在 `_load_collections` 之后追加：

```python
def retrieve_chunks(user: User, query: str, db: Session, *, top_k: int = 8,
                    vector_store=None, embedder=None, reranker=None) -> list:
    """混合检索知识库文本块（公共库+本人私有库）：备课「从知识库生成习题」复用问答检索路径。

    与 answer_events 相同的显式解析约定：经本模块 get_embedder/get_vector_store 取值后
    传入 hybrid_retrieve，使 monkeypatch 对检索路径生效（Plan C Task 6 Minor #1）。
    """
    emb = embedder or get_embedder()
    vs = vector_store or get_vector_store()
    return hybrid_retrieve(query, _load_collections(user, db), top_k=top_k,
                           vector_store=vs, embedder=emb, rerank=reranker)
```

`backend/app/services/prep_generator.py` —— `_EXAM_PROMPT` 之后加 prompt，`generate_exercises` 之后加生成函数：

```python
_KB_EXERCISES_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请**仅依据**下列知识库资料出题，"
    "不要编造资料中没有的知识。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "覆盖知识点：{knowledge_points}\n题目数量：{count} 道\n难度：{difficulty}\n"
    "【知识库资料】\n{kb_material}\n"
    "请以 JSON 格式输出，键为中文：习题（列表，每项含 题干/选项（4 个选项的列表，"
    "如 [\"A.选项甲\", \"B.选项乙\", \"C.选项丙\", \"D.选项丁\"]；每道题的选项必须针对"
    "本题题干设计，禁止各题共用或照抄示例选项）/"
    "答案（如 \"A\"）/解析/知识点/难度（易/中/难））。题型为选择题。不要输出其他内容。"
)


def generate_kb_exercises(course_name, subject, chapter, knowledge_points, count,
                          difficulty, kb_material, llm=None) -> dict:
    """从知识库资料生成习题：{习题[{题干, 选项[], 答案, 解析, 知识点, 难度}]}。

    difficulty 为 易/中/难 时按该难度出题；空串 = 易中难混合。
    """
    diff_text = difficulty if difficulty in ("易", "中", "难") else "易中难混合"
    prompt = _KB_EXERCISES_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        knowledge_points="、".join(knowledge_points), count=count,
        difficulty=diff_text, kb_material=kb_material,
    )
    return _call_json(prompt, temperature=0.3, llm=llm)
```

`backend/app/api/prep.py` ——（1）services import 行改为 `from ..services import kb_service, prep_export, prep_generator, prep_resources`；（2）GenerateIn 加 `difficulty: str = ""`；（3）generate 端点重排（kb_exercises 分支先于 `_collect_resources`，因为其 query 是知识库检索词而非校本资源检索词），并在文件内加 `_generate_kb_exercises`（放在 `_collect_resources` 之后）：

```python
def _generate_kb_exercises(course: Course, data: GenerateIn, user: User, db: Session) -> dict:
    """知识库出题（三通道②）：知识库混合检索 → LLM 仅依据资料出题 → 校验 → 追加进课程习题集。

    检索空手 → BizError 404；LLM/校验失败由上层统一转 502。生成即入学习题库。
    重复生成时同题干题目跳过（幂等追加）。
    """
    search_q = data.query.strip() or "、".join(data.knowledge_points) or course.name
    try:
        hits = kb_service.retrieve_chunks(user, search_q, db, top_k=8)
    except EmbedderError as exc:
        raise BizError(502, str(exc)) from exc
    if not hits:
        raise BizError(404, "知识库中未检索到该课程相关资料，请先上传文档")
    material = "\n".join(f"【{h.chunk.source}】\n{h.chunk.text[:600]}" for h in hits)
    content = prep_generator.generate_kb_exercises(
        course.name, course.subject, data.chapter, data.knowledge_points,
        data.count, data.difficulty, material)
    prep_generator.validate_exercises(content)
    title = f"{course.name}知识库生成习题"
    lesson = (db.query(Lesson).filter(Lesson.course_id == course.id,
                                      Lesson.title == title).first())
    existing = (lesson.content_json or {}).get("习题", []) if lesson is not None else []
    stems = {q.get("题干") for q in existing}
    added = [q for q in content["习题"] if q.get("题干") not in stems]
    if lesson is None:
        lesson = Lesson(course_id=course.id, title=title, lesson_type="exercises",
                        content_json={"习题": added}, created_by=user.id)
        db.add(lesson)
        db.flush()
        _snapshot(lesson, user, db)
    elif added:
        lesson.version += 1
        lesson.content_json = {"习题": existing + added}
        _snapshot(lesson, user, db)
    db.commit()
    db.refresh(lesson)
    return {"content": content,
            "lesson": {"lesson_id": lesson.id, "title": title,
                       "added": len(added), "total": len(existing) + len(added)}}
```

generate 端点改为：

```python
@router.post("/courses/{course_id}/generate")
def generate(course_id: int, data: GenerateIn,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    course = _get_course(course_id, user, db)
    try:
        if data.type == "kb_exercises":
            saved = _generate_kb_exercises(course, data, user, db)
            return {"type": data.type, "content": saved["content"], "lesson": saved["lesson"]}
        resources, citations = _collect_resources(course_id, data.query, db)
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
            raise BizError(400, "不支持的生成类型（plan/cw/exercises/case/exam/kb_exercises）")
    except LLMError as exc:
        # DeepSeek key 未配置/调用失败 → 友好 502（评审修复：原先落通用 500）
        raise BizError(502, str(exc)) from exc
    return {"type": data.type, "content": content, "citations": citations}
```

`frontend/src/views/prep/PrepCourseView.vue` —— 五处改动：

（1）生成类型 radio 加按钮（在 `<el-radio-button value="exercises">习题</el-radio-button>` 之后）：

```html
                <el-radio-button value="kb_exercises">知识库出题</el-radio-button>
```

（2）知识点表单项 v-if 扩展 + 新增难度/题数（替换现有知识点表单项）：

```html
            <el-form-item v-if="genForm.type === 'exercises' || genForm.type === 'kb_exercises'" label="知识点">
              <el-input v-model="genForm.knowledgePoints" placeholder="用、分隔：线性表、栈与队列" />
            </el-form-item>
            <el-form-item v-if="genForm.type === 'kb_exercises'" label="难度">
              <el-select v-model="genForm.difficulty" style="width: 220px">
                <el-option label="易中难混合" value="" />
                <el-option label="易" value="易" />
                <el-option label="中" value="中" />
                <el-option label="难" value="难" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="genForm.type === 'kb_exercises'" label="题数">
              <el-input-number v-model="genForm.count" :min="1" :max="20" />
            </el-form-item>
```

（3）引用资源项 label/placeholder 动态化（替换现有引用资源项）：

```html
            <el-form-item :label="genForm.type === 'kb_exercises' ? '检索知识库' : '引用资源'">
              <el-input v-model="genForm.query" :placeholder="genForm.type === 'kb_exercises'
                ? '检索知识库关键词，留空按知识点或课程名检索' : '留空不检索；填写关键词将检索校本资源并标注引用'" />
            </el-form-item>
```

（4）生成按钮文案动态化（替换现有生成按钮）：

```html
          <el-button type="primary" :loading="generating" @click="onGenerate">
            <el-icon class="btn-ico"><MagicStick /></el-icon>{{ genForm.type === 'kb_exercises' ? '生成并进入学习题库' : '生成初稿' }}
          </el-button>
```

（5）保存区仅非 kb_exercises 显示（替换 `<div class="result-save">` 为）：

```html
            <div v-if="result.type !== 'kb_exercises'" class="result-save">
```

script 中：（1）genForm 加字段：

```ts
const genForm = reactive({ type: 'plan', chapter: '', objectives: '', hours: '', knowledgePoints: '', distribution: '', query: '', difficulty: '', count: 10 })
```

（2）onGenerate 替换为：

```ts
async function onGenerate() {
  generating.value = true
  try {
    const payload: any = {
      type: genForm.type, chapter: genForm.chapter, objectives: genForm.objectives,
      hours: genForm.hours, query: genForm.query,
    }
    if (genForm.type === 'exercises' || genForm.type === 'kb_exercises') {
      payload.knowledge_points = genForm.knowledgePoints.split(/[、,，]/).filter(Boolean)
    }
    if (genForm.type === 'exam' && genForm.distribution.trim()) {
      payload.distribution = genForm.distribution.split('\n').filter(Boolean).map((line) => {
        const [kp, pct] = line.split(/[:：]/)
        return { '知识点': kp.trim(), '占比': (pct || '').trim() }
      })
    }
    if (genForm.type === 'kb_exercises') {
      payload.difficulty = genForm.difficulty
      payload.count = genForm.count
    }
    result.value = await generateContent(courseId, payload)
    if (genForm.type === 'kb_exercises') {
      const saved = result.value.lesson
      ElMessage.success(`已生成并进入学习题库：新增 ${saved.added} 题，共 ${saved.total} 题`)
      await load()
    } else {
      lessonTitle.value = result.value.content['标题'] || result.value.content['试卷标题'] || '未命名'
    }
  } finally { generating.value = false }
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_prep_kb_exercises.py tests/test_prep_api.py tests/test_prep_generator.py -v`
Expected: 全 PASS（既有备课用例不破）。
前端：`cd frontend && npm run build && npx tsc --noEmit` → 无错误。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/kb_service.py backend/app/services/prep_generator.py backend/app/api/prep.py backend/tests/test_prep_kb_exercises.py frontend/src/views/prep/PrepCourseView.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(prep): 知识库出题服务+备课入口（检索→LLM→校验→入学习题库）（Plan G Task 5）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: LearnView 学习方向切换（前端方向贯穿）

**Files:**
- Modify: `frontend/src/api/learn.ts`
- Modify: `frontend/src/views/learn/LearnView.vue`

**Interfaces:**
- Consumes: Task 1 的 `course_id`/`prev_stem` 接口参数；Task 2~4 的三个方向题库（经 `/api/learn/courses` 列表）。
- Produces: 前端全量方向贯穿（诊断/仪表盘/练习/错题本/导入联动当前方向）。

- [ ] **Step 1: api/learn.ts 加参数**

把以下函数签名替换为（其余接口不变）：

```ts
export const getProfile = (courseId?: number) =>
  http.get('/learn/profile', { params: { course_id: courseId } }) as Promise<ProfileData>
export const getDiagnostic = (courseId?: number) =>
  http.get('/learn/diagnostic', { params: { course_id: courseId } }) as Promise<{ questions: Question[]; count: number }>
export const getPath = (courseId?: number) =>
  http.get('/learn/path', { params: { course_id: courseId } }) as Promise<{ path: PathItem[]; mastered: number; unmastered: number }>
export const getTasks = (courseId?: number) =>
  http.get('/learn/tasks', { params: { course_id: courseId } }) as Promise<TaskItem[]>
export const getPractice = (kp: string, courseId?: number, prevStem?: string) =>
  http.get('/learn/practice', { params: { kp, course_id: courseId, prev_stem: prevStem } }) as Promise<Question>
export const listWrongbook = (courseId?: number) =>
  http.get('/learn/wrongbook', { params: { course_id: courseId } }) as Promise<WrongQuestionItem[]>
```

- [ ] **Step 2: 构建验证当前状态（基线）**

Run: `cd frontend && npm run build && npx tsc --noEmit` → 记录通过（此时 LearnView 仍无方向选择器，作为改动前基线）。

- [ ] **Step 3: LearnView.vue 改造**

（1）template 最外层 `<div>` 内顶部（未初始化卡片之前）加方向选择器与空态：

```html
    <!-- 学习方向切换（Plan G：三方向联动全部面板） -->
    <div v-if="learnCourses.length" class="direction-bar">
      <span class="direction-label">学习方向</span>
      <el-select v-model="currentCourseId" style="width: 240px" @change="onSwitchDirection">
        <el-option v-for="c in learnCourses" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
    </div>
    <el-card v-if="!learnCourses.length">
      <el-empty description="暂无学习方向（需教师先在备课模块创建含习题的课程）" />
    </el-card>

    <!-- 未初始化画像：引导 -->
    <el-card v-if="learnCourses.length && profile && !profile.initialized">
      <el-empty description="还没有该方向的学习画像，先完成诊断测试或导入历史成绩">
        <el-button type="primary" @click="startDiagnostic">开始诊断测试</el-button>
        <el-button @click="openImport">导入历史成绩</el-button>
      </el-empty>
    </el-card>
```

（2）script 加状态：

```ts
const learnCourses = ref<{ id: number; name: string }[]>([])
const currentCourseId = ref<number | null>(null)
const lastStem = ref('')
```

（3）替换 loadDashboard / loadWrongbook / startDiagnostic / onNextQuestion / onMounted，新增 onSwitchDirection / openImport：

```ts
async function loadDashboard() {
  profile.value = await getProfile(currentCourseId.value ?? undefined)
  if (!profile.value.initialized) return
  const [p, t, s] = await Promise.all([
    getPath(currentCourseId.value ?? undefined),
    getTasks(currentCourseId.value ?? undefined),
    getSimilar(),
  ])
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
  wrongbook.value = await listWrongbook(currentCourseId.value ?? undefined)
}

async function startDiagnostic() {
  try {
    const data = await getDiagnostic(currentCourseId.value ?? undefined)
    diagQuestions.value = data.questions
    diagnosing.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '暂无可用试题，请先由教师在智能备课模块生成习题')
  }
}

async function onSwitchDirection() {
  // 切换方向重置全部面板状态（诊断/练习/结果），避免跨方向残留
  diagnosing.value = false
  diagQuestions.value = []
  currentQuestion.value = null
  result.value = null
  selectedAnswer.value = ''
  practiceKp.value = ''
  lastStem.value = ''
  await loadDashboard()
  await loadWrongbook()
}

function openImport() {
  importForm.course_id = currentCourseId.value ?? undefined
  importVisible.value = true
}

async function onNextQuestion() {
  if (!practiceKp.value) { ElMessage.warning('请先选择知识点'); return }
  loadingQuestion.value = true
  result.value = null
  selectedAnswer.value = ''
  try {
    currentQuestion.value = await getPractice(
      practiceKp.value, currentCourseId.value ?? undefined, lastStem.value || undefined)
    if (currentQuestion.value) lastStem.value = currentQuestion.value.stem
  } catch (e) {
    currentQuestion.value = null
  } finally {
    loadingQuestion.value = false
  }
}

onMounted(async () => {
  learnCourses.value = await listLearnCourses()
  if (learnCourses.value.length) {
    currentCourseId.value = learnCourses.value[0].id
    await loadDashboard()
    await loadWrongbook()
  }
})
```

（4）样式追加：

```css
.direction-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.direction-label { font-size: 14px; font-weight: 600; color: var(--text-1); }
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build && npx tsc --noEmit` → 无错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api/learn.ts frontend/src/views/learn/LearnView.vue
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "feat(learn-ui): 学习方向切换联动画像/诊断/练习/错题本+prev_stem 防重复（Plan G Task 6）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 文档收尾 + 全量回归 + 本机升级与启动

**Files:**
- Modify: `README.md`（个性化学习小节 + 质量基线数字）
- Modify: `docs/工单19-个性化学习-测试用例与结果.md`（追加 Plan G 用例清单与彩排清单）

**Interfaces:**
- Consumes: 全部任务的最终产物；本机 8002 后端进程（需重启）。

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && python -m pytest -q > out_full.txt 2>&1`
Expected: FAILED = 0；PASSED = 295（基线）+ 新增（Task 1×8 + Task 2×4 + Task 3×3 + Task 4×2 + Task 5×5 ≈ 317，以实际输出为准，**逐条数 PASSED 并记录真实数字**）。

- [ ] **Step 2: 前端全量验证**

Run: `cd frontend && npm run build && npx tsc --noEmit` → 无错误。

- [ ] **Step 3: 本机旧库升级 + 重启服务**

1. 停掉 8002 后端：`netstat -ano | findstr :8002` 找到 PID → `taskkill /F /PID <pid>`。
2. 迁移+播种：`cd backend && python -m scripts.seed_demo_data`。预期输出：学习方向 3 行（各 12 知识点/前置/72 题）+ 公共库演示文档（AI PDF 已存在跳过、DS/ML .md 各入库）。
3. 重启后端（沿用既有 PowerShell Start-Process 分离启动方式，端口 8002）。
4. 前端 5173 热更新（dev server 仍在跑则自动生效；否则 `npm run dev`）。

- [ ] **Step 4: 文档更新**

README：
- 「个性化学习」小节改为：3 个学习方向（人工智能导论 / 数据结构与算法 / 机器学习，顶部选择器切换）；每方向 12 知识点图谱 + 72 道种子题（易2/中2/难2）；题目三通道：老师生成习题/月考题自动入池、备课「知识库出题」从知识库生成习题直接入池、手工种子 216 题保底；练习下一题自动避开上一题（prev_stem）；错题本/诊断/画像按方向独立。
- 「智能备课」小节补一句：生成类型新增「知识库出题」——检索公共库+私有库资料、仅依据资料出题、自动进入该课程学习题库。
- 质量基线数字改为 Step 1 实测的 PASSED 数（deselected 2）。

`docs/工单19-个性化学习-测试用例与结果.md` 末尾追加小节：

```markdown
## Plan G 多学习方向扩展（2026-09-22）

新增用例（后端共 N 条）：
- test_learn_migration.py：知识点同名跨课程共存、旧库迁移（加列/回填/索引重建/幂等）
- 画像/图谱/练习/API 追加：方向画像隔离、路径课程内拓扑、prev_stem 防重复、错题本按课程过滤、诊断按课程 404
- test_seed_learn_bank.py：3 方向各 72 题、每知识点每难度 2 题、题干方向内唯一、选项 4 个带字母、幂等落库、同名知识点跨课程共存、知识文档覆盖全部知识点
- test_prep_kb_exercises.py：知识库出题 prompt/温度、结构校验 502、生成即入学习题库（去重追加）、检索空手 404、LLM 失败 502
- test_learn_practice.py：月考题选择题自动入练习池（三通道①链路钉住）

彩排清单（用户浏览器验收）：
1. 学生登录 → 个性化学习顶部出现「学习方向」选择器（3 个方向，默认第一个）
2. 切换到「数据结构与算法」→ 提示先做该方向诊断测试 → 诊断 10 题（覆盖多知识点、无答案）
3. 提交诊断 → 雷达图 12 维、推荐路径按拓扑序、今日任务带该方向题
4. 自适应练习：连续「下一题」不重复上一题（prev_stem）；答错进错题本（按方向过滤）
5. 切换方向再切回 → 各方向画像独立（AI 方向旧画像不丢，新方向需重新初始化）
6. 教师登录 → 备课「数据结构与算法」→ 生成类型选「知识库出题」→ 题数/难度 → 提示"已生成并进入学习题库"
7. 学生端该方向练习可选到知识库生成的新题
```

- [ ] **Step 5: 提交**

```bash
git add README.md "docs/工单19-个性化学习-测试用例与结果.md"
git -c user.name="huqiaoyu" -c user.email="huqiaoyu@local" commit -m "docs: Plan G 多方向学习文档与质量基线更新

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 6: 用户彩排交接**

向用户交付：访问地址（前端 5173，学生账号 student/student123、教师 teacher/teacher123）、彩排清单（见 Step 4 文档）、已知注意点（真实 DeepSeek key 在 backend/.env 才可演示知识库出题与 AI 解析；bge-m3 首次加载较慢）。
