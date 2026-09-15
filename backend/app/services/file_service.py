# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件服务：上传落盘+登记、路径解析、删除。
db 会话由调用方传入（API 层用请求级会话，测试用临时库）。
"""
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..models.file import FileRecord

ALLOWED_EXTS = {
    # 文档（工单18 验收格式清单）
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    # 文本与笔记
    "md", "txt",
    # 图片
    "png", "jpg", "jpeg", "gif", "bmp",
    # 音视频（工单17 多媒体、工单20 面试录音）
    "mp3", "wav", "m4a", "aac", "mp4", "webm",
}


def _check_ext(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTS:
        raise BizError(400, f"不支持的文件类型：{ext or '无后缀'}")
    return ext


def save_upload(file: UploadFile, owner_id: int, upload_dir: Path | str, db: Session) -> FileRecord:
    """保存上传文件到 upload_dir（磁盘名用 uuid），并在数据库登记。"""
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = _check_ext(file.filename or "unknown")
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    dest = upload_dir / stored_name
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    record = FileRecord(
        filename=file.filename or stored_name,
        stored_name=stored_name,
        ext=ext,
        size=dest.stat().st_size,
        owner_id=owner_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_file_path(record: FileRecord, upload_dir: Path | str) -> Path:
    return Path(upload_dir) / record.stored_name


def delete_file(record_id: int, upload_dir: Path | str, db: Session) -> None:
    """删除磁盘文件与数据库记录（不存在则忽略磁盘错误）。"""
    record = db.get(FileRecord, record_id)
    if record is None:
        return
    path = Path(upload_dir) / record.stored_name
    if path.exists():
        path.unlink()
    db.delete(record)
    db.commit()
