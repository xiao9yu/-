# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""精排候选数 / 截断长度的「质量-时延」A/B。

为什么需要它：精排（bge-reranker-v2-m3）在本机 CPU 上约 2.4 ms/token，单次问答的
20 对候选要 21~31 s，是检索链路 99% 的耗时来源（见 docs/RAG检索与引用质量评测报告.md
§6.1 的耗时归因）。降低候选数是唯一**线性有效**的杠杆，但会牺牲召回——到底砍到
多少不伤质量，不能凭感觉，要测。

关键设计：生产的精排调用是 `rerank(q, fused[:N], top_n)`，即 **RRF 融合结果与候选
截断档无关**。因此只需对前 20 条候选打分一次，即可用同一组分数精确模拟 N 各档的
排序与阈值过滤（阈值取该档内的最高分，与 `Reranker.rerank` 实现一致），无需为每档
重跑模型——否则 6 档 × 32 题要跑两个多小时。

真实耗时另用少量题逐档实测（`--latency-questions`），用于校验"档位—耗时"的线性关系。

用法（在 backend/ 下执行）：
    python -m eval.rerank_ab
    python -m eval.rerank_ab --k-list 20,15,12,10,8,6 --latency-questions 4 \\
        --out eval/reports/rerank_ab.json

截断长度对照：精排耗时与 token 量近似线性，`--max-len` 可压低 token 量（如 384 时约为
1024 的 74%），但**会截断 chunk 尾部**、改变分数与阈值过滤，属质量-时延权衡。精排无采样，
同一题同一档位结果确定，故不同 `--max-len` 可分两次运行精确对比：

    python -m eval.rerank_ab --k-list 10 --max-len 1024 --out eval/reports/rerank_ml1024.json
    python -m eval.rerank_ab --k-list 10 --max-len 384  --out eval/reports/rerank_ml384.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

# settings 用的是相对路径（./data/app.db、./data/faiss），必须在导入 app.* 之前切到 backend/
_BACKEND = Path(__file__).resolve().parent.parent
if Path.cwd() != _BACKEND:
    os.chdir(_BACKEND)

_QA_PATH = Path(__file__).resolve().parent / "qa_set.json"
_TOP_N = 5          # 精排后保留条数（与生产一致）


def simulate_selection(scores: list[float], hits: list, k: int, top_n: int = _TOP_N):
    """按 Reranker.rerank 的语义，在前 k 条候选上复现排序与阈值过滤。

    阈值 `floor = max(ABS_FLOOR, REL_RATIO * max(本档分数))` 必须用**本档**最高分：
    候选变少时最高分可能下降，阈值随之降低，过滤行为与生产一致。
    """
    from app.services.rerank import _ABS_FLOOR, _REL_RATIO

    sc, hs = scores[:k], hits[:k]
    if not sc:
        return []
    floor = max(_ABS_FLOOR, _REL_RATIO * max(sc))
    kept = [(s, h) for s, h in zip(sc, hs) if s >= floor]
    kept.sort(key=lambda t: -t[0])
    return [h for _, h in kept[:top_n]]


def _metric(sources: list[str], expected: list[str], k: int):
    from eval.run_eval import hit_at_k, reciprocal_rank

    if not expected:
        return None, None
    return hit_at_k(sources, expected, k), reciprocal_rank(sources, expected)


