"""
通用树构建工具（Python O(n) 组装）

后端多处 service 手写相同的 nodes_dict + roots_list + 两次遍历模式：
  - user/services/region_service.region_tree
  - customer/services/group_service.tree
  - customer/services/credit_region_service.tree
  - customer/services/region_service.industry_tree
  - warrant/api/v1/dicts.house_apps

统一收敛到本模块。新的树接口调用 build_tree()，禁止就地重复实现。
"""

from typing import Callable, Iterable


def build_tree(
    rows: Iterable,
    parent_getter: Callable[[object], int | None],
    node_mapper: Callable[[object], dict],
    parent_id_null: int = 0,
) -> list[dict]:
    """
    O(n) 组装树结构：先全量创建节点 dict，再按 parent_id 挂 children。

    :param rows: 查询出的模型行列表（需已按合理顺序排序，如 parent_id 或 code）
    :param parent_getter: 从行对象取 parent_id 的 callable（lambda r: r.parent_id）
    :param node_mapper: 从行对象生成节点 dict 的 callable（会被追加 "children": []）
    :param parent_id_null: 根节点的 parent_id 值（默认 0，可传 None）
    :return: 顶层节点列表（每个节点含 children）

    使用示例（最简）::

        def my_tree(db):
            rows = db.scalars(select(MyModel).order_by(MyModel.code)).all()
            return build_tree(
                rows,
                parent_getter=lambda r: r.parent_id,
                node_mapper=lambda r: {"id": r.id, "name": r.name},
            )

    使用示例（自定义字段 + 带统计）::

        def region_tree(db):
            rows = db.scalars(select(Region).where(Region.status == 10)).all()
            return build_tree(
                rows,
                parent_getter=lambda r: r.parent_id,
                node_mapper=lambda r: {
                    "id": r.id, "code": r.code, "name": r.name,
                    "level": r.level,
                },
            )
    """
    nodes: dict[int, dict] = {}
    roots: list[dict] = []

    # 第一次遍历：创建所有节点（带空 children）
    for r in rows:
        node = node_mapper(r)
        node["children"] = []
        nodes[node["id"]] = node

    # 第二次遍历：按 parent_id 挂载
    for r in rows:
        node = nodes[r.id]
        pid = parent_getter(r)
        # 根节点：parent_id 为 parent_id_null 或在 nodes 中不存在
        if pid is None or pid == parent_id_null or pid not in nodes:
            roots.append(node)
        else:
            nodes[pid]["children"].append(node)

    return roots
