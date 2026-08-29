"""用户路由：个人中心 + 用户管理（接口文档 §1 组2/组3）。"""

import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.audit import audit_log
from app.core.db import get_db
from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.exceptions import BizError
from app.core.response import ok
from app.core.response import page as page_result
from app.user.schemas.auth import (
    ChangePasswordReq,
    ProfileUpdateReq,
    ResetPasswordReq,
)
from app.user.schemas.user import (
    RoleAssignReq,
    TransferReq,
    UserCreate,
    UserStatusReq,
    UserUpdate,
)
from app.user.services import auth_service, menu_service, user_service

router = APIRouter(prefix="/users", tags=["用户"])

# 头像上传约束
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
                "image/webp": ".webp"}
MEDIA_AVATARS = "media/avatars"


# ================= 个人中心（登录即可） =================

@router.get("/me")
def get_my_profile(ctx: AuthContext = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """一次性返回完整权限上下文（信息/角色/权限码/菜单树/数据范围）。"""
    return ok(user_service.get_my_profile(db, ctx))


@router.patch("/me")
def update_my_profile(req: ProfileUpdateReq,
                      ctx: AuthContext = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """修改本人基础信息（白名单字段，不含角色/部门/权限）。"""
    user_service.update_my_profile(db, ctx, req)
    return ok(user_service.get_my_profile(db, ctx))


@router.post("/me/avatar")
def upload_avatar(file: UploadFile = File(...),
                  ctx: AuthContext = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """头像上传：本地存储 media/avatars/，返回 URL。"""
    ext = AVATAR_TYPES.get(file.content_type or "")
    if ext is None:
        raise BizError(4001, "仅支持 png/jpg/gif/webp 格式")
    content = file.file.read(AVATAR_MAX_BYTES + 1)
    if len(content) > AVATAR_MAX_BYTES:
        raise BizError(4001, "头像不能超过 2MB")

    from pathlib import Path

    dir_path = Path(__file__).resolve().parents[4] / MEDIA_AVATARS
    dir_path.mkdir(parents=True, exist_ok=True)
    filename = f"{ctx.user_id}_{uuid.uuid4().hex[:8]}{ext}"
    (dir_path / filename).write_bytes(content)

    url = f"/media/avatars/{filename}"
    user_service.update_my_profile(db, ctx, ProfileUpdateReq(avatar_url=url))
    return ok({"url": url})


@router.patch("/me/password")
def change_my_password(req: ChangePasswordReq,
                       ctx: AuthContext = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """修改本人密码：校验旧密 + 策略 + 踢出全部会话。"""
    from app.user.models import User

    user = db.get(User, ctx.user_id)
    if user is None:
        raise BizError(4041, "用户不存在")
    auth_service.change_my_password(db, user, req.old_password, req.new_password)
    return ok()


@router.get("/me/menus")
def my_menus(ctx: AuthContext = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """vben 后端路由协议菜单树（裁决 6：独立接口，动态路由专用）。"""
    return ok(menu_service.vben_route_tree(db, ctx))


# ================= 用户管理（权限点） =================

@router.get("")
def list_users(page: int = 1, page_size: int = 20, q: str | None = None,
               status: int | None = None, dept_id: int | None = None,
               position: str | None = None, role: str | None = None,
               ctx: AuthContext = Depends(require_perm("user:list")),
               db: Session = Depends(get_db)):
    """用户列表（data_scope 过滤 + 分页；role 按角色 code 过滤，如 pm/controler）。"""
    items, total = user_service.list_users(
        db, ctx, page, page_size, q=q, status=status, dept_id=dept_id,
        position=position, role=role,
    )
    return page_result([i.model_dump() for i in items], total, page, page_size)


@router.post("")
@audit_log(module="user", action="create", target_type="user")
def create_user(req: UserCreate, request: Request,
                ctx: AuthContext = Depends(require_perm("user:create")),
                db: Session = Depends(get_db)):
    """新增用户：默认密码/随机密码 + 首登强制改密。"""
    result = user_service.create(db, req)
    return ok(result)


@router.get("/{user_id}")
def get_user(user_id: int,
             ctx: AuthContext = Depends(require_perm("user:list")),
             db: Session = Depends(get_db)):
    """用户详情（角色/部门/最近操作）。"""
    return ok(user_service.get_detail(db, user_id).model_dump())


@router.patch("/{user_id}")
@audit_log(module="user", action="update", target_type="user")
def update_user(user_id: int, req: UserUpdate, request: Request,
                ctx: AuthContext = Depends(require_perm("user:update")),
                db: Session = Depends(get_db)):
    """修改用户（超管互改边界校验在 service）。"""
    user_service.update(db, ctx, user_id, req)
    return ok()


@router.delete("/{user_id}")
@audit_log(module="user", action="delete", target_type="user")
def delete_user(user_id: int, request: Request,
                ctx: AuthContext = Depends(require_perm("user:delete")),
                db: Session = Depends(get_db)):
    """逻辑删除（停用）；超管账号不可删。"""
    if ctx.is_super_admin and user_id == ctx.user_id:
        raise BizError(4091, "不可删除当前登录账号")
    user_service.delete(db, ctx, user_id)
    return ok()


@router.patch("/{user_id}/status")
@audit_log(module="user", action="update", target_type="user_status")
def change_user_status(user_id: int, req: UserStatusReq, request: Request,
                       ctx: AuthContext = Depends(require_perm("user:update")),
                       db: Session = Depends(get_db)):
    """启用/停用/离职（停用即踢出会话）。"""
    user_service.change_status(db, ctx, user_id, req)
    return ok()


@router.post("/{user_id}/password")
@audit_log(module="user", action="reset_pwd", target_type="user")
def reset_password(user_id: int, req: ResetPasswordReq, request: Request,
                   ctx: AuthContext = Depends(require_perm("user:reset_pwd")),
                   db: Session = Depends(get_db)):
    """管理员重置密码：默认随机生成并返回，强制下次改密。"""
    raw = user_service.reset_password(db, user_id, req.new_password)
    return ok({"initial_password": raw})


@router.put("/{user_id}/roles")
@audit_log(module="user", action="assign_role", target_type="user")
def assign_roles(user_id: int, req: RoleAssignReq, request: Request,
                 ctx: AuthContext = Depends(require_perm("user:assign_role")),
                 db: Session = Depends(get_db)):
    """全量替换用户角色（触发权限缓存失效）。"""
    user_service.assign_roles(db, ctx, user_id, req.role_ids)
    return ok()


@router.post("/{user_id}/transfer")
@audit_log(module="user", action="transfer", target_type="user")
def transfer(user_id: int, req: TransferReq, request: Request,
             ctx: AuthContext = Depends(require_perm("user:transfer")),
             db: Session = Depends(get_db)):
    """批量移交该用户名下业务资源（M1 骨架，业务模块接入点 M2+）。"""
    report = user_service.transfer(db, ctx, user_id, req)
    return ok(report.model_dump())
