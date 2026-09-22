# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""多轮会话服务：会话/消息落库、上下文装载、追问检索改写。

为什么需要它：单轮问答里"那它的学习率呢"这类指代型追问，检索拿到的查询词为零信息，
必然空手；数字人也无从知道学生在追问什么，「像助教」和「像播放器」的分水岭就在这。
本模块提供三件事：
  1) 会话与消息持久化（前端刷新/WS 重连后上下文还在）；
  2) 取最近 N 轮上下文喂进提示词，让 LLM 理解指代并保持连贯；
  3) rewrite_query：检索前把指代型追问与前一轮问题拼接，解决检索空手（见下）。
"""
import logging
import re

from sqlalchemy.orm import Session

from ..models.chat import ChatMessage, ChatSession
from ..models.user import User

logger = logging.getLogger("chat_service")

HISTORY_TURNS = 3          # 喂进提示词的历史轮数（1 轮 = 1 问 + 1 答）
_SESSION_TITLE_MAX = 30

# 追问判定分两档，因为"长度"和"标记词"各有盲区（见 rewrite_query 文档）：
#   强指代——脱离上文无法确定所指，长短句命中即改写。
#   注：「这个/那个/该/此/其/那么/那我/为什么」被有意排除：它们作限定词修饰新名词
#   的频率远高于作指代（"这个模型…"/"该方法…"），留在长句判定里会造成误改写。
_STRONG_ANAPHORA_RE = re.compile(r"(它|他|她|上述|前面|刚才|上一|这里|那里)")
# 弱标记——独立问句里也常见，只在**短句**中才视为追问。
_WEAK_FOLLOWUP_RE = re.compile(
    r"(它|他|她|这个|那个|这些|那些|该|此|其|上述|前面|刚才|上一|这里|那里|"
    r"继续|还有|那么|那我|呢|举个例子|再讲|再多|啥意思|什么意思|怎么说)"
)
_FOLLOWUP_MAX_CHARS = 10   # 长度分界：超过此长度即认为问句已自含完整主题
_BARE_FOLLOWUP_MAX_CHARS = 6   # 极短句（无任何标记）同样按追问处理


def create_session(db: Session, user: User, first_question: str) -> ChatSession:
    """新建会话，title 取首问前 30 字。"""
    session = ChatSession(user_id=user.id, title=first_question.strip()[:_SESSION_TITLE_MAX])
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_owned_session(db: Session, user: User, session_id: int) -> ChatSession | None:
    """取本人会话；不存在或非本人返回 None（不区分，避免探测他人会话是否存在）。"""
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        return None
    return session


def resolve_session(db: Session, user: User, session_id: int | None,
                    question: str) -> ChatSession:
    """定位本轮会话：session_id 为空/无效则新建（无效 id 静默新建，不打断提问）。"""
    if session_id is not None:
        session = get_owned_session(db, user, session_id)
        if session is not None:
            return session
    return create_session(db, user, question)


def append_turn(db: Session, session: ChatSession, question: str, answer: str,
                citations: list | None = None) -> None:
    """落库一轮问答（user + assistant 两条）并累加轮数；失败不影响问答流（调用方兜底）。"""
    db.add(ChatMessage(session_id=session.id, role="user", content=question))
    db.add(ChatMessage(session_id=session.id, role="assistant", content=answer,
                       citations=list(citations or [])))
    session.turns = (session.turns or 0) + 1
    db.commit()


def recent_history(db: Session, session: ChatSession,
                   turns: int = HISTORY_TURNS) -> list[dict]:
    """最近 turns 轮上下文（时间正序），返回 [{"role","content"}]，供直接拼进 messages。

    assistant 文本先去掉 [n] 引用编号：提示词里的资料编号每轮重新从 [1] 起编，
    带旧编号进上下文会被模型当成"已存在的资料"引用，产生指向错误的溯源。
    """
    limit = max(1, turns) * 2
    rows = (db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id.desc())
            .limit(limit)
            .all())
    rows.reverse()
    out = []
    for r in rows:
        content = r.content or ""
        if r.role == "assistant":
            content = _strip_cites(content)
        if content.strip():
            out.append({"role": r.role, "content": content})
    return out


def rewrite_query(question: str, history: list[dict]) -> str:
    """追问检索改写：指代型/超短追问拼前一轮问题一起检索，否则原样返回。

    为什么不用 LLM 改写：改写要额外一次 LLM 往返（本机 DeepSeek 首字 1~2s），而语音链路
    对首响延迟极敏感；指代型追问的共指对象在多轮 RAG 里几乎总落在"上一轮用户问题"上，
    拼接是零延迟且可解释的近似。

    判定规则（两档，因为长度与标记词各有盲区）：
      1) 命中**强指代**（它/他/她/上述/前面/刚才/上一/这里/那里）→ 改写，长短句皆然；
      2) **短句**（≤10 字）命中弱标记 → 改写；
      3) **极短句**（≤6 字）无标记 → 改写。

    为什么长句不能只看标记词：早期实现把「为什么 / 那么 / 那我 / 继续 / 这个」当长句
    改写信号，实测 4 条全新问句全部被误改（如"继续讲讲批量归一化的作用"被拼成
    "什么是梯度下降 继续讲讲批量归一化的作用"），检索 query 被上一话题污染。这类词
    在独立问句里出现频率极高，不具指代判别力。超过 10 字的中文问句通常已自含完整主题，
    此时只认真正的指代词。

    为什么极短句反而放宽：≤6 字的问句（"继续"/"还有呢"/"举个例"）本身无可检索信息，
    拼接是唯一出路；而短句自含主题时（"什么是梯度下降"）拼接的偏移也很小——主题词在
    BM25 与向量检索里都占主导，重复出现不会明显改变召回。**宁少勿多**：漏改写的代价是
    检索空手但提示词里已有历史（LLM 仍能答），误改写则是把错误资料引进来当引用。
    """
    if not history:
        return question
    prev_q = ""
    for item in reversed(history):
        if item.get("role") == "user" and item.get("content", "").strip():
            prev_q = item["content"].strip()
            break
    if not prev_q:
        return question
    q = question.strip()
    if _STRONG_ANAPHORA_RE.search(q):
        return f"{prev_q} {q}"
    if len(q) <= _FOLLOWUP_MAX_CHARS and _WEAK_FOLLOWUP_RE.search(q):
        return f"{prev_q} {q}"
    if len(q) <= _BARE_FOLLOWUP_MAX_CHARS:
        return f"{prev_q} {q}"
    return question


def list_sessions(db: Session, user: User, limit: int = 20) -> list[dict]:
    """本人会话列表（最近更新在前）。"""
    rows = (db.query(ChatSession)
            .filter(ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
            .all())
    return [
        {"id": s.id, "title": s.title, "turns": s.turns,
         "created_at": s.created_at.isoformat(), "updated_at": s.updated_at.isoformat()}
        for s in rows
    ]


def list_messages(db: Session, session: ChatSession) -> list[dict]:
    """会话全部消息（时间正序），带引用元数据供前端回放。"""
    rows = (db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id.asc())
            .all())
    return [
        {"id": m.id, "role": m.role, "content": m.content,
         "citations": list(m.citations or []), "created_at": m.created_at.isoformat()}
        for m in rows
    ]


def delete_session(db: Session, user: User, session_id: int) -> bool:
    """删除本人会话及其消息；非本人或不存在返回 False。"""
    session = get_owned_session(db, user, session_id)
    if session is None:
        return False
    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
    db.delete(session)
    db.commit()
    return True


_CITE_RE = re.compile(r"[\[【]\s*\d+(?:\s*[,，、]\s*\d+)*\s*[\]】]")


def _strip_cites(text: str) -> str:
    return _CITE_RE.sub("", text)
