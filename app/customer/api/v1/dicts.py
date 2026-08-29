"""字典路由：行业 / 标签 / 客户下拉字典（行政区域已迁至 user 模块 /regions）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.customer.schemas import TagCreate
from app.customer.services import credit_region_service, customer_service, region_service

router = APIRouter(prefix="/dicts", tags=["customer-dict"])


# ===== 行业 / 标签 =====

@router.get("/industries/tree")
def industries_tree(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """行业分类树。"""
    return ok(region_service.industry_tree(db))


@router.get("/tags")
def list_tags(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """行业/业务标签字典（含 in_use 引用标记）。"""
    return ok(region_service.list_tags(db))


@router.get("/tags/{tag_id}/customers")
def list_tag_customers(
    tag_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """标签下的所有客户（详情抽屉 Tab 用）。"""
    return ok(region_service.list_tag_customers(db, tag_id))


@router.delete("/tags/{tag_id}/customers/{customer_id}")
def remove_tag_customer(
    tag_id: int,
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """移除 标签↔客户 关联（详情抽屉操作列）。"""
    region_service.remove_tag_customer(db, tag_id, customer_id)
    db.commit()
    return ok(message="已移除该客户的标签关联")


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


@router.put("/tags/{tag_id}")
def update_tag(
    tag_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    """编辑标签（name/type 自由字段，留 None 保持不变）。"""
    name = body.get("name")
    type_ = body.get("type")
    region_service.update_tag(db, tag_id, name, type_)
    db.commit()
    return ok(message="标签已更新")


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
