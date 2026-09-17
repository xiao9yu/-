# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""通用依赖：当前登录用户解析。"""
import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.exceptions import BizError
from ..core.security import decode_token
from ..db import get_db
from ..models.user import Role, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(cred.credentials)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_roles(*roles: Role):
    """角色守卫依赖：仅指定角色可访问（台账 A-7，Task 6 公共库管理使用）。"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise BizError(403, "权限不足，仅限：" + "、".join(r.value for r in roles))
        return user
    return checker
