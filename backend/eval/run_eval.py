# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""RAG 检索与引用质量评测。

为什么要它：项目此前没有任何量化口径——"检索准不准""引用有没有编"全靠感觉。
本脚本复用**生产检索链路**（rag.hybrid_retrieve + kb_service.answer_events），
对 eval/qa_set.json 中的题目跑出可复现的指标，供答辩与回归对比。

用法（在 backend/ 下执行）：
    python -m eval.run_eval                       # 检索层指标，零 LLM 成本
    python -m eval.run_eval --with-llm            # 端到端，额外测引用合法性与忠实度代理
    python -m eval.run_eval --no-rerank           # 关精排做对照
    python -m eval.run_eval --out eval/reports/student_full.json

指标口径：
  · hit@k / mrr      期望来源是否进入检索 top-k，及其排名倒数（负样本不计入）
                     —— 仅检索模式基于 hybrid_retrieve 的返回；端到端模式基于下发给
                        模型的 citations（经精排阈值过滤），更贴近学生实际所见
  · source_precision 下发的 citations 中属于期望来源的比例
  · citation_validity 回答里 [n] 编号未越界的比例（越界 = 幻觉引用）
  · faithfulness_proxy 回答句 vs 其被引用 chunk 的 reranker 相关度均值
                      —— **代理指标**：衡量语义相关，不等价于严格蕴含（NLI）
  · negative_ok      负样本未产生引用的比例（检验"资料不足不编造"）
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

# settings 用的是相对路径（./data/app.db、./data/faiss），必须在导入 app.* 之前切到 backend/
_BACKEND = Path(__file__).resolve().parent.parent
if Path.cwd() != _BACKEND:
    os.chdir(_BACKEND)

CITE_RE = re.compile(r"[\[【]\s*(\d+)\s*[\]】]")
SENT_SPLIT_RE = re.compile(r"[。！？!?\n]+")
_MIN_SENT_CHARS = 8          # 过短的句子（"好的"）不参与忠实度统计
_QA_PATH = Path(__file__).resolve().parent / "qa_set.json"


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ---------------- 指标函数（纯函数，便于单测） ----------------

def parse_refs(text: str) -> list[int]:
    """抽出回答中出现的引用编号，如 "见 [1][3]" -> [1, 3]。"""
    return [int(x) for x in CITE_RE.findall(text or "")]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(text or "") if len(s.strip()) >= _MIN_SENT_CHARS]


def _matched(sources: list[str], expected: list[str]) -> bool:
    """来源匹配：按文件名精确匹配（source 字段即文件名）。"""
    return any(s in expected for s in sources)


def hit_at_k(sources: list[str], expected: list[str], k: int) -> float | None:
    """期望来源是否出现在前 k 条；负样本（expected 为空）不适用 → None。"""
    if not expected:
        return None
    return 1.0 if _matched(sources[:k], expected) else 0.0


def reciprocal_rank(sources: list[str], expected: list[str]) -> float | None:
    """首个期望来源的排名倒数。"""
    if not expected:
        return None
    for i, s in enumerate(sources, 1):
        if s in expected:
            return 1.0 / i
    return 0.0


def source_precision(citations: list[dict], expected: list[str]) -> float | None:
    """下发的引用里，属于期望来源的比例。衡量引用是否"散落到无关文件"。"""
    if not expected or not citations:
        return None
    got = [c.get("source") for c in citations]
    return sum(1 for s in got if s in expected) / len(got)


def citation_validity(answer: str, n_citations: int) -> tuple[float | None, list[int]]:
    """回答中 [n] 编号的合法率；返回 (合法率, 越界编号列表)。

    无引用时返回 None（"没引用"是覆盖率问题，不是合法性问题，两者分开衡量）。
    """
    refs = parse_refs(answer)
    if not refs:
        return None, []
    bad = [r for r in refs if r < 1 or r > n_citations]
    return 1.0 - len(bad) / len(refs), bad


