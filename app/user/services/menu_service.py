"""菜单服务：权限过滤 + 双形态输出（自有 MenuNode / vben 路由协议）。"""

from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.user.enums import MenuType
from app.user.models import Menu
from app.user.schemas.auth import MenuNode

# 侧边栏展示类型（按钮不出路由树，仅配置页可见）
_SIDEBAR_TYPES = {MenuType.DIR.value, MenuType.PAGE.value}


def _load_menus(db: Session, ctx: AuthContext) -> list[Menu]:
    """全部可见菜单（超管全量；普通用户按权限码覆盖判定）。"""
    stmt = (
        select(Menu)
        .where(Menu.visible.is_(True))
        .order_by(asc(Menu.ordery), asc(Menu.id))
    )
    menus = list(db.scalars(stmt))
    if ctx.is_super_admin:
        return menus
    return [m for m in menus if m.permission_code is None or m.permission_code in ctx.permission_codes]


def _build_children(menus: list[Menu], parent_id: int) -> list[Menu]:
    return [m for m in menus if m.parent_id == parent_id]


def tree_for_user(db: Session, ctx: AuthContext) -> list[MenuNode]:
    """自有 MenuNode 树（/users/me 内嵌形态）。无权限点的目录仅在有可见后代时保留。"""
    menus = _load_menus(db, ctx)

    def assemble(parent_id: int) -> list[MenuNode]:
        nodes = []
        for m in _build_children(menus, parent_id):
            children = assemble(m.id)
            if m.type == MenuType.DIR.value and m.permission_code is None and not children:
                continue  # 裁空目录
            nodes.append(MenuNode(
                id=m.id, caption=m.caption, icon=m.icon, path=m.path,
                type=m.type, children=children,
            ))
        return nodes

    return assemble(0)


def _path_to_name(path: str) -> str:
    """/system/users -> SystemUsers（vben 路由 name 需唯一）。"""
    return "".join(p.capitalize() for p in path.strip("/").split("/") if p) or "Root"


def vben_route_tree(db: Session, ctx: AuthContext) -> list[dict]:
    """vben 后端路由协议树：{name, path, component, redirect, meta{title,icon}, children}。

    顶级 path 绝对（/system）；子级 path 相对（users）；component 以 / 开头指向
    apps/web-antd/src/views 下路径。
    """
    menus = _load_menus(db, ctx)

    def assemble(parent_id: int) -> list[dict]:
        nodes = []
        for m in _build_children(menus, parent_id):
            if m.type not in _SIDEBAR_TYPES:
                continue
            children = assemble(m.id)
            if m.type == MenuType.DIR.value and m.permission_code is None and not children:
                continue
            path = m.path or ""
            node: dict = {
                "name": _path_to_name(path or str(m.id)),
                "path": path if path.startswith("/") else (path or "/"),
                "meta": {"title": m.caption, "order": m.ordery},
            }
            if m.icon:
                node["meta"]["icon"] = m.icon
            if m.redirect:
                node["redirect"] = m.redirect
            if m.type == MenuType.PAGE.value:
                if m.component:
                    node["component"] = (
                        m.component if m.component.startswith("/") else f"/{m.component}"
                    )
                if m.keep_alive:
                    node["meta"]["keepAlive"] = True
            if children:
                node["children"] = children
            nodes.append(node)
        return nodes

    return assemble(0)
