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
from app.models.learn import KnowledgePoint, KpPrereq
from app.models.prep import Course, CourseFile, Lesson
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
    """公共库演示文档：生成 PDF（文本+表格）→ 解析 → 向量化入公共库。幂等：已有 ready 公共文档则跳过。"""
    from app.models.kb import KbDocument
    exists = db.query(KbDocument).filter(KbDocument.scope == "public",
                                         KbDocument.status == "ready").first()
    if exists:
        print("公共库已有演示文档，跳过")
        return
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        print("admin 不存在，跳过公共库演示数据")
        return
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


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed_users(db)
        make_demo_files()
        seed_prep_demo(db)
        seed_kb_demo(db)
        seed_learn_demo(db)
        print("演示账号：admin/admin123(管理员) teacher/teacher123(教师) student/student123(学生) counselor/counselor123(就业指导)")
    finally:
        db.close()
