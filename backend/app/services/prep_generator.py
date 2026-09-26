# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课生成服务：DeepSeek JSON 结构化生成教案/课件大纲/习题/案例/月考试题。
各生成函数统一签名：课程信息 + 教学参数 + 可选校本资源上下文（RAG 检索结果）→ 结构化 dict。
"""
from .llm_gateway import get_gateway
from ..core.exceptions import BizError

_LESSON_PLAN_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成一份详细教案。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n课时：{hours}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题、教学目标（列表）、教学重点（列表）、教学难点（列表）、"
    "教学过程（列表，每项含 环节/内容/时长）、作业（字符串）、板书设计（字符串）。不要输出其他内容。"
)

_COURSEWARE_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成课件大纲。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n课时：{hours}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题（字符串）、幻灯片（列表，每项含 标题/要点（字符串列表）/"
    "讲稿（字符串，该页的口语化串讲：面向学生讲课的口吻，每页 2~4 句，开场页可含欢迎语，"
    "不照念要点原文，不用 markdown 与引用编号），10~15 页）。不要输出其他内容。"
)

_EXERCISES_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请根据以下信息生成练习题。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "覆盖知识点：{knowledge_points}\n题目数量：{count} 道\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：习题（列表，每项含 题干/选项（4 个选项的列表，"
    "如 [\"A.选项甲\", \"B.选项乙\", \"C.选项丙\", \"D.选项丁\"]；每道题的选项必须针对"
    "本题题干设计，禁止各题共用或照抄示例选项）/"
    "答案（如 \"A\"）/解析/知识点/难度（易/中/难））。题型为选择题。不要输出其他内容。"
)

_EXAM_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请根据以下知识点分布生成一份月考试卷。\n"
    "课程名称：{course_name}\n学科：{subject}\n"
    "知识点分布（知识点：占比）：\n{distribution}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：试卷标题（字符串）、大题（列表，每项含 题型/知识点/"
    "题目（列表，每项含 题干/选项/答案/解析/知识点/难度））。"
    "题型至少包含选择题与简答题；题目总数为 10 道左右，按占比分配。不要输出其他内容。"
)

_KB_EXERCISES_PROMPT = (
    "你是高职院校人工智能课程的命题教师。请**仅依据**下列知识库资料出题，"
    "不要编造资料中没有的知识。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "覆盖知识点（每道题的\"知识点\"字段必须从下列清单中原样选取一个，"
    "不得改写或自创）：{knowledge_points}\n题目数量：{count} 道\n难度：{difficulty}\n"
    "【知识库资料】\n{kb_material}\n"
    "请以 JSON 格式输出，键为中文：习题（列表，每项含 题干/选项（4 个选项的列表，"
    "如 [\"A.选项甲\", \"B.选项乙\", \"C.选项丙\", \"D.选项丁\"]；每道题的选项必须针对"
    "本题题干设计，禁止各题共用或照抄示例选项）/"
    "答案（如 \"A\"）/解析/知识点/难度（易/中/难））。题型为选择题。不要输出其他内容。"
)

_CASE_PROMPT = (
    "你是高职院校人工智能课程的资深教师。请根据以下课程信息生成一个教学案例。\n"
    "课程名称：{course_name}\n学科：{subject}\n章节：{chapter}\n"
    "教学目标：{objectives}\n"
    "{resources_section}"
    "请以 JSON 格式输出，键为中文：标题（字符串）、案例背景（字符串）、案例描述（字符串）、"
    "问题（字符串）、案例分析（字符串）、结论（字符串）。不要输出其他内容。"
)


def _resources_section(resources: str) -> str:
    """校本资源上下文：无资源时给空段，有资源时拼入提示词。"""
    if not resources:
        return ""
    return f"【校本参考资料】\n{resources}\n回答内容应参考上述资料。\n"


def _call_json(prompt: str, temperature: float, llm) -> dict:
    chat = llm or get_gateway()
    messages = [
        {"role": "system", "content": "你是教育智能备课助手，只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    data = chat.chat_json(messages, temperature=temperature)
    if not isinstance(data, dict):
        raise BizError(502, "生成结果格式异常，请重试")
    return data


def _require_keys(data: dict, keys: list[str]) -> None:
    """结构校验：缺必需键抛业务异常（LLM 输出不完整时给出友好提示）。"""
    missing = [k for k in keys if k not in data]
    if missing:
        raise BizError(502, f"生成结果缺少字段：{'、'.join(missing)}，请重试")


def generate_lesson_plan(course_name, subject, chapter, objectives, hours,
                         resources="", llm=None) -> dict:
    """生成教案：{标题, 教学目标[], 教学重点[], 教学难点[], 教学过程[], 作业, 板书设计}。"""
    prompt = _LESSON_PLAN_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, hours=hours, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def generate_courseware(course_name, subject, chapter, objectives, hours,
                        resources="", llm=None) -> dict:
    """生成课件大纲：{标题, 幻灯片[{标题, 要点[]}]}。"""
    prompt = _COURSEWARE_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, hours=hours, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def generate_exercises(course_name, subject, chapter, knowledge_points, count,
                       resources="", llm=None) -> dict:
    """生成习题集：{习题[{题干, 选项[], 答案, 解析, 知识点, 难度}]}（工单19 复用结构）。"""
    prompt = _EXERCISES_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        knowledge_points="、".join(knowledge_points), count=count,
        resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.3, llm=llm)


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


def generate_monthly_exam(course_name, subject, distribution, resources="", llm=None) -> dict:
    """生成月考试卷：{试卷标题, 大题[{题型, 知识点, 题目[]}]}。distribution 为 [{知识点, 占比}]。"""
    dist_text = "\n".join(f"- {d['知识点']}：{d['占比']}" for d in distribution)
    prompt = _EXAM_PROMPT.format(
        course_name=course_name, subject=subject, distribution=dist_text,
        resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.3, llm=llm)


def generate_case(course_name, subject, chapter, objectives, resources="", llm=None) -> dict:
    """生成教学案例：{标题, 案例背景, 案例描述, 问题, 案例分析, 结论}。"""
    prompt = _CASE_PROMPT.format(
        course_name=course_name, subject=subject, chapter=chapter,
        objectives=objectives, resources_section=_resources_section(resources),
    )
    return _call_json(prompt, temperature=0.7, llm=llm)


def validate_lesson_plan(data: dict) -> None:
    _require_keys(data, ["标题", "教学目标", "教学重点", "教学难点", "教学过程", "作业", "板书设计"])


def validate_courseware(data: dict) -> None:
    _require_keys(data, ["标题", "幻灯片"])
    if not isinstance(data["幻灯片"], list) or not data["幻灯片"]:
        raise BizError(502, "生成结果缺少幻灯片内容，请重试")
    for slide in data["幻灯片"]:
        _require_keys(slide, ["标题", "要点", "讲稿"])
        if not isinstance(slide["讲稿"], str) or not slide["讲稿"].strip():
            raise BizError(502, "生成结果缺少讲稿，请重试")


def validate_exercises(data: dict) -> None:
    _require_keys(data, ["习题"])
    if not isinstance(data["习题"], list) or not data["习题"]:
        raise BizError(502, "生成结果缺少习题，请重试")
    for ex in data["习题"]:
        _require_keys(ex, ["题干", "选项", "答案", "解析", "知识点", "难度"])


def validate_exam(data: dict) -> None:
    _require_keys(data, ["试卷标题", "大题"])
    if not isinstance(data["大题"], list) or not data["大题"]:
        raise BizError(502, "生成结果缺少大题，请重试")
    for section in data["大题"]:
        _require_keys(section, ["题型", "知识点", "题目"])


def validate_case(data: dict) -> None:
    _require_keys(data, ["标题", "案例背景", "案例描述", "问题", "案例分析", "结论"])
