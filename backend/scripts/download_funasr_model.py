# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""FunASR 模型预下载（modelscope，约 1GB，一次性；也可由启动预热自动完成）。

funasr 的 "paraformer-zh" 别名实际解析到 SeACo 模型（2026-09-19 冒烟实测），
故预下载同一模型 id，保证离线环境启动预热命中缓存。

用法：cd backend && python scripts/download_funasr_model.py
"""
from modelscope import snapshot_download

if __name__ == "__main__":
    path = snapshot_download(
        "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    )
    print("模型已缓存：", path)
