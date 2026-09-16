# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import re

from app.services.parser.chunk import Chunk
from app.services.rag import KBCollection
from app.services.rag_ask import build_answer_prompt, rag_ask


class FakeLLM:
    """记录调用并返回固定答案。"""
    def __init__(self, answer="资料[1]说明了梯度下降的原理。"):
        self.answer = answer
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.answer


def _col():
    return KBCollection(name="kb", chunks=[
        Chunk(text="梯度下降通过沿负梯度方向迭代更新参数。", kind="text", source="教材.pdf", page=3, id="c1"),
        Chunk(text="房价预测案例：线性回归拟合房价。", kind="text", source="笔记.md", page=None, id="c2"),
        # 第三块与查询无关，但必须存在：rank_bm25 的 IDF 在 2 篇语料、df=1 时恒为 0，
        # 加上 BM25Index 只保留 score>0，2 篇语料下 BM25 永远召不回任何块（Task 8 测试同样用 3 篇）。
        Chunk(text="计算机网络的七层模型。", kind="text", source="教材.pdf", page=8, id="c3"),
    ])


class FakeVS:
    def search(self, name, qv, top_k, filter_dict=None):
        return []


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0, 1.0, 0.0]


def test_build_answer_prompt_numbers_context():
    hits = [type("H", (), {"chunk": _col().chunks[0], "score": 0.9})()]
    messages = build_answer_prompt("什么是梯度下降", hits)
    system = messages[0]["content"]
    assert "[1]" in system
    assert "教材.pdf" in system and "第3页" in system
    assert "什么是梯度下降" in messages[1]["content"]


def test_rag_ask_returns_citations():
    llm = FakeLLM()
    result = rag_ask(
        "什么是梯度下降", [_col()], top_k=2,
        vector_store=FakeVS(), embedder=FakeEmbedder(), llm=llm,
    )
    assert result.answer == llm.answer
    assert len(llm.calls) == 1
    assert result.citations  # 即使向量库为空，BM25 也应召回语料
    assert result.citations[0]["ref_no"] == 1
    assert "source" in result.citations[0] and "excerpt" in result.citations[0]


def test_rag_ask_citations_align_with_truncated_prompt():
    # 评审修复回归：max_chars 截断发生时，prompt 内编号必须与 citations 的 ref_no 严格一致。
    # 语料 6 块 × 约 831 字符（含头部），5 块 4155 > 4000，必然在第 5 块截断（前 4 块 3324）。
    # 每对相邻两块共享一个 df=2 的查询词：N=6 时 df=2 的词 IDF=log4.5-log2.5≈0.588>0，
    # 6 块全部 BM25 score>0（df=3 时 IDF 恰为 0，df≥4 为负，只有 df=1/2 才为正且安全）。
    filler = "内容" * 400  # 800 字符填充，凑足截断所需长度
    chunks = [
        Chunk(text=f"梯度下降。{filler}", kind="text", source="教材.pdf", page=1, id="c1"),
        Chunk(text=f"梯度下降。{filler}", kind="text", source="教材.pdf", page=2, id="c2"),
        Chunk(text=f"优化收敛。{filler}", kind="text", source="教材.pdf", page=3, id="c3"),
        Chunk(text=f"优化收敛。{filler}", kind="text", source="教材.pdf", page=4, id="c4"),
        Chunk(text=f"拟合迭代。{filler}", kind="text", source="教材.pdf", page=5, id="c5"),
        Chunk(text=f"拟合迭代。{filler}", kind="text", source="教材.pdf", page=6, id="c6"),
    ]
    col = KBCollection(name="kb", chunks=chunks)
    llm = FakeLLM()
    result = rag_ask(
        "梯度下降优化收敛拟合迭代", [col],
        vector_store=FakeVS(), embedder=FakeEmbedder(), llm=llm,
    )
    assert result.citations  # BM25 至少召回 3 块（实际 6 块全部 score>0）
    assert len(result.citations) < len(col.chunks)  # 超出 4000 预算，必然截断
    ref_nos = [c["ref_no"] for c in result.citations]
    assert ref_nos == list(range(1, len(ref_nos) + 1))  # 编号从 1 连续
    prompt_numbers = {
        int(m) for m in re.findall(r"\[(\d+)\] 来源", llm.calls[0][0]["content"])
    }
    assert prompt_numbers == set(ref_nos)  # prompt 内编号集合与 citations 严格对齐
