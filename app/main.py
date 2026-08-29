"""应用入口：中间件 / 异常处理 / 路由注册。

模块路由注册约定：每个业务模块 `app/<module>/api/v1/__init__.py` 暴露 `router`，
在下方 MODULE_ROUTERS 按依赖层级顺序登记（M0 仅 user；customer/institution/...
各自里程碑实施时追加）。
"""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.approval.api.v1 import router as approval_router
from app.attachment.api.v1 import router as attachment_router
from app.core.dicts import router as dict_router
from app.core.exceptions import BizError
from app.core.health import router as health_router
from app.core.logging import RequestIdMiddleware, setup_logging
from app.customer.api.v1 import router as customer_router
from app.institution.api.v1 import router as institution_router
from app.user.api.v1 import router as user_router
from app.warrant.api.v1 import router as warrant_router

logger = logging.getLogger(__name__)

setup_logging()

app = FastAPI(
    title="WHDB 担保业务管理系统 API",
    version="0.1.0",
    docs_url="/docs",  # 仅内网开放
)


@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    """业务异常 → 对应业务码。

    HTTP 状态映射：仅 token 失效类（4011/4012）→ 401（前端 axios 据此触发
    refresh 静默续期）；登录表单层错误（4010 密码错 / 4013 锁定 / 4014 验证码）
    保持 200，避免登录失败误触发刷新链；403x → 403；其余业务码 HTTP 200，
    由响应体 code 区分成败。
    """
    status = 200
    if exc.code in (4011, 4012):
        status = 401
    elif 4030 <= exc.code < 4040:
        status = 403
    return JSONResponse(
        status_code=status,
        content={"code": exc.code, "message": exc.message, "data": exc.data},
    )

# 模块路由（依赖层级顺序：L1 基建在前，L2 主数据、L3 权证依次）
MODULE_ROUTERS = (
    user_router,
    approval_router,
    attachment_router,
    institution_router,
    customer_router,
    warrant_router,
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    """参数校验失败 → 400x，data 携带字段级错误（field -> [messages]）。"""
    errors: dict[str, list[str]] = {}
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", ()) if loc != "body")
        errors.setdefault(field or "__root__", []).append(err.get("msg", "invalid"))
    return JSONResponse(
        status_code=200,
        content={"code": 4001, "message": "参数校验失败", "data": errors},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    """未捕获异常 → 500x，写 error 日志（含 request_id），响应可回溯。"""
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=200,
        content={
            "code": 5001,
            "message": "服务端异常，请联系管理员并提供 X-Request-ID",
            "data": None,
        },
    )


app.add_middleware(RequestIdMiddleware)

# 健康检查 + 业务模块路由
app.include_router(health_router, prefix="/api/v1")
for module_router in MODULE_ROUTERS:
    app.include_router(module_router, prefix="/api/v1")

# 字典聚合路由必须最后注册：/dicts/{name} 通配路由会遮蔽业务模块的
# 单段字典路径（/dicts/tags、/dicts/genders、/dicts/customers 等），
# FastAPI 按注册顺序匹配，先注册业务路由、通配路由兜底。
app.include_router(dict_router, prefix="/api/v1")

# 静态资源（头像等本地上传文件）
MEDIA_ROOT = Path(__file__).resolve().parent.parent / "media"
(MEDIA_ROOT / "avatars").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")
