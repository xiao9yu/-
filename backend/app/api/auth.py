# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""认证接口：注册/登录/当前用户。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..core.security import create_access_token, hash_password, verify_password
from ..db import get_db
from ..models.user import Role, User
from .deps import get_current_user

router = APIRouter()


class RegisterIn(BaseModel):
    username: str
    password: str
    role: Role = Role.student
    real_name: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    real_name: str

    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/register", response_model=UserOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise BizError(400, "用户名已存在")
    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role,
        real_name=data.real_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if user is None or not verify_password(data.password, user.hashed_password):
        raise BizError(401, "用户名或密码错误")
    return TokenOut(access_token=create_access_token(user.id, user.role.value), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
