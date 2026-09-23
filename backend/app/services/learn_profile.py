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


def record_ask_events(user: User, question: str, db: Session) -> int:
    """助教提问画像联动：问题包含知识点名 → 记 +2 低权重事件（关注度激励）。"""
    hits = [kp for kp in db.query(KnowledgePoint).all() if kp.name in question]
    for kp in hits:
        apply_event(user, kp, DELTA_ASK, db, event_type="ask", detail=question[:200])
    if hits:
        db.commit()
    return len(hits)


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
