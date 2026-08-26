"""角色路由（接口文档 §1 组5）。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_log
from app.core.db import get_db
from app.core.deps import AuthContext, require_perm
from app.core.response import ok
from app.user.schemas.org import (
    RoleCreate,
    RolePermAssignReq,
    RoleUpdate,
    RoleUserAssignReq,
)
from app.user.services import org_service

router = APIRouter(prefix="/roles", tags=["角色"])


@router.get("")
def list_roles(ctx: AuthContext = Depends(require_perm("role:list")),
               db: Session = Depends(get_db)):
    """角色列表（含用户数/权限数/内置标记）。"""
    return ok([r.model_dump() for r in org_service.list_roles(db)])


@router.post("")
@audit_log(module="role", action="create", target_type="role")
def create_role(req: RoleCreate, request: Request,
                ctx: AuthContext = Depends(require_perm("role:create")),
                db: Session = Depends(get_db)):
    role_id = org_service.create_role(db, req)
    return ok({"id": role_id})


@router.get("/{role_id}")
def role_detail(role_id: int,
                ctx: AuthContext = Depends(require_perm("role:list")),
                db: Session = Depends(get_db)):
    """角色详情：权限码列表 + 绑定用户。"""
    return ok(org_service.get_role_detail(db, role_id).model_dump())


@router.patch("/{role_id}")
@audit_log(module="role", action="update", target_type="role")
def update_role(role_id: int, req: RoleUpdate, request: Request,
                ctx: AuthContext = Depends(require_perm("role:update")),
                db: Session = Depends(get_db)):
    """修改角色（内置角色仅允许改 name/description/data_scope）。"""
    org_service.update_role(db, role_id, req)
    return ok()


@router.delete("/{role_id}")
@audit_log(module="role", action="delete", target_type="role")
def delete_role(role_id: int, request: Request,
                ctx: AuthContext = Depends(require_perm("role:delete")),
                db: Session = Depends(get_db)):
    """删除（仅非内置；拦截：仍有用户绑定）。"""
    org_service.delete_role(db, role_id)
    return ok()


@router.put("/{role_id}/permissions")
@audit_log(module="role", action="assign_perm", target_type="role")
def assign_role_perms(role_id: int, req: RolePermAssignReq, request: Request,
                      ctx: AuthContext = Depends(require_perm("role:assign")),
                      db: Session = Depends(get_db)):
    """全量替换角色权限（提交后批量失效绑定用户权限缓存）。"""
    org_service.assign_role_perms(db, role_id, req.permission_ids)
    return ok()


@router.put("/{role_id}/users")
@audit_log(module="role", action="assign_user", target_type="role")
def assign_role_users(role_id: int, req: RoleUserAssignReq, request: Request,
                      ctx: AuthContext = Depends(require_perm("role:assign")),
                      db: Session = Depends(get_db)):
    """批量给角色绑定用户（增量）。"""
    org_service.assign_role_users(db, role_id, req.user_ids)
    return ok()
