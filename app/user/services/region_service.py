"""行政区域服务（从 customer 模块迁入，作为用户模块基础数据）。"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.user.models import Region

# 层级中文标签（原 customer/enums.py LABELS["region_level"]，随模型迁入）
REGION_LEVEL_LABELS: dict[int, str] = {10: "省", 20: "市", 30: "区县", 40: "乡镇街道"}


def region_tree(db: Session) -> list[dict]:
    """全量区域树：一次性查出，Python 侧 O(n) 组装（约 4.5 万条）。"""
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
    """指定节点直接下级（树形表格懒加载，带 has_children 标记供前端渲染展开箭头）。"""
    rows = db.scalars(
        select(Region)
        .where(Region.parent_id == region_id)
        .order_by(Region.ordery, Region.code)
    ).all()
    # 一条 GROUP BY 批量判定子节点存在性，避免逐行 EXISTS
    child_counts: dict[int, int] = {}
    if rows:
        ids = [r.id for r in rows]
        child_counts = dict(
            db.execute(
                select(Region.parent_id, func.count())
                .where(Region.parent_id.in_(ids))
                .group_by(Region.parent_id)
            ).all()
        )
    return [
        {"id": r.id, "code": r.code, "name": r.name, "level": r.level,
         "level_display": REGION_LEVEL_LABELS.get(r.level),
         "parent_id": r.parent_id, "status": r.status,
         "has_children": child_counts.get(r.id, 0) > 0}
        for r in rows
    ]


def region_roots(db: Session) -> list[dict]:
    """顶层省级列表（页面首屏，只取 34 条）。"""
    return region_children(db, 0)


def region_detail(db: Session, region_id: int) -> dict | None:
    """单节点详情（带完整路径），供前端编辑回显：懒加载树中没有该节点时插入临时节点。"""
    r = db.get(Region, region_id)
    if r is None:
        return None
    # 沿 parent_id 链向上取祖先名称（≤4 级，直接循环查即可）
    parts: list[str] = [r.name]
    pid = r.parent_id
    while pid > 0:
        parent = db.get(Region, pid)
        if parent is None:
            break
        parts.insert(0, parent.name)
        pid = parent.parent_id
    return {
        "id": r.id, "code": r.code, "name": r.name, "level": r.level,
        "level_display": REGION_LEVEL_LABELS.get(r.level),
        "parent_id": r.parent_id, "path": "/".join(parts),
    }


def region_search(db: Session, q: str) -> list[dict]:
    """按名称/代码搜索区域（限 50 条，平铺结果带层级标签 + 完整路径）。"""
    like = f"%{q}%"
    rows = db.scalars(
        select(Region)
        .where(or_(Region.name.like(like), Region.code.like(like)))
        .order_by(Region.code)
        .limit(50)
    ).all()
    if not rows:
        return []

    # 迭代收集所有祖先 id，一次 IN 查询拉回，避免 N+1
    all_parent_ids: set[int] = set()
    frontier = {r.parent_id for r in rows if r.parent_id > 0}
    while frontier:
        all_parent_ids.update(frontier)
        parents = db.scalars(
            select(Region.parent_id).where(Region.id.in_(frontier))
        ).all()
        frontier = {p for p in parents if p > 0 and p not in all_parent_ids}

    ancestor_map: dict[int, Region] = {}
    if all_parent_ids:
        for r in db.scalars(select(Region).where(Region.id.in_(all_parent_ids))):
            ancestor_map[r.id] = r

    def _build_path(node: Region) -> str:
        parts: list[str] = [node.name]
        pid = node.parent_id
        while pid > 0 and pid in ancestor_map:
            parts.append(ancestor_map[pid].name)
            pid = ancestor_map[pid].parent_id
        parts.reverse()
        return "/".join(parts)

    return [
        {"id": r.id, "code": r.code, "name": r.name, "level": r.level,
         "level_display": REGION_LEVEL_LABELS.get(r.level),
         "parent_id": r.parent_id, "path": _build_path(r)}
        for r in rows
    ]