def run(args: argparse.Namespace) -> dict:
    from sqlalchemy.orm import sessionmaker

    from app.config import settings
    from app.db import engine
    from app.models.user import User
    from app.services import kb_service
    from app.services.embeddings import get_embedder
    from app.services.rag import hybrid_retrieve
    from app.services.rerank import _sigmoid, get_reranker
    from app.services.vector_store import get_vector_store
    from eval.run_eval import load_qa

    # 让生产路径（Reranker.rerank → predict）也用同一截断档位，逐档实测耗时才有意义
    settings.rerank_max_len = args.max_len or settings.rerank_max_len
    args.max_len = settings.rerank_max_len

    ks = [int(x) for x in args.k_list.split(",") if x.strip()]
    ks = sorted(set(ks), reverse=True)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    user = db.query(User).filter(User.username == args.user).first()
    if user is None:
        raise SystemExit(f"用户不存在：{args.user}")
    collections = kb_service._load_collections(user, db)
    print(f"[准备] 用户={user.username}(id={user.id}) 语料="
          f"{sum(len(c.chunks) for c in collections)} chunks")

    embedder = get_embedder()
    store = get_vector_store()
    reranker = get_reranker()
    if reranker is None:
        raise SystemExit("精排不可用（模型未加载），无法做 A/B")

    items = load_qa(_QA_PATH)
    if args.limit:
        items = items[: args.limit]
    print(f"[准备] 题量={len(items)}  候选档位={ks}  逐档实测题量={args.latency_questions}\n")

    # 预热：BM25 懒建索引 + reranker 首次推理
    hybrid_retrieve("预热查询：梯度下降", collections, top_k=_TOP_N,
                    vector_store=store, embedder=embedder, rerank=reranker)

    per_k: dict[int, dict] = {k: {"sources": [], "expected": [], "kept": []} for k in ks}
    tok_per_pair: list[int] = []
    scored_pairs = 0

    for n, item in enumerate(items, 1):
        q = item["question"]
        expected = item.get("expected_sources") or []

        # 1) 取与生产完全相同的 20 条 RRF 候选（rerank=None 时 hybrid_retrieve 返回全量融合结果）
        fused = hybrid_retrieve(q, collections, top_k=_TOP_N,
                                vector_store=store, embedder=embedder, rerank=None)
        cands = fused[: args.max_candidates]
        if not cands:
            continue

        # 2) 打分一次（真实前向），token 量用于解释耗时
        pairs = [[q, h.chunk.text] for h in cands]
        enc = reranker.model._tokenizer(pairs, padding=True, truncation=True,
                                        max_length=args.max_len, return_tensors="pt")
        tok = int(enc["input_ids"].shape[0] * enc["input_ids"].shape[1])
        tok_per_pair.append(round(tok / len(pairs)))
        scored_pairs += len(pairs)

        t = time.time()
        scores = [_sigmoid(x) for x in reranker.model.predict(pairs, max_length=args.max_len)]
        full_ms = (time.time() - t) * 1000

        # 3) 用同一组分数模拟各档
        for k in ks:
            sel = simulate_selection(scores, cands, k)
            srcs = [h.chunk.source for h in sel]
            h1, rr = _metric(srcs, expected, 1)
            h5, _ = _metric(srcs, expected, _TOP_N)
            per_k[k]["sources"].append(srcs)
            per_k[k]["expected"].append(expected)
            per_k[k]["kept"].append(len(sel))

        # 4) 逐档真实耗时（少量题）
        if n <= args.latency_questions:
            for k in ks:
                t = time.time()
                reranker.rerank(q, cands[:k], top_n=_TOP_N)
                per_k[k].setdefault("real_ms", []).append((time.time() - t) * 1000)

        flag = "" if not expected else (
            "✓" if any(x in expected for x in per_k[ks[0]]["sources"][-1]) else "✗")
        print(f"  [{n:2d}/{len(items)}] {flag} {item['id']:7s} 候选{len(cands)}条 "
              f"前沿{tok:5d}tok {full_ms:7.0f}ms  {q[:26]}")

    db.close()

    # ---------------- 汇总 ----------------
    report: dict = {
        "meta": {
            "user": user.username,
            "n_questions": len(items),
            "k_list": ks,
            "max_candidates": args.max_candidates,
            "max_len": args.max_len,
            "avg_tokens_per_pair": round(statistics.mean(tok_per_pair)) if tok_per_pair else 0,
            "latency_questions": args.latency_questions,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "by_k": {},
    }
    for k in ks:
        d = per_k[k]
        pos = [(s, e) for s, e in zip(d["sources"], d["expected"]) if e]
        h1 = statistics.mean([1.0 if any(x in e for x in s[:1]) else 0.0 for s, e in pos])
        h3 = statistics.mean([1.0 if any(x in e for x in s[:3]) else 0.0 for s, e in pos])
        h5 = statistics.mean([1.0 if any(x in e for x in s) else 0.0 for s, e in pos])
        mrr = statistics.mean(
            [next((1.0 / i for i, x in enumerate(s, 1) if x in e), 0.0) for s, e in pos])
        real = d.get("real_ms")
        report["by_k"][str(k)] = {
            "hit@1": round(h1, 4), "hit@3": round(h3, 4), "hit@5": round(h5, 4),
            "mrr": round(mrr, 4),
            "avg_kept": round(statistics.mean(d["kept"]), 2),
            "avg_empty_rate": round(
                statistics.mean([1.0 if not s else 0.0 for s in d["sources"]]), 4),
            "measured_ms": round(statistics.mean(real)) if real else None,
            "n_measured": len(real) if real else 0,
        }

    # 与最大档相比，各档的"丢题"明细（质量问题必须可见，不能只看均值）
    base = per_k[ks[0]]
    lost: list[dict] = []
    for i, item in enumerate(items):
        if i >= len(base["sources"]):
            break
        exp = base["expected"][i]
        if not exp:
            continue
        base_ok = any(x in exp for x in base["sources"][i])
        for k in ks[1:]:
            ok = any(x in exp for x in per_k[k]["sources"][i])
            if base_ok and not ok:
                lost.append({"id": item["id"], "k": k, "question": item["question"]})
    report["regressions_vs_%d" % ks[0]] = lost
    return report


def print_report(rep: dict) -> None:
    m = rep["meta"]
    print("\n" + "=" * 78)
    print(f"精排候选数 A/B  题量={m['n_questions']}  max_len={m['max_len']}  "
          f"平均 {m['avg_tokens_per_pair']} tok/对")
    print("=" * 78)
    head = (f"{'候选数':>6}{'hit@1':>9}{'hit@3':>9}{'hit@5':>9}{'MRR':>9}"
            f"{'平均保留':>10}{'空手率':>9}{'实测耗时':>11}")
    print(head)
    print("-" * len(head))
    for k, a in rep["by_k"].items():
        ms = f"{a['measured_ms']:>9.0f}ms" if a["measured_ms"] is not None else f"{'-':>11}"
        print(f"{k:>6}{a['hit@1']:>9.1%}{a['hit@3']:>9.1%}{a['hit@5']:>9.1%}"
              f"{a['mrr']:>9.3f}{a['avg_kept']:>10.1f}{a['avg_empty_rate']:>9.1%}{ms}")
    key = "regressions_vs_%s" % list(rep["by_k"])[0]
    reg = rep.get(key) or []
    if reg:
        print(f"\n相对最大档（{list(rep['by_k'])[0]}）的质量回退（{len(reg)} 处）：")
        for r in reg:
            print(f"  k={r['k']:<3} {r['id']:7s} {r['question'][:40]}")
    else:
        print(f"\n相对最大档无质量回退。")


def main() -> None:
    ap = argparse.ArgumentParser(description="精排候选数质量-时延 A/B")
    ap.add_argument("--user", default="student")
    ap.add_argument("--k-list", default="20,15,12,10,8,6",
                    help="逗号分隔的候选档位")
    ap.add_argument("--max-candidates", type=int, default=20,
                    help="最多取多少条 RRF 候选参与打分（= 现状上限）")
    ap.add_argument("--max-len", type=int, default=0,
                    help="tokenizer 截断长度；0 = 用 settings.rerank_max_len（默认 1024=不截断）")
    ap.add_argument("--latency-questions", type=int, default=4,
                    help="逐档实测真实耗时的题量（每题各档各跑一次，代价高）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题（调试用）")
    ap.add_argument("--out", default="", help="结果 JSON 落盘路径")
    args = ap.parse_args()

    rep = run(args)
    print_report(rep)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    main()
