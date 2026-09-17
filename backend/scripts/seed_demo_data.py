# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""演示数据脚本：预置 4 类角色账号 + 人工智能课程样例文档。
用法：cd backend && python -m scripts.seed_demo_data
"""
import sys
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


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_users(db)
        make_demo_files()
        seed_prep_demo(db)
        print("演示账号：admin/admin123(管理员) teacher/teacher123(教师) student/student123(学生) counselor/counselor123(就业指导)")
    finally:
        db.close()
