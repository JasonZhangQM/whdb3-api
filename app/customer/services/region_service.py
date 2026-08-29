"""行业 / 标签字典服务（行政区域已迁至 app/user/services/region_service.py）。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.core.tree import build_tree
from app.customer.models import ExtraTag, Industry


def industry_tree(db: Session) -> list[dict]:
    rows = db.scalars(select(Industry).order_by(Industry.code)).all()
    return build_tree(
        rows,
        parent_getter=lambda r: r.parent_id,
        node_mapper=lambda r: {
            "id": r.id, "code": r.code, "name": r.name,
            "ind_typ": r.ind_typ, "parent_id": r.parent_id,
        },
    )


# ===== 标签 =====

def list_tags(db: Session) -> list[dict]:
    from app.customer.models import CustomerTagRelation
    from app.user.models import User

    rows = db.scalars(select(ExtraTag).order_by(ExtraTag.type, ExtraTag.id)).all()
    # 一条 GROUP BY 批量统计各标签引用数（替代逐行 JSON_CONTAINS，走中间表索引）
    usage = dict(
        db.execute(
            select(CustomerTagRelation.tag_id, func.count())
            .group_by(CustomerTagRelation.tag_id)
        ).all()
    )
    # 批量取创建人姓名（列表尾列展示，避免 N+1）
    creator_ids = {t.created_by for t in rows if t.created_by}
    creator_names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()
    ) if creator_ids else {}
    return [
        {"id": t.id, "name": t.name, "type": t.type,
         "in_use": usage.get(t.id, 0) > 0,
         "created_by_name": creator_names.get(t.created_by) or ""}
        for t in rows
    ]


def list_tag_customers(db: Session, tag_id: int) -> list[dict]:
    """标签下的所有客户（中间表 JOIN，走 customer_id 索引）。"""
    from sqlalchemy import select

    from app.customer.models import Customer, CustomerTagRelation
    from app.user.models import User

    rows = db.execute(
        select(Customer, User.name)
        .join(CustomerTagRelation, CustomerTagRelation.customer_id == Customer.id)
        .outerjoin(User, User.id == Customer.managementor_id)
        .where(CustomerTagRelation.tag_id == tag_id)
        .order_by(Customer.id)
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "short_name": c.short_name,
            "genre": c.genre,
            "custom_state": c.custom_state,
            "classification": c.classification,
            "managementor_name": manager or "",
        }
        for c, manager in rows
    ]


def remove_tag_customer(db: Session, tag_id: int, customer_id: int) -> None:
    """移除单个 标签↔客户 关联（详情抽屉操作列）。"""
    from app.customer.models import CustomerTagRelation

    rel = db.scalar(
        select(CustomerTagRelation).where(
            CustomerTagRelation.tag_id == tag_id,
            CustomerTagRelation.customer_id == customer_id,
        )
    )
    if rel is None:
        raise BizError(4041, "该客户未使用此标签")
    db.delete(rel)


def create_tag(db: Session, name: str, type_: int, user_id: int) -> int:
    dup = db.scalar(select(ExtraTag.id).where(ExtraTag.name == name))
    if dup is not None:
        raise BizError(4091, "标签名已存在")
    t = ExtraTag(name=name, type=type_, created_by=user_id)
    db.add(t)
    db.flush()
    return t.id


def delete_tag(db: Session, tag_id: int) -> None:
    from app.customer.models import CustomerTagRelation

    t = db.get(ExtraTag, tag_id)
    if t is None:
        raise BizError(4041, "标签不存在")
    # 拦截：已被客户使用（中间表计数，走索引）
    used = db.scalar(
        select(func.count())
        .select_from(CustomerTagRelation)
        .where(CustomerTagRelation.tag_id == tag_id)
    )
    if used:
        raise BizError(4091, f"标签已被 {used} 个客户使用，不可删除")
    db.delete(t)


def update_tag(db: Session, tag_id: int, name: str | None, type_: int | None) -> None:
    """编辑标签名称/类型（自由字段：传 None 表示不修改）。"""
    t = db.get(ExtraTag, tag_id)
    if t is None:
        raise BizError(4041, "标签不存在")
    if name is not None and name != t.name:
        dup = db.scalar(select(ExtraTag.id).where(ExtraTag.name == name))
        if dup is not None and dup != tag_id:
            raise BizError(4091, "标签名已存在")
        t.name = name
    if type_ is not None:
        t.type = type_
