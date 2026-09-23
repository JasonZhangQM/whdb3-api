"""操作审计 AOP 装饰器（详设 §7）。

用法：路由层写接口声明式标注，业务零侵入。

    @router.post("/users")
    @audit_log(module="user", action="create", target_type="user")
    def create_user(req: UserCreate, ctx: AuthContext = Depends(require_perm(...)), request: Request, ...):

约定：被装饰端点的参数名固定识别 `ctx`（AuthContext）与 `request`（Request）。
日志用独立会话写入（业务事务回滚不丢审计轨迹），失败仅告警不影响业务。
core(L0) -> user 模块模型属逆向引用，按规则 R3 函数内局部 import。
"""

import functools
import logging

from fastapi import Request

from app.core.deps import AuthContext
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

STATUS_SUCCESS = 10
STATUS_FAILED = 20


def _write_log(**kwargs) -> None:
    """独立会话落库，容错（审计失败不阻断业务响应）。

    锁等待上限 3 秒：业务失败路径下，业务会话 savepoint 回滚只还原数据、
    行锁仍留在外层事务里，审计 INSERT 曾因此等满 innodb_lock_wait_timeout
    (默认 50s) 把用户响应拖到前端超时。SET SESSION 用后恢复 DEFAULT，
    避免该连接回池后带 3s 锁超时污染其他业务查询。
    """
    from sqlalchemy import text

    try:
        # R3：core -> user 逆向引用，函数内局部 import
        from app.core.db import SessionLocal
        from app.user.models import OperationLog

        with SessionLocal() as db:
            db.execute(text("SET SESSION innodb_lock_wait_timeout = 3"))
            try:
                db.add(OperationLog(**kwargs))
                db.commit()
            finally:
                try:
                    db.rollback()  # 提交失败时清会话状态；成功时无事务为 no-op
                    db.execute(text("SET SESSION innodb_lock_wait_timeout = DEFAULT"))
                except Exception:
                    pass
    except Exception:
        logger.warning("audit log write failed", exc_info=True)


def audit_log(module: str, action: str, target_type: str | None = None):
    """记录一次写操作：操作人/对象/请求元数据/成败。"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            ctx: AuthContext | None = kwargs.get("ctx")
            request: Request | None = kwargs.get("request")
            base = dict(
                user_id=ctx.user_id if ctx else None,
                username=ctx.username if ctx else None,
                user_name=getattr(ctx, "_display_name", None),
                module=module,
                action=action,
                target_type=target_type,
                method=request.method if request else None,
                path=request.url.path if request else None,
                ip=request.client.host if request and request.client else None,
                user_agent=request.headers.get("user-agent") if request else None,
            )
            try:
                result = func(*args, **kwargs)
            except BizError as e:
                # 业务失败也留痕（message 携带失败原因）
                _write_log(**base, status=STATUS_FAILED, message=e.message)
                raise
            # target_id 从返回值取约定字段（各端点返回 ok(data)，data 含 id 即记）
            target_id = None
            data = getattr(result, "get", lambda *_: None)("data")
            if isinstance(data, dict):
                target_id = str(data.get("id")) if data.get("id") is not None else None
            _write_log(**base, status=STATUS_SUCCESS, target_id=target_id)
            return result

        return wrapper

    return decorator
