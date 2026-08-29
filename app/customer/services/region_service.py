"""行业 / 标签字典服务（行政区域已迁至 app/user/services/region_service.py）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.customer.models import ExtraTag, Industry


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
