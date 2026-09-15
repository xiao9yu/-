# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""PDF 解析：按页抽取文本与内嵌图片（图片 OCR + 保留原图）。"""
import uuid
from pathlib import Path

import pymupdf

from .chunk import Chunk, split_text
from .image_parser import ocr_image


def parse_pdf(path: Path, extract_dir: Path | None = None) -> list[Chunk]:
    doc = pymupdf.open(str(path))
    chunks: list[Chunk] = []
    for idx, page in enumerate(doc, start=1):
        # 1) 文本
        text = page.get_text().strip()
        for part in split_text(text):
            chunks.append(Chunk(text=part, kind="text", source=path.name, page=idx))
        # 2) 内嵌图片 → 存盘 + OCR（提取目录默认 uploads/extracted）
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                pix = doc.extract_image(xref)
            except Exception:
                continue
            img_path = (extract_dir or Path("uploads/extracted")) / f"{uuid.uuid4().hex}.{pix['ext']}"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(pix["image"])
            ocr_text = ocr_image(img_path)
            chunks.append(Chunk(
                text=ocr_text,
                kind="image",
                source=path.name,
                page=idx,
                meta={"image_path": str(img_path)},
            ))
    doc.close()
    return chunks
