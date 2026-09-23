# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""演示数据脚本：预置 4 类角色账号 + 人工智能课程样例文档。
用法：cd backend && python -m scripts.seed_demo_data
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pymupdf import open as open_pdf

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models.file import FileRecord
from app.models.prep import Course, CourseFile
from app.models.user import Role, User
from app.services.file_service import save_upload

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"

USERS = [
    ("admin", "admin123", Role.admin, "管理员"),
    ("teacher", "teacher123", Role.teacher, "王老师"),
    ("student", "student123", Role.student, "李同学"),
    ("counselor", "counselor123", Role.counselor, "张指导"),
]


def seed_users(db) -> None:
    for username, pwd, role, name in USERS:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(username=username, hashed_password=hash_password(pwd), role=role, real_name=name))
    db.commit()


# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
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


def _build_kb_demo_pdf(path):
    """3 页演示 PDF：第 1 页文本（梯度下降）、第 2 页表格（优化器对比）、第 3 页文本（反向传播）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    def _register_font():
        # 与 make_demo_files 相同策略：Windows 用 simhei.ttf，否则 STSong-Light
        try:
            pdfmetrics.registerFont(TTFont("demo", r"C:\Windows\Fonts\simhei.ttf"))
        except Exception:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            return "STSong-Light"
        return "demo"

    font = _register_font()
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    def draw_text_page(lines):
        y = h - 80
        c.setFont(font, 14)
        for line in lines:
            c.drawString(60, y, line)
            y -= 30

    draw_text_page([
        "人工智能导论知识库",
        "一、梯度下降：机器学习最常用的优化算法。",
        "核心思想：沿损失函数梯度反方向迭代更新参数，使损失逐步减小。",
        "学习率控制每步更新幅度：过大会震荡发散，过小则收敛缓慢。",
    ])
    c.showPage()
    c.setFont(font, 14)
    c.drawString(60, h - 80, "二、常见优化器对比")
    rows = [["优化器", "特点"], ["SGD", "每次用单样本梯度，收敛慢"], ["Adam", "自适应学习率，收敛快且稳定"]]
    x0, y0, cell_w, cell_h = 60, h - 140, 240, 30
    c.setFont(font, 12)
    for r, row in enumerate(rows):
        for col, cell in enumerate(row):
            c.rect(x0 + col * cell_w, y0 - r * cell_h, cell_w, cell_h)
            c.drawString(x0 + col * cell_w + 8, y0 - r * cell_h + 10, cell)
    c.showPage()
    draw_text_page([
        "三、反向传播：利用链式法则逐层计算梯度，",
        "是训练深度神经网络的基础算法，与梯度下降配合完成参数更新。",
    ])
    c.save()


def make_demo_files() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    # 1) 讲义 docx
    doc = Document()
    doc.add_heading("人工智能导论讲义", level=1)
    doc.add_heading("第3章 机器学习基础", level=2)
    doc.add_paragraph("梯度下降是机器学习中最基础的优化算法。它通过沿损失函数负梯度方向迭代更新参数，逐步逼近最优解。学习率控制每次更新的步长。")
    doc.add_paragraph("线性回归通过拟合一条直线描述特征与目标值之间的关系，常用于房价预测等连续值预测场景。")
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "算法"; table.cell(0, 1).text = "适用场景"
    table.cell(1, 0).text = "线性回归"; table.cell(1, 1).text = "房价预测"
    table.cell(2, 0).text = "逻辑回归"; table.cell(2, 1).text = "二分类"
    doc.save(DEMO_DIR / "人工智能导论讲义.docx")
    # 2) 课件 pptx
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "机器学习基础"
    slide.placeholders[1].text = "主讲：王老师"
    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "梯度下降"
    slide2.placeholders[1].text = "沿负梯度方向迭代更新参数"
    prs.save(DEMO_DIR / "机器学习课件.pptx")
    # 3) 试题 xlsx
    wb = Workbook()
    ws = wb.active
    ws.append(["题干", "选项A", "选项B", "选项C", "选项D", "答案", "知识点", "难度"])
    ws.append(["梯度下降中控制步长的参数是", "学习率", "批量大小", "迭代次数", "正则系数", "A", "梯度下降", "易"])
    ws.append(["以下哪个算法适合房价预测", "线性回归", "K-means", "决策树分类", "PCA", "A", "线性回归", "易"])
    wb.save(DEMO_DIR / "诊断试题.xlsx")
    # 4) 教材 pdf
    pdf_doc = open_pdf()
    page = pdf_doc.new_page()
    page.insert_text((72, 72), "人工智能导论：机器学习基础\n梯度下降通过迭代更新参数逼近最优解。", fontname="china-s")
    pdf_doc.save(DEMO_DIR / "人工智能导论教材.pdf")
    pdf_doc.close()
    print("演示文件已生成：", DEMO_DIR)


# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
def migrate_learn_schema(db) -> None:
    """Plan G 旧库迁移（幂等）：knowledge_points 加 course_id 列 → 回填「人工智能导论」→
    移除旧 name 唯一索引、重建 (course_id, name) 唯一索引；wrong_questions 同样加
    course_id 列并回填「人工智能导论」（旧错题全部来自该课程，修复跨课程错题泄漏）。
    新库（create_all 建表）自动跳过。"""
    from sqlalchemy import inspect, text
    engine = db.get_bind()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("knowledge_points")}
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
    if inspector.has_table("wrong_questions"):
        cols_wq = {c["name"] for c in inspector.get_columns("wrong_questions")}
        if "course_id" not in cols_wq:
            db.execute(text("ALTER TABLE wrong_questions "
                            "ADD COLUMN course_id INTEGER REFERENCES courses(id)"))
            db.commit()
        db.execute(text("UPDATE wrong_questions SET course_id = "
                        "(SELECT id FROM courses WHERE name = '人工智能导论') "
                        "WHERE course_id IS NULL"))
        db.commit()


# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19 扩展：多学习方向)
def seed_learn_demo(db) -> None:
    """个性化学习演示数据（Plan G）：3 个学习方向图谱 + 216 道手工种子题。幂等。"""
    from scripts.seed_learn_bank import seed_learn_directions
    result = seed_learn_directions(db)
    for name, info in result.items():
        print(f"学习方向「{name}」：{info['kps']} 知识点 + "
              f"{info['prereqs']} 前置关系 + {info['exercises']} 题")


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        migrate_learn_schema(db)   # Plan G 旧库升级（幂等，新库自动跳过）
        seed_users(db)
        make_demo_files()
        seed_prep_demo(db)
        seed_kb_demo(db)
        seed_learn_demo(db)
        print("演示账号：admin/admin123(管理员) teacher/teacher123(教师) student/student123(学生) counselor/counselor123(就业指导)")
    finally:
        db.close()
