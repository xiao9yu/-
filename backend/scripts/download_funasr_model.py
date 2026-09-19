# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-数字人交互(18扩展)
"""FunASR 模型预下载（modelscope，约 1GB，一次性；也可由启动预热自动完成）。

用法：cd backend && python scripts/download_funasr_model.py
"""
from modelscope import snapshot_download

if __name__ == "__main__":
    path = snapshot_download(
        "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
    )
    print("模型已缓存：", path)
