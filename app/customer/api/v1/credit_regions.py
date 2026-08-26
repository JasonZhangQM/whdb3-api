"""授信区域路由：树形区域 + 成员 + 统计（接口 4-10）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result
from app.customer.schemas import CreditRegionCreate, CreditRegionUpdate
from app.customer.services import credit_region_service

router = APIRouter(prefix="/credit-regions", tags=["credit-region"])


@router.get("")
def list_credit_regions(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:list")),
):
    """授信区域树（带额度/已用/成员数）。"""
    return ok(credit_region_service.tree(db))


@router.post("")
def create_credit_region(
    body: CreditRegionCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:create")),
):
    region_id = credit_region_service.create(
        db, body.code, body.name, body.parent_id,
        body.credit_amount, body.platform_name, body.description, user.user_id,
    )
    db.commit()
    return ok({"id": region_id}, message="授信区域已创建")


@router.get("/{region_id}")
def get_credit_region(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """区域详情（成员 Top20 + 实时授信/在保汇总）。"""
    return ok(credit_region_service.get_detail(db, region_id))


@router.patch("/{region_id}")
def update_credit_region(
    region_id: int,
    body: CreditRegionUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:update")),
):
    credit_region_service.update(
        db, region_id, body.name, body.credit_amount,
        body.platform_name, body.description, body.status,
    )
    db.commit()
    return ok(message="修改成功")


@router.delete("/{region_id}")
def delete_credit_region(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:delete")),
):
    """删除区域（拦截：仍有成员客户/子区域）。"""
    credit_region_service.delete(db, region_id)
    db.commit()
    return ok(message="区域已删除")


@router.get("/{region_id}/members")
def list_region_members(
    region_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    items, total = credit_region_service.list_members(db, region_id, page, page_size)
    return page_result(items, total, page, page_size)


@router.get("/{region_id}/stats")
def region_stats(
    region_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:detail")),
):
    """区域授信统计（总额度/已用/在保/五级分类分布）。"""
    return ok(credit_region_service.stats(db, region_id))
