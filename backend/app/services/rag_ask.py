# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 问答组装：检索结果编号拼入提示词 → LLM 生成 → 返回带引用溯源的答案。"""
from dataclasses import dataclass, field

from .llm_gateway import get_gateway
from .rag import KBCollection, RagHit, hybrid_retrieve

PROMPT_SYSTEM = (
    "你是高职院校的教育智能助教。请基于【检索资料】回答学生的问题，"
    "回答时在引用资料处标注编号如[1][2]。若资料不足以回答，请明确说明。"
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


def build_answer_prompt(question: str, hits: list[RagHit], max_chars: int = 4000) -> list[dict]:
    """把检索结果编号拼进 system prompt，超出长度截断。"""
    blocks = []
    for i, h in _select_hits(hits, max_chars):
        page = f" 第{h.chunk.page}页" if h.chunk.page is not None else ""
        blocks.append(f"[{i}] 来源:{h.chunk.source}{page} 类型:{h.chunk.kind}\n{h.chunk.text}")
    system = PROMPT_SYSTEM
    if blocks:
        system += "\n\n【检索资料】\n" + "\n\n".join(blocks)
    user = f"【问题】{question}\n要求：引用资料处标注编号如[1]；资料不足时说明。"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


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
