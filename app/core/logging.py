"""日志与 request_id 中间件：按天切割保留 30 天，响应头回写 X-Request-ID。"""

import logging
import uuid
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 请求级上下文：日志 formatter 可直接引用 %(request_id)s
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


class RequestIdFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return super().format(record)


def setup_logging() -> None:
    """应用启动时调用一次。业务/异常日志走 app.log，uvicorn 访问日志由 uvicorn 自身管理。"""
    fmt = RequestIdFormatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
    )

    app_handler = TimedRotatingFileHandler(
        LOG_DIR / "app.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    app_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # 幂等：重复启动（如 --reload）不叠加 handler
    if not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers):
        root.addHandler(app_handler)
        root.addHandler(console)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = uuid.uuid4().hex[:12]
        request_id_var.set(rid)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
