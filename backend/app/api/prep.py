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
