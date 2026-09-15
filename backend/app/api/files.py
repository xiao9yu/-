# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""文件接口：上传/下载/我的文件列表。"""
from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..config import settings
from ..core.exceptions import BizError
from ..db import get_db
from ..models.file import FileRecord
from ..models.user import User
from ..services.file_service import delete_file, get_file_path, save_upload
from .deps import get_current_user

router = APIRouter()


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    ext: str
    size: int
    created_at: object


@router.post("/upload", response_model=FileOut)
def upload(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return save_upload(file, owner_id=user.id, upload_dir=settings.upload_dir, db=db)


@router.get("", response_model=list[FileOut])
def list_files(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(FileRecord).filter(FileRecord.owner_id == user.id).order_by(FileRecord.id.desc()).all()


@router.get("/{file_id}/download")
def download(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(FileRecord, file_id)
    if record is None:
        raise BizError(404, "文件不存在")
    path = get_file_path(record, settings.upload_dir)
    if not path.exists():
        raise BizError(404, "文件已丢失")
    return FileResponse(path, filename=record.filename)


@router.delete("/{file_id}")
def remove(file_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(FileRecord, file_id)
    if record is None or record.owner_id != user.id:
        raise BizError(404, "文件不存在")
    delete_file(file_id, settings.upload_dir, db)
    return {"ok": True}
