# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-个性化学习推荐任务(19)
"""AIGC 错题本服务：答错登记 + DeepSeek 生成（解析/错误原因/变式题）。

口径：答题提交时同步生成；LLM 失败错题保留（status=failed），接口正常返回，
前端错题本提供"重新生成"按钮。prompt 结构按验收要求：原题干+错误答案+正确答案+
知识点+常见错误类型 → 解析 + 错误原因 + 2~3 道变式题。
"""
import logging

from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.learn import WrongQuestion
from ..models.user import User
from .llm_gateway import LLMGateway, LLMError, get_gateway

logger = logging.getLogger("learn_wrongbook")

_WRONG_ANALYSIS_PROMPT = (
    "你是高职院校人工智能课程的辅导教师。学生做错了下面这道题，请帮助其掌握该知识点。\n"
    "原题干：{stem}\n选项：{options}\n学生答案：{user_answer}\n正确答案：{correct_answer}\n"
    "知识点：{knowledge_point}\n难度：{difficulty}\n"
    "请以 JSON 格式输出，键为中文："
    "解析（字符串，讲清解题思路）、错误原因（字符串，分析学生常见错误类型）、"
    "变式题（列表，2~3 道，每项含 题干/选项（列表，如 [\"A.学习率\", ...]）/答案（如 \"A\"）/解析）。"
    "变式题围绕同一知识点、不同角度，难度相近。不要输出其他内容。"
)


def _options_text(options: list) -> str:
    return "；".join(str(o) for o in (options or []))


def generate_analysis(wq: WrongQuestion, llm: LLMGateway | None = None) -> dict:
    """DeepSeek 生成错题解析：{解析, 错误原因, 变式题[2~3]}。结构不完整抛 BizError。"""
    gateway = llm or get_gateway()
    prompt = _WRONG_ANALYSIS_PROMPT.format(
        stem=wq.stem, options=_options_text(wq.options), user_answer=wq.user_answer,
        correct_answer=wq.correct_answer, knowledge_point=wq.knowledge_point,
        difficulty=wq.difficulty,
    )
    data = gateway.chat_json(
        [{"role": "system", "content": "你是教育错题辅导助手，只输出合法 JSON。"},
         {"role": "user", "content": prompt}],
        temperature=0.3,
    )
    for key in ("解析", "错误原因", "变式题"):
        if key not in data:
            raise BizError(502, f"错题解析生成结果缺少字段：{key}，请重试")
    if not isinstance(data["变式题"], list) or len(data["变式题"]) < 2:
        raise BizError(502, "错题解析生成的变式题不足 2 道，请重试")
    return data


def add_wrong_question(user: User, *, stem: str, options: list, user_answer: str,
                       correct_answer: str, knowledge_point: str, difficulty: str,
                       db: Session, llm: LLMGateway | None = None) -> WrongQuestion:
    """登记错题并同步生成 AI 解析；LLM 失败错题保留（status=failed），不抛异常。"""
    wq = WrongQuestion(user_id=user.id, stem=stem, options=options, user_answer=user_answer,
                       correct_answer=correct_answer, knowledge_point=knowledge_point,
                       difficulty=difficulty, status="pending")
    db.add(wq)
    db.flush()
    try:
        data = generate_analysis(wq, llm)
        wq.analysis = data["解析"]
        wq.error_reason = data["错误原因"]
        wq.variants = data["变式题"][:3]
        wq.status = "generated"
    except (LLMError, BizError) as exc:
        logger.warning("错题 AI 解析生成失败：%s（错题已保留）", exc)
        wq.status = "failed"
    db.commit()
    db.refresh(wq)
    return wq


def list_wrongbook(user: User, db: Session) -> list[WrongQuestion]:
    """本人错题本（倒序）。"""
    return (db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
            .order_by(WrongQuestion.id.desc()).all())


def regenerate(user: User, wq_id: int, db: Session, llm: LLMGateway | None = None) -> WrongQuestion:
    """重新生成解析（仅本人）。LLM 失败保持 failed 不抛异常（前端提示重试）。"""
    wq = db.get(WrongQuestion, wq_id)
    if wq is None or wq.user_id != user.id:
        raise BizError(404, "错题不存在")
    try:
        data = generate_analysis(wq, llm)
        wq.analysis = data["解析"]
        wq.error_reason = data["错误原因"]
        wq.variants = data["变式题"][:3]
        wq.status = "generated"
    except (LLMError, BizError) as exc:
        logger.warning("错题重新生成失败：%s", exc)
        wq.status = "failed"
    db.commit()
    db.refresh(wq)
    return wq