def cited_sentence_ratio(answer: str) -> float | None:
    """带引用的句子占（有效长句的）比例——引用覆盖率，防"全篇无标注"。"""
    sents = split_sentences(answer)
    if not sents:
        return None
    return sum(1 for s in sents if parse_refs(s)) / len(sents)


def faithfulness_pairs(answer: str, citations: list[dict]) -> list[list[str]]:
    """构造忠实度打分对 [[被引用 chunk 文本, 回答句], ...]。"""
    by_ref = {c.get("ref_no"): c.get("text", "") for c in citations}
    pairs: list[list[str]] = []
    for sent in split_sentences(answer):
        for ref in parse_refs(sent):
            text = by_ref.get(ref)
            if text and text.strip():
                pairs.append([text, sent])
    return pairs


def mean(vals: list[float | None]) -> float | None:
    nums = [v for v in vals if v is not None]
    return sum(nums) / len(nums) if nums else None


# ---------------- 评测执行 ----------------

def load_qa(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["items"] if isinstance(data, dict) else data


def run(args: argparse.Namespace) -> dict:
    from app.db import SessionLocal
    from app.models.user import User
    from app.services import kb_service, learn_profile
    from app.services.embeddings import get_embedder
    from app.services.rag import hybrid_retrieve
    from app.services.rerank import get_reranker
    from app.services.vector_store import get_vector_store

    # 评测是只读语义：屏蔽画像写入，否则几十道题会污染 learn_events 演示数据
    learn_profile.record_ask_events = lambda *a, **k: None

    db = SessionLocal()
    user = db.query(User).filter(User.username == args.user).first()
    if user is None:
        raise SystemExit(f"用户不存在：{args.user}")
    collections = kb_service._load_collections(user, db)
    n_chunks = sum(len(c.chunks) for c in collections)
    print(f"[准备] 用户={user.username}(id={user.id}) 集合={[c.name for c in collections]} "
          f"语料={n_chunks} chunks")

    t0 = time.time()
    embedder = get_embedder()
    print(f"[准备] bge-m3 就绪 用时 {time.time() - t0:.1f}s")
    store = get_vector_store()
    reranker = None
    if not args.no_rerank:
        t1 = time.time()
        reranker = get_reranker()
        print(f"[准备] reranker={'就绪' if reranker else '不可用(降级)'} 用时 {time.time() - t1:.1f}s")

    items = load_qa(_QA_PATH)
    if args.limit:
        items = items[: args.limit]
    rows: list[dict] = []

    # 预热：BM25 索引（按语料指纹懒建）与 reranker 首次推理都会计入首题耗时，
    # 不预热会把一次性开销摊进平均耗时，掩盖真实稳态时延
    if not args.no_warmup:
        t = time.time()
        hybrid_retrieve("预热查询：梯度下降", collections, top_k=args.top_k,
                        vector_store=store, embedder=embedder, rerank=reranker)
        print(f"[准备] 检索链路预热完成 用时 {time.time() - t:.1f}s")

    print(f"[评测] 共 {len(items)} 题  模式={'检索+生成' if args.with_llm else '仅检索'}"
          f"  精排={'关' if args.no_rerank else '开'}\n")

    for n, item in enumerate(items, 1):
        q = item["question"]
        expected = item.get("expected_sources") or []
        row: dict = {"id": item["id"], "group": item["group"], "question": q,
                     "expected": expected, "expects_citation": item.get("expects_citation", True)}

        if args.with_llm:
            # 端到端模式复用生产链路的 citations 作为检索来源：它正是"下发给模型的资料"、
            # 也是学生实际看到的溯源，比在门外再检索一次更贴近端到端质量；同时避免重复检索
            # 把单题耗时翻倍（精排是 20s 级瓶颈，见报告"检索时延"一节）。
            answer, citations, err = "", [], None
            t = time.time()
            for event, data in kb_service.answer_events(
                    q, user, db, vector_store=store, embedder=embedder, reranker=reranker):
                if event == "citations":
                    citations = data
                elif event == "delta":
                    answer += data.get("text", "")
                elif event == "error":
                    err = data.get("message")
            row["gen_ms"] = round((time.time() - t) * 1000)
            row["error"] = err
            row["answer"] = answer
            row["n_citations"] = len(citations)
            row["citation_sources"] = [c.get("source") for c in citations]
            sources = row["citation_sources"]
            row["retrieval_source"] = "citations"
            row["source_precision"] = source_precision(citations, expected)
            valid, bad = citation_validity(answer, len(citations))
            row["citation_validity"] = valid
            row["bad_refs"] = bad
            row["cited_sentence_ratio"] = cited_sentence_ratio(answer)
            pairs = faithfulness_pairs(answer, citations)
            if pairs and reranker is not None:
                scores = [sigmoid(x) for x in reranker.model.predict(pairs)]
                row["faithfulness_proxy"] = sum(scores) / len(scores)
                row["faithfulness_n"] = len(pairs)
            else:
                row["faithfulness_proxy"] = None
                row["faithfulness_n"] = 0
            if not expected:      # 负样本：不应产生引用
                row["negative_ok"] = (len(citations) == 0 and not parse_refs(answer))
        else:
            t = time.time()
            hits = hybrid_retrieve(q, collections, top_k=args.top_k,
                                   vector_store=store, embedder=embedder, rerank=reranker)
            row["retrieve_ms"] = round((time.time() - t) * 1000)
            sources = [h.chunk.source for h in hits]
            row["hit_scores"] = [round(float(h.score), 4) for h in hits]
            row["retrieval_source"] = "hits"

        row["hit_sources"] = sources
        row["hit@1"] = hit_at_k(sources, expected, 1)
        row["hit@3"] = hit_at_k(sources, expected, 3)
        row["hit@5"] = hit_at_k(sources, expected, args.top_k)
        row["mrr"] = reciprocal_rank(sources, expected)
        row["empty_retrieval"] = len(sources) == 0

        rows.append(row)
        flag = "" if row["hit@5"] is None else ("✓" if row["hit@5"] else "✗")
        ms = row.get("retrieve_ms", row.get("gen_ms"))
        ms_txt = f"{ms:>6d}ms" if ms is not None else "      -"
        extra = ""
        if args.with_llm:
            extra = f"  引用{row['n_citations']}条"
            if row["citation_validity"] is not None:
                extra += f" 合法率={row['citation_validity']:.0%}"
        print(f"  [{n:2d}/{len(items)}] {flag} {item['id']:7s} {q[:28]:<28s}{ms_txt}{extra}")

    db.close()
    return summarize(rows, args, user.username, n_chunks)


def summarize(rows: list[dict], args, user: str, n_chunks: int) -> dict:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)

    def agg(rs: list[dict]) -> dict:
        return {
            "n": len(rs),
            "hit@1": mean([r["hit@1"] for r in rs]),
            "hit@3": mean([r["hit@3"] for r in rs]),
            "hit@5": mean([r["hit@5"] for r in rs]),
            "mrr": mean([r["mrr"] for r in rs]),
            "source_precision": mean([r.get("source_precision") for r in rs]),
            "citation_validity": mean([r.get("citation_validity") for r in rs]),
            "cited_sentence_ratio": mean([r.get("cited_sentence_ratio") for r in rs]),
            "faithfulness_proxy": mean([r.get("faithfulness_proxy") for r in rs]),
            "empty_retrieval_rate": mean([1.0 if r["empty_retrieval"] else 0.0 for r in rs]),
            "avg_retrieve_ms": mean([r.get("retrieve_ms") for r in rs]),
            "avg_gen_ms": mean([r.get("gen_ms") for r in rs]),
            "error_rate": mean([1.0 if r.get("error") else 0.0 for r in rs]) if args.with_llm else None,
        }

    pos = [r for r in rows if r["expected"]]
    neg = [r for r in rows if not r["expected"]]
    out = {
        "meta": {
            "user": user, "n_chunks": n_chunks, "top_k": args.top_k,
            "rerank": not args.no_rerank, "with_llm": args.with_llm,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "overall": agg(pos),
        "by_group": {g: agg(rs) for g, rs in groups.items() if g != "负样本"},
    }
    if neg and args.with_llm:
        out["negative"] = {
            "n": len(neg),
            "no_citation_rate": mean([1.0 if r.get("negative_ok") else 0.0 for r in neg]),
            "empty_retrieval_rate": mean([1.0 if r["empty_retrieval"] else 0.0 for r in neg]),
        }
    out["items"] = rows
    return out


def fmt(v, pct: bool = True) -> str:
    if v is None:
        return "  -  "
    return f"{v:.1%}" if pct else f"{v:.3f}"


def print_report(res: dict) -> None:
    m = res["meta"]
    print("\n" + "=" * 74)
    print(f"评测结果  用户={m['user']}  语料={m['n_chunks']} chunks  top_k={m['top_k']}  "
          f"精排={'开' if m['rerank'] else '关'}  生成={'开' if m['with_llm'] else '关'}")
    print("=" * 74)
    head = f"{'分组':<14}{'n':>4}{'hit@1':>8}{'hit@3':>8}{'hit@5':>8}{'MRR':>8}"
    if m["with_llm"]:
        head += f"{'引用准':>8}{'合法率':>8}{'覆盖':>7}{'忠实度':>8}{'出错':>7}"
    print(head)
    print("-" * len(head))
    for g, a in res["by_group"].items():
        line = (f"{g:<14}{a['n']:>4}{fmt(a['hit@1']):>8}{fmt(a['hit@3']):>8}"
                f"{fmt(a['hit@5']):>8}{fmt(a['mrr'], False):>8}")
        if m["with_llm"]:
            line += (f"{fmt(a['source_precision']):>8}{fmt(a['citation_validity']):>8}"
                     f"{fmt(a['cited_sentence_ratio']):>7}{fmt(a['faithfulness_proxy']):>8}"
                     f"{fmt(a['error_rate']):>7}")
        print(line)
    o = res["overall"]
    line = (f"{'【总体】':<14}{o['n']:>4}{fmt(o['hit@1']):>8}{fmt(o['hit@3']):>8}"
            f"{fmt(o['hit@5']):>8}{fmt(o['mrr'], False):>8}")
    if m["with_llm"]:
        line += (f"{fmt(o['source_precision']):>8}{fmt(o['citation_validity']):>8}"
                 f"{fmt(o['cited_sentence_ratio']):>7}{fmt(o['faithfulness_proxy']):>8}"
                 f"{fmt(o['error_rate']):>7}")
    print("-" * len(head))
    print(line)
    if "negative" in res:
        neg = res["negative"]
        print(f"\n负样本（{neg['n']} 题）：无误引用率={fmt(neg['no_citation_rate'])}  "
              f"检索空手率={fmt(neg['empty_retrieval_rate'])}")
    if o.get("avg_retrieve_ms") is not None:
        print(f"\n平均检索耗时 {o['avg_retrieve_ms']:.0f} ms/题"
              f"（检索来源：{res['items'][0].get('retrieval_source', 'hits')}）")
    if o.get("avg_gen_ms") is not None:
        print(f"平均端到端耗时 {o['avg_gen_ms']:.0f} ms/题（含检索 + LLM 生成）")
    miss = [r["id"] for r in res["items"] if r.get("hit@5") == 0.0]
    if miss:
        print(f"未命中题目：{', '.join(miss)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 检索与引用质量评测")
    ap.add_argument("--user", default="student", help="以哪个用户视角评测（决定可见的私有库）")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--with-llm", action="store_true", help="跑端到端生成（消耗 LLM 调用）")
    ap.add_argument("--no-rerank", action="store_true", help="关闭精排，用于对照")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（调试用）")
    ap.add_argument("--no-warmup", action="store_true", help="跳过检索链路预热（测冷启动时用）")
    ap.add_argument("--out", default="", help="结果 JSON 落盘路径")
    args = ap.parse_args()

    res = run(args)
    print_report(res)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    main()
