# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文档解析管线入口：PDF/DOCX/PPTX/XLSX/图片 → 多模态 Chunk 列表。"""
from pathlib import Path

from .chunk import Chunk, split_text  # noqa: F401
from .image_parser import ocr_image, parse_image  # noqa: F401
from .office_parser import parse_docx, parse_pptx, parse_xlsx  # noqa: F401
from .pdf_parser import parse_pdf  # noqa: F401

_PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": None,  # 老格式：提示用户转存 docx（V1 不支持二进制 doc）
    ".pptx": parse_pptx,
    ".xlsx": parse_xlsx,
    ".png": parse_image, ".jpg": parse_image, ".jpeg": parse_image,
    ".gif": parse_image, ".bmp": parse_image,
}


def parse_document(path: Path | str) -> list[Chunk]:
    """按扩展名分发解析器；不支持的格式返回空列表。"""
    path = Path(path)
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        return []
    return parser(path)
