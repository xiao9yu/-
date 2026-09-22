# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 问答组装：检索结果编号拼入提示词 → LLM 生成 → 返回带引用溯源的答案。"""
from dataclasses import dataclass, field

from .llm_gateway import get_gateway
from .rag import KBCollection, RagHit, hybrid_retrieve

PROMPT_SYSTEM = (
    "你是高职院校的教育智能助教，名字叫“朵娅”。请仅依据【检索资料】回答学生的问题："
    "答案必须来自检索资料，不得编造或补充资料中没有的内容；以口语化、连贯的方式"
    "给出答案本身，适合语音朗读；不得使用“参考答案”“答案一/二/三”“回答思路如下”"
    "等字样，不得照搬资料原文结构，应将资料中的多条参考回答提炼合并为一段简洁、"
    "直接的回答；凡是采用资料内容之处必须标注引用编号如[1][2]。"
    "若检索资料不足以回答，请明确说明，不要自行编造。"
)

PROMPT_SYSTEM_GENERAL = (
    "你是高职院校的教育智能助教，名字叫“朵娅”。知识库中没有找到与该问题相关的资料，"
    "请基于你自己的知识直接回答学生的问题：以口语化、连贯的方式给出答案本身，"
    "适合语音朗读；回答就是答案本身，不要提及“资料不足”“知识库中没有”等字样，"
    "不得使用“参考答案”“答案一/二/三”等格式。"
)

PROMPT_HISTORY_HINT = (
    "【对话历史】本轮是连续对话的后续轮次：请结合上文理解学生的追问"
    "（如“它”“这个”“那为什么”指代前文），保持连贯，已讲过的内容不要重复展开；"
    "若本轮问题与上文无关，按新问题独立作答。"
)


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict] = field(default_factory=list)


def _select_hits(hits: list[RagHit], max_chars: int) -> list[tuple[int, RagHit]]:
    """按 max_chars 预算截断命中并编号，返回 (ref_no, hit) 列表。"""
    selected: list[tuple[int, RagHit]] = []
    total = 0
    for i, h in enumerate(hits, start=1):
        page = f" 第{h.chunk.page}页" if h.chunk.page is not None else ""
        block = f"[{i}] 来源:{h.chunk.source}{page} 类型:{h.chunk.kind}\n{h.chunk.text}"
        if total + len(block) > max_chars:
            break
        selected.append((i, h))
        total += len(block)
    return selected


def build_answer_prompt(question: str, hits: list[RagHit], max_chars: int = 4000,
                        history: list[dict] | None = None) -> list[dict]:
    """把检索结果编号拼进 system prompt，超出长度截断。

    无命中（检索空手或精排阈值过滤掉全部弱命中）时改用通用知识提示词：
    LLM 以自身知识直接回答，不引用、不推诿。

    history 非空时把历史轮次作为正式对话消息插在 system 与当前 user 之间：
    让模型按"对话"而非"单发问答"理解，是追问能接得上话的前提。
    """
    blocks = []
    for i, h in _select_hits(hits, max_chars):
        page = f" 第{h.chunk.page}页" if h.chunk.page is not None else ""
        blocks.append(f"[{i}] 来源:{h.chunk.source}{page} 类型:{h.chunk.kind}\n{h.chunk.text}")
    if blocks:
        system = PROMPT_SYSTEM + "\n\n【检索资料】\n" + "\n\n".join(blocks)
        user = f"【问题】{question}\n要求：引用资料处标注编号如[1]；资料不足时说明。"
    else:
        system = PROMPT_SYSTEM_GENERAL
        user = f"【问题】{question}"
    if history:
        system = f"{system}\n\n{PROMPT_HISTORY_HINT}"
    messages = [{"role": "system", "content": system}]
    for item in history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    return messages


def rag_ask(
    question: str,
    collections: list[KBCollection],
    top_k: int = 5,
    *,
    vector_store=None,
    embedder=None,
    llm=None,
    rerank=None,
) -> RagAnswer:
    """完整链路：混合检索（含可选精排）→ 组装提示词 → LLM 生成 → 引用溯源。"""
    hits = hybrid_retrieve(question, collections, top_k,
                           vector_store=vector_store, embedder=embedder, rerank=rerank)
    selected = _select_hits(hits, 4000)  # 与 prompt 同一编号切片，截断后引用不越界
    messages = build_answer_prompt(question, hits)
    chat = llm or get_gateway()
    answer = chat.chat(messages)
    citations = [
        {
            "ref_no": i,
            "source": h.chunk.source,
            "page": h.chunk.page,
            "kind": h.chunk.kind,
            "excerpt": h.chunk.text[:200],
            "image_path": h.chunk.meta.get("image_path"),
        }
        for i, h in selected
    ]
    return RagAnswer(answer=answer, citations=citations)
