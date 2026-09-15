# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""统一的内容块结构：工单18 多模态解析的基础数据结构。"""
import uuid
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """解析产物块。kind: text(文本) | table(表格) | image(图片) | formula(公式)。"""
    text: str
    kind: str
    source: str              # 来源文件名
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    page: int | None = None  # PDF 页码（从 1 开始），Office 文档为 None
    meta: dict = field(default_factory=dict)  # 附加信息：image_path、sheet 名等


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按字符数切块（带重叠），保证向量化粒度与上下文连贯。"""
    if len(text) <= chunk_size:
        return [text]
    parts = []
    start = 0
    while start < len(text):
        parts.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return [p for p in parts if p.strip()]
