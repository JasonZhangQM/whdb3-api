"""权限与菜单路由（接口文档 §1 组6）。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_log
from app.core.db import get_db
from app.core.deps import AuthContext, require_perm
from app.core.response import ok
from app.user.schemas.org import MenuCreate, MenuUpdate
from app.user.services import org_service

router = APIRouter(tags=["权限与菜单"])


@router.get("/permissions")
def list_permissions(ctx: AuthContext = Depends(require_perm("menu:list")),
                     db: Session = Depends(get_db)):
    """全部权限清单（按模块分组用，前端配置页）。"""
    return ok(org_service.list_permissions(db))


@router.get("/menus")
def list_menus(ctx: AuthContext = Depends(require_perm("menu:list")),
               db: Session = Depends(get_db)):
    """全部菜单树（配置页用，含按钮）。"""
    return ok(org_service.list_menus(db))


@router.post("/menus")
@audit_log(module="menu", action="create", target_type="menu")
def create_menu(req: MenuCreate, request: Request,
                ctx: AuthContext = Depends(require_perm("menu:create")),
                db: Session = Depends(get_db)):
    """新增菜单/目录/按钮（自动生成对应 permission_code + 权限点）。"""
    menu_id = org_service.create_menu(db, req)
    return ok({"id": menu_id})


@router.patch("/menus/{menu_id}")
@audit_log(module="menu", action="update", target_type="menu")
def update_menu(menu_id: int, req: MenuUpdate, request: Request,
                ctx: AuthContext = Depends(require_perm("menu:update")),
                db: Session = Depends(get_db)):
    org_service.update_menu(db, menu_id, req)
    return ok()


@router.delete("/menus/{menu_id}")
@audit_log(module="menu", action="delete", target_type="menu")
def delete_menu(menu_id: int, request: Request,
                ctx: AuthContext = Depends(require_perm("menu:delete")),
                db: Session = Depends(get_db)):
    """删除（子级联动删；菜单权限已被角色引用则拦截）。"""
    org_service.delete_menu(db, menu_id)
    return ok()
