"""集团路由：树形集团 + 成员管理（接口 15-22）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result
from app.customer.schemas import GroupCreate, GroupMemberAddReq, GroupUpdate
from app.customer.services import group_service

router = APIRouter(prefix="/customer-groups", tags=["customer-group"])


@router.get("")
def list_groups(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """集团树（下拉字典用，带成员数/在保汇总/母公司名称）。"""
    return ok(group_service.tree(db))


@router.post("")
def create_group(
    body: GroupCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("customer:group_list")),
):
    """新建集团（母公司自动加入成员）。"""
    group_id = group_service.create(
        db, body.code, body.name, body.parent_id,
        body.parent_customer_id, body.credit_amount,
        body.description, user.user_id,
    )
    db.commit()
    return ok({"id": group_id}, message="集团已创建")


@router.get("/{group_id}")
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    """集团详情（成员 Top20 + 授信/在保汇总）。"""
    return ok(group_service.get_detail(db, group_id))


@router.patch("/{group_id}")
def update_group(
    group_id: int,
    body: GroupUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    group_service.update(
        db, group_id, body.name, body.parent_id,
        body.parent_customer_id, body.credit_amount,
        body.description,
    )
    db.commit()
    return ok(message="修改成功")


@router.delete("/{group_id}")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    """删除集团（拦截：仍有成员/子集团）。"""
    group_service.delete(db, group_id)
    db.commit()
    return ok(message="集团已删除")


@router.get("/{group_id}/members")
def list_group_members(
    group_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    items, total = group_service.list_members(db, group_id, page, page_size)
    return page_result(items, total, page, page_size)


@router.post("/{group_id}/members")
def add_group_members(
    group_id: int,
    body: GroupMemberAddReq,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    """批量加入成员企业（拦截：非企业客户/已属其他集团）。"""
    added = group_service.add_members(db, group_id, body.customer_ids)
    db.commit()
    return ok({"added": added}, message=f"已加入 {added} 家成员企业")


@router.delete("/{group_id}/members/{customer_id}")
def remove_group_member(
    group_id: int,
    customer_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("customer:group_list")),
):
    """移除成员企业（母公司不可移除）。"""
    group_service.remove_member(db, group_id, customer_id)
    db.commit()
    return ok(message="已移除")
