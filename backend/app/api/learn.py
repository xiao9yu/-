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


@router.get("/similar")
def similar(user: User = Depends(_student), course_id: int | None = Query(None),
            db: Session = Depends(get_db)):
    return learn_profile.similar_students(user, db, course_id=course_id)


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
    return learn_profile.init_from_diagnostic(user, stats, db)


@router.post("/import")
def import_score(data: ImportIn, user: User = Depends(_student), db: Session = Depends(get_db)):
    if not (0 <= data.score <= 100):
        raise BizError(400, "成绩需在 0~100 之间")
    kps = {q.get("知识点") for q in learn_practice.collect_questions(db, course_id=data.course_id)
           if q.get("知识点")}
    if not kps:
        raise BizError(400, "该课程暂无试题，无法初始化画像")
    return learn_profile.init_from_import(user, sorted(kps), data.score, db,
                                          course_id=data.course_id)


# ---------- 自适应练习 ----------


@router.get("/practice")
def practice(kp: str = Query(...), course_id: int | None = None,
             prev_stem: str | None = None,
             user: User = Depends(_student), db: Session = Depends(get_db)):
    if not kp.strip():
        raise BizError(400, "知识点不能为空")
    return learn_practice.next_question(user, kp.strip(), db,
                                        course_id=course_id, prev_stem=prev_stem)


@router.post("/practice/submit")
def practice_submit(data: SubmitIn, user: User = Depends(_student), db: Session = Depends(get_db)):
    if not data.answer.strip():
        raise BizError(400, "请先作答")
    return learn_practice.submit_answer(user, data.lesson_id, data.stem, data.answer, db)


# ---------- 错题本 ----------


@router.get("/wrongbook")
def wrongbook(course_id: int | None = None, user: User = Depends(_student),
              db: Session = Depends(get_db)):
    return [{"id": w.id, "stem": w.stem, "options": w.options, "user_answer": w.user_answer,
             "correct_answer": w.correct_answer, "knowledge_point": w.knowledge_point,
             "difficulty": w.difficulty, "analysis": w.analysis, "error_reason": w.error_reason,
             "variants": w.variants, "status": w.status, "created_at": w.created_at.isoformat()}
            for w in learn_wrongbook.list_wrongbook(user, db, course_id=course_id)]


@router.post("/wrongbook/{wq_id}/regenerate")
def wrongbook_regenerate(wq_id: int, user: User = Depends(_student), db: Session = Depends(get_db)):
    w = learn_wrongbook.regenerate(user, wq_id, db)
    return {"id": w.id, "analysis": w.analysis, "error_reason": w.error_reason,
            "variants": w.variants, "status": w.status}
