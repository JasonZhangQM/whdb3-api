"""授信区域服务：树形区域 + 额度统计 + 成员管理。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.core.tree import build_tree
from app.customer.models import CreditRegion, Customer


def _node_fields(r: CreditRegion, member_count: int) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "parent_id": r.parent_id,
        "platform_name": r.platform_name,
        "credit_amount": float(r.credit_amount),
        "used_amount": float(r.used_amount),
        "member_count": member_count,
        "status": r.status,
    }


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Customer.credit_region_id, func.count())
        .where(Customer.credit_region_id.is_not(None))
        .group_by(Customer.credit_region_id)
    ).all()
    return dict(rows)


def tree(db: Session) -> list[dict]:
    """授信区域树（带额度/已用/成员数）。"""
    rows = db.scalars(select(CreditRegion).order_by(CreditRegion.code)).all()
    counts = _member_counts(db)
    return build_tree(
        rows,
        parent_getter=lambda r: r.parent_id,
        node_mapper=lambda r: _node_fields(r, counts.get(r.id, 0)),
    )


def get_or_404(db: Session, region_id: int) -> CreditRegion:
    r = db.get(CreditRegion, region_id)
    if r is None:
        raise BizError(4041, "授信区域不存在")
    return r


def get_detail(db: Session, region_id: int) -> dict:
    from app.user.models import User

    r = get_or_404(db, region_id)
    creator = db.scalar(select(User.name).where(User.id == r.created_by)) or ""
    # 成员 Top 20 + 授信/在保汇总（实时统计）
    members = db.execute(
        select(Customer, User.name)
        .join(User, User.id == Customer.managementor_id)
        .where(Customer.credit_region_id == region_id)
        .order_by(Customer.credit_amount.desc())
        .limit(20)
    ).all()
    agg = db.execute(
        select(
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
            func.count(Customer.id),
        ).where(Customer.credit_region_id == region_id)
    ).one()

    detail = _node_fields(r, agg[2])
    detail.update(
        {
            "children": [],
            "description": r.description,
            "created_by_name": creator,
            "created_at": r.created_at,
            "members": [
                {
                    "id": c.id, "name": c.name, "short_name": c.short_name,
                    "genre": c.genre,
                    "managementor_name": mname,
                    "credit_amount": float(c.credit_amount),
                    "amount": float(c.amount),
                    "classification": c.classification,
                }
                for c, mname in members
            ],
            "total_credit_amount": float(agg[0]),
            "total_amount": float(agg[1]),
        }
    )
    return detail


def create(db: Session, code: str, name: str, parent_id: int | None,
           credit_amount: float, platform_name: str | None,
           description: str | None, user_id: int) -> int:
    dup = db.scalar(select(CreditRegion.id).where(CreditRegion.code == code))
    if dup is not None:
        raise BizError(4091, "区域编码已存在")
    if parent_id:
        get_or_404(db, parent_id)
    r = CreditRegion(
        code=code, name=name, parent_id=parent_id or None,
        credit_amount=credit_amount, platform_name=platform_name,
        description=description, status=10, created_by=user_id,
    )
    db.add(r)
    db.flush()
    return r.id


def update(db: Session, region_id: int, name: str, credit_amount: float,
           platform_name: str | None, description: str | None, status: int) -> None:
    r = get_or_404(db, region_id)
    r.name = name
    r.credit_amount = credit_amount
    r.platform_name = platform_name
    r.description = description
    r.status = status


def delete(db: Session, region_id: int) -> None:
    r = get_or_404(db, region_id)
    # 拦截：仍有成员客户 / 子区域
    member = db.scalar(
        select(Customer.id).where(Customer.credit_region_id == region_id).limit(1)
    )
    if member is not None:
        raise BizError(4091, "区域仍有成员客户，不可删除")
    child = db.scalar(
        select(CreditRegion.id).where(CreditRegion.parent_id == region_id).limit(1)
    )
    if child is not None:
        raise BizError(4091, "区域存在子区域，不可删除")
    db.delete(r)


def list_members(db: Session, region_id: int, page: int, page_size: int):
    from app.user.models import User

    get_or_404(db, region_id)
    stmt = (
        select(Customer, User.name)
        .join(User, User.id == Customer.managementor_id)
        .where(Customer.credit_region_id == region_id)
        .order_by(Customer.credit_amount.desc())
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        {
            "id": c.id, "name": c.name, "short_name": c.short_name,
            "genre": c.genre,
            "managementor_name": mname,
            "credit_amount": float(c.credit_amount),
            "amount": float(c.amount),
            "classification": c.classification,
        }
        for c, mname in rows
    ]
    return items, total


def stats(db: Session, region_id: int) -> dict:
    """区域授信统计：总额度/已用/成员授信/在保/五级分类分布。"""
    from app.customer.enums import LABELS

    r = get_or_404(db, region_id)
    agg = db.execute(
        select(
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
            func.count(Customer.id),
        ).where(Customer.credit_region_id == region_id)
    ).one()
    cls_rows = db.execute(
        select(Customer.classification, func.count())
        .where(Customer.credit_region_id == region_id)
        .group_by(Customer.classification)
    ).all()
    return {
        "credit_amount": float(r.credit_amount),
        "used_amount": float(r.used_amount),
        "total_credit_amount": float(agg[0]),
        "total_amount": float(agg[1]),
        "member_count": agg[2],
        "classification_distribution": {
            LABELS["classification"].get(c, str(c)): n for c, n in cls_rows
        },
    }


def recalc_used_amount(db: Session, region_id: int) -> None:
    """刷新区域已用额度缓存（客户授信变更事件触发，异步容错）。"""
    r = db.get(CreditRegion, region_id)
    if r is None:
        return
    total = db.scalar(
        select(func.coalesce(func.sum(Customer.credit_amount), 0)).where(
            Customer.credit_region_id == region_id
        )
    )
    r.used_amount = float(total or 0)
