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
import re

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
_OPTION_LETTER = re.compile(r"^([A-Za-z])[.、．:：)）]")


def _lesson_items(lesson: Lesson) -> list[dict]:
    """提取 lesson 内的题目列表：习题集取"习题"，月考题展开"大题"下的"题目"。

    （评审修复：抽题与定位共用同一提取逻辑，避免两处逐字重复漂移——
    serve/submit 口径不一致会让答对的题被判"试题不存在"。）
    """
    content = lesson.content_json or {}
    if lesson.lesson_type == "exercises":
        return content.get("习题", [])
    return [q for s in content.get("大题", []) for q in s.get("题目", [])]


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
        for q in _lesson_items(lesson):
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
    for q in _lesson_items(lesson):
        if isinstance(q, dict) and q.get("题干") == stem:
            return q
    raise BizError(404, "试题不存在（可能已被修改，请重新获取练习题）")


def check_answer(q: dict, answer: str | None) -> bool:
    """判定学生答案：接受裸字母（如 "A"）或完整选项文本（如 "A.学习率"）。

    前端单选绑定整段选项文本；后端按选项前缀字母归一化比对（防作弊仍在后端）。
    空答案一律判错（防御性，路由层已拦截空提交）。
    """
    given = (answer or "").strip().upper()
    expected = str(q.get("答案", "")).strip().upper()
    if given == expected:
        return True
    for opt in q.get("选项", []) or []:
        text = str(opt).strip()
        m = _OPTION_LETTER.match(text)
        if m and m.group(1).upper() == expected and text.upper() == given:
            return True
    return False


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
    # 输出英文字段（Task 6 API 与前端 Question 结构契约）；答案/解析一律剔除（防前端作弊）
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


def submit_answer(user: User, lesson_id: int, stem: str, answer: str,
                  db: Session, llm: LLMGateway | None = None) -> dict:
    """提交练习答案：后端比对 → 画像事件（对 +10/错 -15）→ 难度调整 → 错题入册+AI 解析。"""
    q = find_question(db, lesson_id, stem)
    correct = check_answer(q, answer)
    kp_name = q.get("知识点") or "未分类知识点"
    lesson = db.get(Lesson, lesson_id)
    kp = learn_profile.get_or_create_kp(db, kp_name,
                                        lesson.course_id if lesson is not None else None)
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
