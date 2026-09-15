# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
import io

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import BizError
from app.db import Base
from app.services.file_service import delete_file, get_file_path, save_upload


@pytest.fixture
def db(tmp_path):
    """服务函数直测：独立临时库，不污染开发库。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'f.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    yield Session()
    Base.metadata.drop_all(engine)


def _upload(tmp_path, db, filename="教案.md", content=b"hello"):
    return save_upload(
        UploadFile(filename=filename, file=io.BytesIO(content)),
        owner_id=1, upload_dir=tmp_path, db=db,
    )


def test_save_upload_creates_record_and_file(tmp_path, db):
    record = _upload(tmp_path, db)
    assert record.filename == "教案.md"
    path = get_file_path(record, tmp_path)
    assert path.exists() and path.read_bytes() == b"hello"


def test_save_upload_rejects_bad_ext(tmp_path, db):
    with pytest.raises(BizError, match="不支持"):
        _upload(tmp_path, db, filename="virus.exe")


def test_save_upload_allows_image_and_audio(tmp_path, db):
    for name in ["a.png", "b.jpg", "c.wav", "d.mp3", "e.pdf", "f.pptx", "g.xlsx"]:
        assert _upload(tmp_path, db, filename=name).id > 0


def test_delete_file_removes_disk(tmp_path, db):
    record = _upload(tmp_path, db)
    path = get_file_path(record, tmp_path)
    delete_file(record.id, upload_dir=tmp_path, db=db)
    assert not path.exists()
