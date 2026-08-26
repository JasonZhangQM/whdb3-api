"""集团服务：树形集团 + 母公司自动加入 + 成员管理。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.customer.enums import Genre
from app.customer.models import Customer, Group


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Customer.group_id, func.count())
        .where(Customer.group_id.is_not(None))
        .group_by(Customer.group_id)
    ).all()
    return dict(rows)


def tree(db: Session) -> list[dict]:
    """集团树（带成员数/在保汇总/母公司名称）。"""
    rows = db.scalars(select(Group).order_by(Group.code)).all()
    counts = _member_counts(db)
    # 母公司名与集团在保汇总
    parent_names = {}
    if rows:
        ids = [r.id for r in rows]
        parent_ids = [r.parent_customer_id for r in rows if r.parent_customer_id]
        if parent_ids:
            parent_rows = db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(parent_ids))
            ).all()
            parent_names = dict(parent_rows)
        # 各集团在保汇总（实时 SUM，作树节点展示）
        sums = dict(
            db.execute(
                select(Customer.group_id, func.coalesce(func.sum(Customer.amount), 0))
                .where(Customer.group_id.in_(ids))
                .group_by(Customer.group_id)
            ).all()
        )
    else:
        sums = {}

    nodes: dict[int, dict] = {}
    roots: list[dict] = []
    for r in rows:
        nodes[r.id] = {
            "id": r.id, "code": r.code, "name": r.name, "parent_id": r.parent_id,
            "parent_customer_id": r.parent_customer_id,
            "parent_customer_name": parent_names.get(r.parent_customer_id or 0),
            "credit_amount": float(r.credit_amount),
            "total_insure_amount": float(sums.get(r.id, 0)),
            "member_count": counts.get(r.id, 0),
            "status": r.status,
            "children": [],
        }
    for r in rows:
        node = nodes[r.id]
        parent = nodes.get(r.parent_id)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


def get_or_404(db: Session, group_id: int) -> Group:
    g = db.get(Group, group_id)
    if g is None:
        raise BizError(4041, "集团不存在")
    return g


def _customer_brief(c: Customer, mname: str) -> dict:
    return {
        "id": c.id, "name": c.name, "short_name": c.short_name,
        "genre": c.genre, "custom_state": c.custom_state,
        "is_core": c.is_core, "is_acceptor": c.is_acceptor,
        "managementor_name": mname,
        "credit_amount": float(c.credit_amount),
        "amount": float(c.amount),
        "classification": c.classification,
    }


def get_detail(db: Session, group_id: int) -> dict:
    from app.user.models import User

    g = get_or_404(db, group_id)
    creator = db.scalar(select(User.name).where(User.id == g.created_by)) or ""
    members = db.execute(
        select(Customer, User.name)
        .join(User, User.id == Customer.managementor_id)
        .where(Customer.group_id == group_id)
        .order_by(Customer.credit_amount.desc())
        .limit(20)
    ).all()

    # 树节点同款字段 + 成员列表
    counts = _member_counts(db)
    detail = {
        "id": g.id, "code": g.code, "name": g.name, "parent_id": g.parent_id,
        "parent_customer_id": g.parent_customer_id,
        "parent_customer_name": None,
        "credit_amount": float(g.credit_amount),
        "total_insure_amount": sum(float(c.amount) for c, _ in members),
        "member_count": counts.get(group_id, 0),
        "status": g.status,
        "children": [],
        "description": g.description,
        "created_by_name": creator,
        "created_at": g.created_at,
        "members": [_customer_brief(c, mname) for c, mname in members],
    }
    if g.parent_customer_id:
        detail["parent_customer_name"] = db.scalar(
            select(Customer.name).where(Customer.id == g.parent_customer_id)
        )
    return detail


def create(db: Session, code: str, name: str, parent_id: int,
           parent_customer_id: int, credit_amount: float,
           description: str | None, user_id: int) -> int:
    # 校验
    dup = db.scalar(select(Group.id).where(Group.code == code))
    if dup is not None:
        raise BizError(4091, "集团编码已存在")
    parent_customer = db.get(Customer, parent_customer_id)
    if parent_customer is None:
        raise BizError(4041, "母公司客户不存在")
    if parent_customer.genre != Genre.COMPANY:
        raise BizError(4001, "母公司必须是企业客户")
    if parent_customer.custom_state == 90:
        raise BizError(4001, "母公司客户已注销")
    if parent_customer.group_id is not None:
        raise BizError(4091, "母公司客户已属于其他集团")
    if parent_id:
        get_or_404(db, parent_id)

    # 写入（事务）：集团 + 母公司自动加入
    g = Group(
        code=code, name=name, parent_id=parent_id,
        parent_customer_id=parent_customer_id,
        credit_amount=credit_amount, description=description,
        status=10, created_by=user_id,
    )
    db.add(g)
    db.flush()
    parent_customer.group_id = g.id
    return g.id


def update(db: Session, group_id: int, name: str, parent_id: int | None,
           credit_amount: float, description: str | None, status: int) -> None:
    g = get_or_404(db, group_id)
    g.name = name
    if parent_id is not None:
        g.parent_id = parent_id
    g.credit_amount = credit_amount
    g.description = description
    g.status = status


def delete(db: Session, group_id: int) -> None:
    g = get_or_404(db, group_id)
    # 拦截：仍有成员企业（母公司除外也不能删——母公司也在成员里）
    member = db.scalar(
        select(Customer.id).where(Customer.group_id == group_id).limit(1)
    )
    if member is not None:
        raise BizError(4091, "集团仍有成员企业，请先移除全部成员（含母公司自动脱离需删除集团）")
    child = db.scalar(select(Group.id).where(Group.parent_id == group_id).limit(1))
    if child is not None:
        raise BizError(4091, "集团存在子集团，不可删除")
    db.delete(g)


def list_members(db: Session, group_id: int, page: int, page_size: int):
    from app.user.models import User

    get_or_404(db, group_id)
    stmt = (
        select(Customer, User.name)
        .join(User, User.id == Customer.managementor_id)
        .where(Customer.group_id == group_id)
        .order_by(Customer.credit_amount.desc())
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return [_customer_brief(c, mname) for c, mname in rows], total


def add_members(db: Session, group_id: int, customer_ids: list[int]) -> int:
    g = get_or_404(db, group_id)
    if g.status != 10:
        raise BizError(4091, "集团已停用")
    added = 0
    for cid in customer_ids:
        c = db.get(Customer, cid)
        if c is None:
            raise BizError(4041, f"客户 {cid} 不存在")
        if c.genre != Genre.COMPANY:
            raise BizError(4001, f"客户 {c.name} 不是企业客户，不可加入集团")
        if c.group_id is not None and c.group_id != group_id:
            raise BizError(4091, f"客户 {c.name} 已属于其他集团")
        if c.group_id != group_id:
            c.group_id = group_id
            added += 1
    return added


def remove_member(db: Session, group_id: int, customer_id: int) -> None:
    g = get_or_404(db, group_id)
    if customer_id == g.parent_customer_id:
        raise BizError(4091, "母公司不可移除，仅可通过删除集团脱离")
    c = db.get(Customer, customer_id)
    if c is None or c.group_id != group_id:
        raise BizError(4041, "该客户不属于本集团")
    c.group_id = None


def group_summary(db: Session, group_id: int) -> dict:
    """集团内成员授信/在保汇总（实时统计）。"""
    get_or_404(db, group_id)
    agg = db.execute(
        select(
            func.count(Customer.id),
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
        ).where(Customer.group_id == group_id)
    ).one()
    return {
        "member_count": agg[0],
        "total_credit_amount": float(agg[1]),
        "total_amount": float(agg[2]),
    }
