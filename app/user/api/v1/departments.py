"""部门路由（接口文档 §1 组4）。

注意路由注册顺序：/departments/tree 必须先于 /departments/{id}（FastAPI 按注册序匹配）。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_log
from app.core.db import get_db
from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.response import ok
from app.user.schemas.org import DeptCreate, DeptUpdate
from app.user.services import org_service

router = APIRouter(prefix="/departments", tags=["部门"])


@router.get("")
def dept_tree(ctx: AuthContext = Depends(require_perm("dept:list")),
              db: Session = Depends(get_db)):
    """部门树（带人数/负责人/状态）。"""
    return ok([n.model_dump() for n in org_service.dept_tree(db)])


@router.get("/tree")
def dept_tree_simple(ctx: AuthContext = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """精简部门树（用户分配/筛选下拉用，登录即可）。"""
    return ok([n.model_dump() for n in org_service.dept_tree(db)])


@router.get("/{dept_id}")
def dept_detail(dept_id: int,
                ctx: AuthContext = Depends(require_perm("dept:list")),
                db: Session = Depends(get_db)):
    """部门详情：基础信息 + 在职成员 + 直接下级部门。"""
    return ok(org_service.get_dept_detail(db, dept_id))


@router.post("")
@audit_log(module="dept", action="create", target_type="dept")
def create_dept(req: DeptCreate, request: Request,
                ctx: AuthContext = Depends(require_perm("dept:create")),
                db: Session = Depends(get_db)):
    dept_id = org_service.create_dept(db, req)
    return ok({"id": dept_id})


@router.patch("/{dept_id}")
@audit_log(module="dept", action="update", target_type="dept")
def update_dept(dept_id: int, req: DeptUpdate, request: Request,
                ctx: AuthContext = Depends(require_perm("dept:update")),
                db: Session = Depends(get_db)):
    org_service.update_dept(db, dept_id, req)
    return ok()


@router.delete("/{dept_id}")
@audit_log(module="dept", action="delete", target_type="dept")
def delete_dept(dept_id: int, request: Request,
                ctx: AuthContext = Depends(require_perm("dept:delete")),
                db: Session = Depends(get_db)):
    """删除（拦截：仍有成员/子部门）。"""
    org_service.delete_dept(db, dept_id)
    return ok()
