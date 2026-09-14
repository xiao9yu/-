# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""业务异常与全局异常处理器：所有接口返回结构化错误 JSON，前端不白屏。"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BizError(Exception):
    """业务异常：携带 HTTP 状态码与用户可读的中文提示。"""

    def __init__(self, status_code: int = 400, message: str = "操作失败"):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def biz_error_handler(request: Request, exc: BizError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logging.exception("未处理异常: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
