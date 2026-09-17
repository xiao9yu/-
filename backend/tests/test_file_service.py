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


def test_download_requires_ownership(client, tmp_path, monkeypatch):
    """越权防护：用户不能下载他人文件（评审 Important 修复回归）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def _reg(u):
        return client.post(
            "/api/auth/register",
            json={"username": u, "password": "pass123456", "role": "student"},
        )

    def _token(u):
        return client.post(
            "/api/auth/login", json={"username": u, "password": "pass123456"}
        ).json()["access_token"]

    _reg("u1")
    _reg("u2")
    t1, t2 = _token("u1"), _token("u2")
    up = client.post(
        "/api/files/upload",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert up.status_code == 200
    fid = up.json()["id"]
    # 他人下载 → 404；本人下载 → 200
    assert (
        client.get(f"/api/files/{fid}/download", headers={"Authorization": f"Bearer {t2}"}).status_code
        == 404
    )
    assert (
        client.get(f"/api/files/{fid}/download", headers={"Authorization": f"Bearer {t1}"}).status_code
        == 200
    )


def test_save_upload_exceeds_limit_rejected(tmp_path, db):
    """超过大小上限拒绝上传且不留残留（台账 A-6）。
    注：本文件 db 夹具在 tmp_path 下建 f.db，故断言对象用上传子目录（偏离简报，理由见报告）。
    """
    import io
    import pytest
    from fastapi import UploadFile
    from app.core.exceptions import BizError
    from app.models.file import FileRecord
    from app.services.file_service import save_upload

    upload_dir = tmp_path / "up"
    file = UploadFile(filename="big.pdf", file=io.BytesIO(b"x" * 100))
    with pytest.raises(BizError, match="大小限制"):
        save_upload(file, owner_id=1, upload_dir=upload_dir, db=db, max_bytes=10)
    assert db.query(FileRecord).count() == 0
    assert list(upload_dir.iterdir()) == []


def test_list_files_pagination(client, tmp_path, monkeypatch):
    """GET /api/files 支持 page/size 分页（台账 A-6）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))

    def _reg(u):
        return client.post("/api/auth/register",
                           json={"username": u, "password": "pass123456", "role": "student"})

    def _token(u):
        return client.post("/api/auth/login",
                           json={"username": u, "password": "pass123456"}).json()["access_token"]

    _reg("p1")
    t = _token("p1")
    headers = {"Authorization": f"Bearer {t}"}
    for i in range(3):
        assert client.post("/api/files/upload",
                           files={"file": (f"f{i}.txt", b"hello", "text/plain")},
                           headers=headers).status_code == 200
    r1 = client.get("/api/files", params={"page": 1, "size": 2}, headers=headers)
    assert r1.status_code == 200 and len(r1.json()) == 2
    r2 = client.get("/api/files", params={"page": 2, "size": 2}, headers=headers)
    assert r2.status_code == 200 and len(r2.json()) == 1
