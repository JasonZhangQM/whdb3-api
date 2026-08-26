"""行政区域 / 行业 / 标签字典服务。"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.customer.enums import LABELS
from app.customer.models import ExtraTag, Industry, Region


def region_tree(db: Session) -> list[dict]:
    """全量区域树：一次性查出，Python 侧 O(n) 组装（约几千条）。"""
    rows = db.scalars(
        select(Region).where(Region.status == 10).order_by(Region.code)
    ).all()
    nodes: dict[int, dict] = {}
    roots: list[dict] = []
    for r in rows:
        nodes[r.id] = {
            "id": r.id, "code": r.code, "name": r.name,
            "level": r.level, "parent_id": r.parent_id, "children": [],
        }
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_id)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def region_children(db: Session, region_id: int) -> list[dict]:
    rows = db.scalars(
        select(Region)
        .where(Region.parent_id == region_id, Region.status == 10)
        .order_by(Region.ordery, Region.code)
    ).all()
    return [
        {"id": r.id, "code": r.code, "name": r.name, "level": r.level,
         "parent_id": r.parent_id}
        for r in rows
    ]


def region_search(db: Session, q: str) -> list[dict]:
    """按名称/代码搜索区域。"""
    like = f"%{q}%"
    rows = db.scalars(
        select(Region)
        .where(or_(Region.name.like(like), Region.code.like(like)))
        .order_by(Region.code)
        .limit(50)
    ).all()
    return [
        {"id": r.id, "code": r.code, "name": r.name, "level": r.level,
         "level_display": LABELS["region_level"].get(r.level),
         "parent_id": r.parent_id}
        for r in rows
    ]


def industry_tree(db: Session) -> list[dict]:
    rows = db.scalars(select(Industry).order_by(Industry.code)).all()
    nodes: dict[int, dict] = {}
    roots: list[dict] = []
    for r in rows:
        nodes[r.id] = {
            "id": r.id, "code": r.code, "name": r.name,
            "ind_typ": r.ind_typ, "parent_id": r.parent_id, "children": [],
        }
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_id)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


# ===== 标签 =====

def list_tags(db: Session) -> list[dict]:
    from sqlalchemy import func

    from app.customer.models import Customer

    rows = db.scalars(select(ExtraTag).order_by(ExtraTag.type, ExtraTag.id)).all()
    items = []
    for t in rows:
        # in_use：customers.tags JSON 数组是否引用该标签 id
        used = db.scalar(
            select(func.count())
            .select_from(Customer)
            .where(func.json_contains(Customer.tags, str(t.id)))
        )
        items.append(
            {"id": t.id, "name": t.name, "type": t.type, "status": t.status,
             "in_use": bool(used)}
        )
    return items


def create_tag(db: Session, name: str, type_: int, user_id: int) -> int:
    dup = db.scalar(select(ExtraTag.id).where(ExtraTag.name == name))
    if dup is not None:
        raise BizError(4091, "标签名已存在")
    t = ExtraTag(name=name, type=type_, status=10, created_by=user_id)
    db.add(t)
    db.flush()
    return t.id


def delete_tag(db: Session, tag_id: int) -> None:
    from sqlalchemy import func

    from app.customer.models import Customer

    t = db.get(ExtraTag, tag_id)
    if t is None:
        raise BizError(4041, "标签不存在")
    # 拦截：已被客户使用
    used = db.scalar(
        select(func.count())
        .select_from(Customer)
        .where(func.json_contains(Customer.tags, str(tag_id)))
    )
    if used:
        raise BizError(4091, f"标签已被 {used} 个客户使用，不可删除")
    db.delete(t)
