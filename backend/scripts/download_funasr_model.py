# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""FunASR 模型预下载（modelscope，合计约 2GB，一次性；也可由启动预热自动完成）。

三个别名的实际解析（funasr/download/name_maps_from_hub.py，本机 1.4.16 实测）：
  paraformer-zh            → iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
  paraformer-zh-streaming  → iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online
  fsmn-vad                 → iic/speech_fsmn_vad_zh-cn-16k-common-pytorch
按真实 id 预下载，保证离线环境（HF_HUB_OFFLINE=1）下启动预热直接命中缓存。

用法：cd backend && python scripts/download_funasr_model.py
"""
from modelscope import snapshot_download

MODELS = [
    ("批量转写 paraformer-zh",
     "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"),
    ("流式转写 paraformer-zh-streaming",
     "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"),
    ("端点检测 fsmn-vad",
     "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"),
]

if __name__ == "__main__":
    for label, model_id in MODELS:
        path = snapshot_download(model_id)
        print(f"{label} 已缓存：{path}")
