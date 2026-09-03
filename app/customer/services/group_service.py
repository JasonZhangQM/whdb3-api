"""集团服务：树形集团 + 母公司自动加入 + 成员管理。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.core.tree import build_tree
from app.customer.enums import Genre
from app.customer.models import Customer, Group


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Customer.group_id, func.count())
        .where(Customer.group_id.is_not(None))
        .group_by(Customer.group_id)
    ).all()
    return dict(rows)


def _children_map(db: Session) -> dict[int, list[int]]:
    """集团 parent_id → children id 映射（一次查询，供子树聚合复用）。

    先 flush：SessionLocal autoflush=False，session 中未落库的
    parent_id 变更（如同事务内先挂父子再反向挂）若不 flush，
    防环校验会读到旧树导致漏判。
    """
    db.flush()
    result: dict[int, list[int]] = {}
    for pid, cid in db.execute(select(Group.parent_id, Group.id)).all():
        result.setdefault(pid, []).append(cid)
    return result


def _subtree_ids(children_map: dict[int, list[int]], root: int) -> list[int]:
    """root 自身 + 全部子孙集团 id（BFS；visited 防脏数据成环时死循环）。"""
    ids = [root]
    seen = {root}
    queue = [root]
    while queue:
        for cid in children_map.get(queue.pop(0), []):
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
                queue.append(cid)
    return ids


def _summary(db: Session, group_id: int) -> dict:
    """集团合并汇总（含子集团）：成员数 / 授信 / 在保（实时 SUM）。

    P0 修复：金额与成员数均为合并口径——担保集团授信管控需要
    覆盖子集团，防止父集团额度统计漏算。
    """
    ids = _subtree_ids(_children_map(db), group_id)
    agg = db.execute(
        select(
            func.count(Customer.id),
            func.coalesce(func.sum(Customer.credit_amount), 0),
            func.coalesce(func.sum(Customer.amount), 0),
        ).where(Customer.group_id.in_(ids))
    ).one()
    return {
        "member_count": agg[0],
        "total_credit_amount": float(agg[1]),
        "total_amount": float(agg[2]),
    }


def tree(db: Session) -> list[dict]:
    """集团树（成员数/在保汇总为合并口径：本集团 + 全部子集团）。"""
    rows = db.scalars(select(Group).order_by(Group.name)).all()
    counts = _member_counts(db)
    children_map = _children_map(db)
    # 母公司名与各集团直接成员在保 SUM
    parent_names = {}
    sums: dict[int, float] = {}
    if rows:
        parent_ids = [r.parent_customer_id for r in rows if r.parent_customer_id]
        if parent_ids:
            parent_rows = db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(parent_ids))
            ).all()
            parent_names = dict(parent_rows)
        # 直接成员在保 SUM（实时聚合作底数，节点值再叠加子孙集团）
        sums = dict(
            db.execute(
                select(Customer.group_id, func.coalesce(func.sum(Customer.amount), 0))
                .where(Customer.group_id.in_([r.id for r in rows]))
                .group_by(Customer.group_id)
            ).all()
        )

    def merged(gid: int) -> tuple[float, int]:
        """合并口径：本集团 + 子孙集团的在保额与成员数。"""
        ids = _subtree_ids(children_map, gid)
        return (
            sum(sums.get(i, 0) for i in ids),
            sum(counts.get(i, 0) for i in ids),
        )

    return build_tree(
        rows,
        parent_getter=lambda r: r.parent_id,
        node_mapper=lambda r: {
            "id": r.id, "name": r.name, "parent_id": r.parent_id,
            "parent_customer_id": r.parent_customer_id,
            "parent_customer_name": parent_names.get(r.parent_customer_id or 0),
            "credit_amount": float(r.credit_amount),
            "total_insure_amount": float(merged(r.id)[0]),
            "member_count": merged(r.id)[1],
            "status": r.status,
        },
    )


def _find_tree_node(nodes: list[dict], gid: int) -> dict | None:
    """在树中按 id 查找节点（get_detail 取 children 复用树口径）。"""
    for n in nodes:
        if n["id"] == gid:
            return n
        if n["children"]:
            found = _find_tree_node(n["children"], gid)
            if found:
                return found
    return None


def get_or_404(db: Session, group_id: int) -> Group:
    g = db.get(Group, group_id)
    if g is None:
        raise BizError(4041, "集团不存在")
    return g


def _customer_brief(c: Customer, mname: str) -> dict:
    return {
        "id": c.id, "name": c.name, "short_name": c.short_name,
        "genre": c.genre,
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

    # 汇总为合并口径（本集团 + 子集团，全量实时 SUM）；
    # members 仍为直接成员 Top20 展示列表
    summary = _summary(db, group_id)
    # 子集团列表复用树口径（每个子集团节点自带合并口径统计与 status）
    node = _find_tree_node(tree(db), group_id)
    detail = {
        "id": g.id, "name": g.name, "parent_id": g.parent_id,
        "parent_customer_id": g.parent_customer_id,
        "parent_customer_name": None,
        "credit_amount": float(g.credit_amount),
        "total_insure_amount": summary["total_amount"],
        "member_count": summary["member_count"],
        "status": g.status,
        "children": node["children"] if node else [],
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


def _validate_parent_customer(
    db: Session, customer_id: int, exclude_group_id: int | None = None
) -> Customer:
    """校验母公司客户资格（create / update 换母公司复用）。

    exclude_group_id：换母公司场景新母公司若已在本集团可放行。
    """
    c = db.get(Customer, customer_id)
    if c is None:
        raise BizError(4041, "母公司客户不存在")
    if c.genre != Genre.COMPANY:
        raise BizError(4001, "母公司必须是企业客户")
    if c.group_id is not None and c.group_id != exclude_group_id:
        raise BizError(4091, "母公司客户已属于其他集团")
    return c


def create(db: Session, name: str, parent_id: int | None,
           parent_customer_id: int, credit_amount: float,
           description: str | None, user_id: int) -> int:
    parent_customer = _validate_parent_customer(db, parent_customer_id)
    if parent_id:
        get_or_404(db, parent_id)

    # 写入（事务）：集团 + 母公司自动加入
    g = Group(
        name=name, parent_id=parent_id or None,
        parent_customer_id=parent_customer_id,
        credit_amount=credit_amount, description=description,
        created_by=user_id,
    )
    db.add(g)
    db.flush()
    parent_customer.group_id = g.id
    return g.id


def update(db: Session, group_id: int, name: str, parent_id: int | None,
           parent_customer_id: int | None, credit_amount: float,
           description: str | None) -> None:
    g = get_or_404(db, group_id)

    # 父集团变更：校验存在性 + 不可挂到自身或其子孙（防成环）。
    # 入参兼容 0=顶级（历史约定），存储统一 NULL
    if parent_id is not None and (parent_id or None) != g.parent_id:
        if parent_id:
            get_or_404(db, parent_id)
            if parent_id in _subtree_ids(_children_map(db), group_id):
                raise BizError(4091, "父集团不可设为自身或其子孙集团")
        g.parent_id = parent_id or None

    # 换母公司：旧母公司自动脱离，新母公司自动加入（同事务原子完成）
    if parent_customer_id is not None and parent_customer_id != g.parent_customer_id:
        new_parent = _validate_parent_customer(
            db, parent_customer_id, exclude_group_id=group_id
        )
        if g.parent_customer_id:
            old_parent = db.get(Customer, g.parent_customer_id)
            if old_parent is not None and old_parent.group_id == group_id:
                old_parent.group_id = None
        new_parent.group_id = group_id
        g.parent_customer_id = parent_customer_id

    g.name = name
    g.credit_amount = credit_amount
    g.description = description


def delete(db: Session, group_id: int) -> None:
    g = get_or_404(db, group_id)
    # 拦截：集团下任一成员（母公司也是成员，且不可单独移除）或子集团存在时不可删
    member = db.scalar(
        select(Customer.id).where(Customer.group_id == group_id).limit(1)
    )
    if member is not None:
        raise BizError(4091, "集团仍有成员企业（含母公司），请先移除全部成员后再删除")
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
    get_or_404(db, group_id)
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
    """集团（含子集团）成员授信/在保合并汇总（实时统计）。"""
    get_or_404(db, group_id)
    return _summary(db, group_id)
