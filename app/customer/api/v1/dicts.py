"""字典路由：行政区域 / 行业 / 标签 / 客户下拉字典（接口 1-3, 11-14, 23）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.customer.schemas import TagCreate
from app.customer.services import credit_region_service, customer_service, region_service

router = APIRouter(prefix="/dicts", tags=["customer-dict"])


# ===== 行政区域 =====

@router.get("/regions/tree")
def regions_tree(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """行政区域全量树（Redis 缓存 1 小时，前端级联全量模式）。"""
    return ok(region_service.region_tree(db))


@router.get("/regions/search")
def regions_search(
    q: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """按名称/代码搜索区域（限 50 条）。"""
    return ok(region_service.region_search(db, q))


@router.get("/regions/{region_id}/children")
def region_children(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """指定节点直接下级（级联选择器懒加载）。"""
    return ok(region_service.region_children(db, region_id))


# ===== 行业 / 标签 =====

@router.get("/industries/tree")
def industries_tree(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """行业分类树。"""
    return ok(region_service.industry_tree(db))


@router.get("/tags")
def list_tags(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """行业/业务标签字典（含 in_use 引用标记）。"""
    return ok(region_service.list_tags(db))


@router.post("/tags")
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:update")),
):
    """新增标签（管理员类操作，借 customer:update 权限点）。"""
    tag_id = region_service.create_tag(db, body.name, body.type, user.user_id)
    db.commit()
    return ok({"id": tag_id}, message="标签已创建")


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """删除标签（拦截：已被客户使用）。"""
    region_service.delete_tag(db, tag_id)
    db.commit()
    return ok(message="标签已删除")


# ===== 客户下拉字典 =====

@router.get("/customers")
def customers_dict(
    genre: int | None = None,
    is_core: bool | None = None,
    is_acceptor: bool | None = None,
    managementor_id: int | None = None,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """客户下拉字典（表单选择用，按类型/经理/核心/承兑人筛选）。"""
    return ok(customer_service.customer_dict(db, genre, is_core, is_acceptor, managementor_id))


# ===== 授信区域（挂在 /dicts 下供下拉，管理接口见 credit_regions.py）=====

@router.get("/credit-regions/tree")
def credit_regions_tree(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """授信区域树（下拉选择用）。"""
    return ok(credit_region_service.tree(db))
