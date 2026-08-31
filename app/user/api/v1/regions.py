"""行政区域路由（从 customer/dicts 迁入用户模块，基础数据）。

所有接口均为只读字典类（供业务页面下拉/级联/搜索用），
仅要求登录即可访问，不绑定 region:list 权限——
否则 pm/controler 等业务角色无法使用行政区下拉框。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user
from app.core.db import get_db
from app.core.exceptions import BizError
from app.core.response import ok
from app.user.services import region_service

router = APIRouter(prefix="/regions", tags=["region"])


@router.get("/roots")
def region_roots(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """顶层省级列表（懒加载 TreeSelect 首屏）。"""
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
    """按名称/代码搜索区域（远程搜索下拉框用，限 50 条）。"""
    return ok(region_service.region_search(db, q))


@router.get("/{region_id}")
def region_detail(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """单节点详情（带完整路径，编辑回显用）。"""
    data = region_service.region_detail(db, region_id)
    if data is None:
        raise BizError(4041, "区域不存在")
    return ok(data)


@router.get("/{region_id}/children")
def region_children(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """指定节点直接下级（TreeSelect 懒加载展开子级）。"""
    return ok(region_service.region_children(db, region_id))
