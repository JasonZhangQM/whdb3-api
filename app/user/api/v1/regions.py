"""行政区域路由（从 customer/dicts 迁入用户模块，基础数据）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.user.services import region_service

router = APIRouter(prefix="/regions", tags=["region"])


@router.get("/roots")
def region_roots(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("region:list")),
):
    """顶层省级列表（树形表格首屏）。"""
    return ok(region_service.region_roots(db))


@router.get("/tree")
def regions_tree(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """行政区域全量树（前端级联选择器全量模式）。"""
    return ok(region_service.region_tree(db))


@router.get("/search")
def regions_search(
    q: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """按名称/代码搜索区域（限 50 条）。"""
    return ok(region_service.region_search(db, q))


@router.get("/{region_id}/children")
def region_children(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """指定节点直接下级（树形表格展开懒加载）。"""
    return ok(region_service.region_children(db, region_id))
