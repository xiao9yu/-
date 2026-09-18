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
