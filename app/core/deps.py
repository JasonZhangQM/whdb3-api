"""三层授权依赖：登录态 / 权限点 / 数据范围。

依赖方向说明：core(L0) 调 user 模块(L1) 的 context_service 属逆向引用，
按模块依赖规则 R3 用函数内局部 import，禁止模块顶层 import。
"""

from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import (
    ERR_TOKEN_INVALID,
    ERR_UNAUTHORIZED,
    BizError,
)
from app.core.security import TokenService


@dataclass
class AuthContext:
    """请求级权限上下文（由 context_service 组装，缓存于 Redis）。"""

    user_id: int
    username: str
    role_codes: set[str]
    permission_codes: set[str]
    data_scope: int
    # 三态：None=不追加条件(ALL)；[]=仅本人；[ids]=部门范围
    dept_scope_ids: list[int] | None
    is_super_admin: bool


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> AuthContext:
    """层1 登录态：验签 → 黑名单 → 用户行实时读库（停用即时生效）→ 组装权限上下文。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise BizError(ERR_UNAUTHORIZED, "未认证")
    token = auth.removeprefix("Bearer ")

    try:
        payload = TokenService.verify_access_token(token)
    except jwt.ExpiredSignatureError:
        # 4011 过期：前端据此走静默续期（与 4010 无效严格区分，避免前端死循环）
        raise BizError(4011, "token 已过期") from None

    user_id = int(payload["sub"])

    # R3：core -> user 模块逆向引用，函数内局部 import
    from app.user.services import context_service

    return context_service.load_auth_context(db, user_id)


def require_perm(code: str):
    """层2 权限点：超管短路（对新权限点天然免疫，seed 无需维护全量快照）。"""

    def checker(ctx: AuthContext = Depends(get_current_user)) -> AuthContext:
        if ctx.is_super_admin or code in ctx.permission_codes:
            return ctx
        raise BizError(4030, f"无操作权限: {code}")

    return checker


def _main_column(stmt: Select, name: str):
    """从语句主表取列：兼容 ORM 类属性与 Core Table 两种形态。"""
    entity = stmt.get_final_froms()[0]
    if hasattr(entity, name):  # select(Model) 时 froms 为 ORM 实体
        return getattr(entity, name)
    return entity.c[name]  # select(Table) / 子查询时走 .c 集合


def apply_data_scope_filter(
    stmt: Select,
    ctx: AuthContext,
    owner_field: str = "created_by",
    dept_field: str | None = None,
) -> Select:
    """层3 数据范围：业务模块 service 查询的统一入口。

    - owner_field/dept_field 由调用方传名（各模块归属字段命名不同，收口在参数）
    - 三态语义：None 不追加 / [] 仅本人 / [ids] 部门 IN
    """
    if ctx.is_super_admin or ctx.data_scope == 40:  # DataScope.ALL
        return stmt

    if ctx.data_scope == 10:  # DataScope.SELF：仅本人
        return stmt.filter(_main_column(stmt, owner_field) == ctx.user_id)

    if ctx.dept_scope_ids:  # [ids]：部门范围
        field = dept_field or "dept_id"
        return stmt.filter(_main_column(stmt, field).in_(ctx.dept_scope_ids))

    return stmt  # dept_scope_ids 为空列表且非 SELF（如无部门用户）：不追加
