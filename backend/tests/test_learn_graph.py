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
    s = Session()
    yield s
    s.close()  # 先关 Session 再 drop_all，避免 Windows SQLite 文件锁
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
