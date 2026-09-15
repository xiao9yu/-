# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""图片解析：OCR 提取文字（rapidocr = PaddleOCR 模型的 ONNX 实现，安装轻量）。"""
from pathlib import Path

from .chunk import Chunk

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_image(image_path) -> str:
    """OCR 识别图片中的文字，多行用换行连接。"""
    result, _ = _get_engine()(str(image_path))
    if not result:
        return ""
    return "\n".join(item[1] for item in result)


def parse_image(path: Path) -> list[Chunk]:
    text = ocr_image(path)
    return [Chunk(
        text=text,
        kind="image",
        source=path.name,
        meta={"image_path": str(path)},
    )]
