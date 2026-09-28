# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""NLI 忠实度评分器（评测专用，不进生产链路）。

为什么需要它：run_eval 原有 faithfulness_proxy 用 reranker 相关度衡量
"回答句与引用资料有多相关"，但**相关 ≠ 资料逻辑上支持该句**——句子可能与资料
主题一致、内容却是 LLM 自己编的（"相关但推不出"）。本模块接入 modelscope
中文 NLI 模型 iic/nlp_structbert_nli_chinese-base（三分类：矛盾=0/蕴涵=1/中立=2，
label_mapping.json），把忠实度升级为**严格蕴含判断**：资料（premise）逻辑上
蕴含回答句（hypothesis）才算忠实。

加载方式（2026-09-28 踩坑定案）：**不用 modelscope pipeline**——pipeline 构建
时会按模型自带 requirements.txt 自动 pip 安装依赖（实测把 transformers 4.57.6
降级成 4.48.3、huggingface-hub 降成 0.25.2，且卸载残留导致新旧文件混杂、加载
报 ImportError，波及生产链路）。本模块改走直载：snapshot_download（缓存命中
不装依赖）+ SbertForSequenceClassification 直读 state_dict（0 missing /
0 unexpected）+ BertTokenizerFast。加载失败缓存 None 哨兵，调用方静默降级为
仅代理指标，不炸评测、不重试风暴。

自检：
    python -c "from eval import nli_scorer as n; s=n.get_nli_scorer(); \
print(n.nli_entailment_rate([['梯度下降沿损失函数负梯度方向迭代更新参数。',
'梯度下降沿负梯度方向更新参数。']], s))"
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_ID = "iic/nlp_structbert_nli_chinese-base"

# label_mapping.json：矛盾=0、蕴涵=1、中立=2。蕴涵=忠实，其余一律不忠实。
_ID2LABEL = {0: "contradiction", 1: "entailment", 2: "neutral"}
_ENTAILMENT = {"蕴涵", "蕴含", "entailment"}
_CONTRADICTION = {"矛盾", "contradiction"}
_NEUTRAL = {"中立", "neutral"}

_scorer = None      # (model, tokenizer)；加载失败缓存 None 哨兵
_loaded = False


def _load_scorer():
    import torch
    from modelscope.hub.snapshot_download import snapshot_download
    from modelscope.models.nlp.structbert import SbertConfig, SbertForSequenceClassification
    from transformers import BertTokenizerFast

    local = snapshot_download(_MODEL_ID)
    cfg = SbertConfig.from_pretrained(local)
    cfg.num_labels = 3
    model = SbertForSequenceClassification(cfg)
    sd = torch.load(Path(local) / "pytorch_model.bin", map_location="cpu", weights_only=False)
    missing, unexpected = model.load_state_dict(sd)
    if missing or unexpected:
        raise RuntimeError(f"state_dict 键不匹配：missing={missing[:3]} unexpected={unexpected[:3]}")
    model.eval()
    tok = BertTokenizerFast.from_pretrained(local)
    return model, tok


def get_nli_scorer():
    """懒加载 + None 哨兵：只在首次调用时尝试加载，失败不再重试。"""
    global _scorer, _loaded
    if not _loaded:
        _loaded = True
        try:
            _scorer = _load_scorer()
            logger.info("NLI 模型加载完成（%s，直载路径）", _MODEL_ID)
        except Exception:
            _scorer = None
            logger.exception("NLI 模型加载失败，忠实度指标降级为仅代理指标")
    return _scorer


def extract_label(out: Any) -> str:
    """把（外部 pipeline 形态的）输出归一化为 entailment / neutral / contradiction / unknown。

    直载路径已产出 id，此函数保留用于兼容 pipeline 输出与单测钉住标签口径。
    """
    if isinstance(out, str):
        raw = out
    elif isinstance(out, (int, float)):
        return _ID2LABEL.get(int(out), "unknown")
    elif isinstance(out, dict):
        labels = out.get("labels") or out.get("label")
        raw = labels[0] if isinstance(labels, (list, tuple)) and labels else labels
        if raw is None:
            return "unknown"
    else:
        return "unknown"
    s = str(raw).strip()
    if s in _ENTAILMENT:
        return "entailment"
    if s in _CONTRADICTION:
        return "contradiction"
    if s in _NEUTRAL:
        return "neutral"
    if s.isdigit():
        return _ID2LABEL.get(int(s), "unknown")
    return "unknown"


def count_labels(ids: list[int]) -> dict[str, int]:
    """标签 id 序列 → 三分类计数（纯函数）。未知 id 计入 unknown，不虚高不冤枉。"""
    counts: dict[str, int] = {"entailment": 0, "neutral": 0, "contradiction": 0, "unknown": 0}
    for lid in ids:
        counts[_ID2LABEL.get(int(lid), "unknown")] += 1
    return counts


def entailment_rate(counts: dict[str, int]) -> float | None:
    """计数 → 蕴涵率（纯函数）。三分类有效对为 0 时返回 None（不给 0% 假结论）。"""
    valid = sum(counts.get(k, 0) for k in ("entailment", "neutral", "contradiction"))
    if valid == 0:
        return None
    return counts.get("entailment", 0) / valid


def nli_entailment_rate(pairs: list[list[str]], scorer=None) -> tuple[float | None, dict[str, int]]:
    """pairs: [[资料文本, 回答句], ...] → (蕴涵率, 三分类计数)。

    批量推理（一次 forward 全部 pairs）。scorer 不可用或 pairs 为空返回 (None, {})。
    单对推理异常时全部计入 unknown（不猜、不炸评测）。
    """
    if not pairs or scorer is None:
        return None, {}
    import torch
    model, tok = scorer
    try:
        prems, hyps = zip(*pairs)
        enc = tok(list(prems), list(hyps), return_tensors="pt",
                  max_length=512, truncation=True, padding=True)
        with torch.no_grad():
            out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"],
                        token_type_ids=enc["token_type_ids"])
        logits = out.logits if hasattr(out, "logits") else out["logits"]
        counts = count_labels(logits.argmax(dim=-1).tolist())
    except Exception:
        logger.exception("NLI 批量推理失败，%d 对全部计入 unknown", len(pairs))
        counts = {"entailment": 0, "neutral": 0, "contradiction": 0, "unknown": len(pairs)}
    return entailment_rate(counts), counts
