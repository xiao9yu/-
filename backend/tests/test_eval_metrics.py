# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 评测脚本的指标函数测试（纯函数，不加载模型）。"""
import pytest

from eval.run_eval import (
    cited_sentence_ratio,
    citation_validity,
    faithfulness_pairs,
    hit_at_k,
    parse_refs,
    reciprocal_rank,
    sigmoid,
    source_precision,
    split_sentences,
)

PDF = "大模型提示词工程（Prompt Engineering）是什么？提示词技巧有哪些？.pdf"
DOCX = "02-RAG系列-面试题及答案.docx"


# ---------- 引用编号解析 ----------
@pytest.mark.parametrize("text,expected", [
    ("这是答案[1]。", [1]),
    ("见[1][3]两处。", [1, 3]),
    ("参考【2】的说法。", [2]),
    ("指向 [ 4 ] 的原文。", [4]),
    ("没有引用。", []),
    ("", []),
])
def test_parse_refs(text, expected):
    assert parse_refs(text) == expected


def test_split_sentences_drops_short_fragments():
    # 分句用 re.split，标点作为分隔符被移除（句子本身不含句末标点）
    sents = split_sentences("好的。梯度下降是一种优化算法，沿梯度反方向迭代更新参数。")
    assert sents == ["梯度下降是一种优化算法，沿梯度反方向迭代更新参数"]


# ---------- 检索层指标 ----------
def test_hit_at_k_respects_cutoff():
    sources = [DOCX, PDF]
    assert hit_at_k(sources, [PDF], 1) == 0.0
    assert hit_at_k(sources, [PDF], 2) == 1.0


def test_hit_at_k_returns_none_for_negative_sample():
    """负样本（expected 为空）不计入命中率，避免稀释指标。"""
    assert hit_at_k([DOCX], [], 5) is None
    assert reciprocal_rank([DOCX], []) is None
    assert source_precision([{"source": DOCX}], []) is None


def test_reciprocal_rank():
    assert reciprocal_rank([PDF, DOCX], [DOCX]) == 0.5
    assert reciprocal_rank([PDF, DOCX], [PDF]) == 1.0
    assert reciprocal_rank([DOCX], [PDF]) == 0.0


def test_source_precision_counts_expected_ratio():
    cites = [{"source": PDF}, {"source": PDF}, {"source": DOCX}]
    assert source_precision(cites, [PDF]) == pytest.approx(2 / 3)


def test_source_precision_none_when_no_citations():
    assert source_precision([], [PDF]) is None


# ---------- 生成层指标 ----------
def test_citation_validity_flags_out_of_range():
    """越界编号 = 幻觉引用，必须能被发现（这正是原实现的缺口）。"""
    rate, bad = citation_validity("答案见[1]，另见[7]。", n_citations=3)
    assert bad == [7]
    assert rate == pytest.approx(0.5)


def test_citation_validity_all_legal():
    rate, bad = citation_validity("答案见[1][2]。", n_citations=2)
    assert bad == [] and rate == 1.0


def test_citation_validity_none_without_refs():
    """无引用是覆盖率问题，不是合法性问题，两者分开衡量。"""
    rate, bad = citation_validity("这是一段没有任何标注的回答。", n_citations=5)
    assert rate is None and bad == []


def test_cited_sentence_ratio():
    answer = "梯度下降是优化算法，沿梯度反方向更新参数[1]。它需要设置学习率。"
    assert cited_sentence_ratio(answer) == pytest.approx(0.5)


def test_faithfulness_pairs_links_sentence_to_its_cited_chunk():
    cites = [{"ref_no": 1, "text": "梯度下降沿反方向更新参数"},
             {"ref_no": 2, "text": "学习率控制步长"}]
    answer = "梯度下降沿反方向更新参数[1]。学习率控制步长[2]。无关的话没有引用。"
    pairs = faithfulness_pairs(answer, cites)
    assert len(pairs) == 2
    assert pairs[0] == ["梯度下降沿反方向更新参数", "梯度下降沿反方向更新参数[1]"]
    assert pairs[1][0] == "学习率控制步长"


def test_faithfulness_pairs_skips_unresolvable_refs():
    """引用了不存在的编号时不构造打分对（不猜测、不虚高）。"""
    assert faithfulness_pairs("答案[9]。这里还有一句足够长的话。", [{"ref_no": 1, "text": "x"}]) == []


def test_sigmoid_bounds_and_midpoint():
    assert sigmoid(0) == pytest.approx(0.5)
    assert 0 < sigmoid(-8) < 0.01
    assert 0.99 < sigmoid(8) < 1
