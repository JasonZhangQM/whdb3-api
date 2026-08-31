"""字典路由：前端下拉数据源（接口文档 §1 组8）。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import AuthContext, get_current_user
from app.core.response import ok
from app.user.enums import LABELS
from app.user.services import org_service

router = APIRouter(prefix="/dicts", tags=["字典"])


@router.get("/genders")
def genders(ctx: AuthContext = Depends(get_current_user)):
    return ok([{"value": v, "label": t} for v, t in LABELS["gender"].items()])


@router.get("/user-statuses")
def user_statuses(ctx: AuthContext = Depends(get_current_user)):
    return ok([{"value": v, "label": t} for v, t in LABELS["user_status"].items()])


@router.get("/data-scopes")
def data_scopes(ctx: AuthContext = Depends(get_current_user)):
    return ok([{"value": v, "label": t} for v, t in LABELS["data_scope"].items()])


@router.get("/positions")
def positions(dept_id: int | None = None,
              ctx: AuthContext = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """职务字典：取在职用户 distinct position（M1 动态来源；seed 扩展后可换静态表）。"""
    from app.user.models import User
    from app.user.enums import UserStatus

    stmt = select(User.position).where(
        User.status == UserStatus.ACTIVE.value, User.position.isnot(None)
    ).distinct()
    if dept_id:
        stmt = stmt.where(User.dept_id == dept_id)
    return ok(sorted(db.scalars(stmt).all()))


@router.get("/users")
def user_options(dept_id: int | None = None, position: str | None = None,
                 role: str | None = None,
                 ctx: AuthContext = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """员工下拉（在职，按部门/职务/角色 code 筛选）。role 传角色 code 如 pm/controler。"""
    return ok(org_service.list_user_options(db, dept_id, position, role))
