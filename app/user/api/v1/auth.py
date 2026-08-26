"""认证路由：登录 / 刷新 / 登出 / 验证码 / 权限码（接口文档 §1 组1，白名单）。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import AuthContext, get_current_user
from app.core.response import ok
from app.user.models import Permission
from app.user.schemas.auth import LoginReq, RefreshReq
from app.user.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login")
def login(req: LoginReq, request: Request, db: Session = Depends(get_db)):
    """账号密码登录（三层保护：验证码 → 滑窗锁定 → 密码）。"""
    result = auth_service.login(
        db, req, _client_ip(request), request.headers.get("user-agent")
    )
    return ok(result)


@router.get("/codes")
def my_access_codes(ctx: AuthContext = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """当前用户权限码（vben 按钮级 access codes；超管返回全量）。"""
    if ctx.is_super_admin:
        return ok(list(db.scalars(select(Permission.code).order_by(Permission.id))))
    return ok(sorted(ctx.permission_codes))


@router.post("/refresh")
def refresh(req: RefreshReq, request: Request, db: Session = Depends(get_db)):
    """旋转式刷新：旧 refresh 作废，签发新 token 对。"""
    pair = auth_service.refresh(
        db, req.refresh_token, _client_ip(request), request.headers.get("user-agent")
    )
    return ok(pair)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """登出：access 进黑名单 + 删除 refresh。幂等——无 token / token 已失效也返回成功。"""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if token:
        auth_service.logout(db, token, _client_ip(request),
                            request.headers.get("user-agent"))
    return ok()


@router.get("/captcha")
def captcha():
    """图形验证码（SVG，一次性，TTL 120s）。"""
    return ok(auth_service.generate_captcha())
