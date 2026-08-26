"""seed：内置角色 / 权限 / 菜单 / 超管 / 审批流定义初始化（幂等，可重复执行）。

用法：python scripts/seed.py
数据来源：各模块 permissions.py 声明（在此聚合，新增模块登记一行）。
"""

import sys
from pathlib import Path

# 保证以仓库内任意目录运行均可导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.approval.models import ApprovalFlowDef, ApprovalFlowNode  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.customer import permissions as customer_perms  # noqa: E402
from app.institution import permissions as institution_perms  # noqa: E402
from app.user import permissions as user_perms  # noqa: E402
from app.user.enums import PermType  # noqa: E402
from app.user.models import (  # noqa: E402
    Menu,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.warrant import permissions as warrant_perms  # noqa: E402

# bcrypt（总体方案 §3.3：cost=12，不兼容旧 pbkdf2 哈希）
pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)

# 超管初始密码（满足策略：≥10 位、大小写+数字；首登强制改密）
ADMIN_INIT_PASSWORD = "Admin@whdb3"

ORDINAL_STEP = 100  # 菜单/权限排序步长，便于后续插入

# ---- 模块聚合：新增模块的 permissions.py 在此登记 ----
ALL_MENUS: list[dict] = (
    user_perms.MENUS
    + institution_perms.MENUS
    + customer_perms.MENUS
    + warrant_perms.MENUS
)
ALL_ACTIONS: list[tuple[str, str]] = (
    user_perms.ACTION_PERMISSIONS
    + institution_perms.ACTION_PERMISSIONS
    + customer_perms.ACTION_PERMISSIONS
    + warrant_perms.ACTION_PERMISSIONS
)

# 菜单权限（type=10）中文名：与各模块 MENUS 的 permission_code 对应
MENU_PERM_NAMES: dict[str, str] = {
    "user:list": "用户列表",
    "dept:list": "部门列表",
    "role:list": "角色列表",
    "menu:list": "菜单列表",
    "log:operation": "操作日志查询",
    "log:login": "登录日志查询",
    "institution:list": "机构列表",
    "customer:list": "客户列表",
    "warrant:list": "权证列表",
}

# 审批流定义（总体方案 §5.3：流程定义走代码版本管理，新增 flow_code 需评审）
# M2 首发：客户创建 / 敏感修改 / 批量移交，单节点或签（部门负责人）
APPROVAL_FLOWS: list[dict] = [
    {
        "code": "customer_create",
        "name": "客户创建审批",
        "description": "新建客户（含企业/个人扩展），审批通过后落库",
        "nodes": [
            {"step": 1, "name": "部门负责人审批", "approver_role_code": "dept_manager"},
        ],
    },
    {
        "code": "customer_update",
        "name": "客户敏感修改审批",
        "description": "名称/证件号/状态/授信额度等敏感字段变更，通过后应用 diff",
        "nodes": [
            {"step": 1, "name": "部门负责人审批", "approver_role_code": "dept_manager"},
        ],
    },
    {
        "code": "customer_transfer",
        "name": "客户批量移交审批",
        "description": "批量变更管护经理（≤200），通过后一条 UPDATE 批量生效",
        "nodes": [
            {"step": 1, "name": "部门负责人审批", "approver_role_code": "dept_manager"},
        ],
    },
]


def seed_menus(db: Session) -> dict[str, int]:
    """递归建菜单（按 path 幂等），返回 permission_code -> menu_id 映射。

    多模块声明同一目录（如 /basic）时按 path 幂等合并，children 挂到同一目录下。
    """

    def upsert(nodes: list[dict], parent_id: int, start_order: int) -> None:
        for i, node in enumerate(nodes):
            menu = db.scalar(select(Menu).where(Menu.path == node["path"]))
            if menu is None:
                menu = Menu(parent_id=parent_id, path=node["path"])
                db.add(menu)
            menu.caption = node["caption"]
            menu.icon = node.get("icon")
            menu.component = node.get("component")
            menu.type = node["type"]
            menu.ordery = start_order + i * ORDINAL_STEP
            menu.visible = True
            menu.permission_code = node.get("permission_code")
            db.flush()  # 拿 id 供子级/权限回挂
            if node.get("children"):
                upsert(node["children"], menu.id, ORDINAL_STEP)

    upsert(ALL_MENUS, parent_id=0, start_order=ORDINAL_STEP)

    # permission_code -> menu_id（供菜单权限挂 menu_id）
    mapping: dict[str, int] = {}

    def walk(nodes: list[dict]) -> None:
        for node in nodes:
            code = node.get("permission_code")
            if code:
                menu = db.scalar(select(Menu).where(Menu.path == node["path"]))
                assert menu is not None
                mapping[code] = menu.id
            if node.get("children"):
                walk(node["children"])

    walk(ALL_MENUS)
    return mapping


def seed_permissions(db: Session, menu_ids: dict[str, int]) -> dict[str, int]:
    """建权限（菜单权限 type=10 挂 menu_id；操作权限 type=20），返回 code -> permission_id。"""

    def upsert_perm(code: str, name: str, perm_type: int, menu_id: int | None, ordery: int) -> int:
        perm = db.scalar(select(Permission).where(Permission.code == code))
        if perm is None:
            perm = Permission(code=code)
            db.add(perm)
        perm.name = name
        perm.module = code.split(":")[0]
        perm.type = perm_type
        perm.menu_id = menu_id
        perm.ordery = ordery
        db.flush()
        return perm.id

    ids: dict[str, int] = {}

    # 菜单权限：与菜单树同源（user:list / dept:list / ...）
    for i, (code, menu_id) in enumerate(menu_ids.items()):
        ids[code] = upsert_perm(
            code, MENU_PERM_NAMES.get(code, code), PermType.MENU.value, menu_id,
            (i + 1) * ORDINAL_STEP,
        )

    # 操作权限
    for i, (code, name) in enumerate(ALL_ACTIONS):
        ids[code] = upsert_perm(
            code, name, PermType.ACTION.value, None,
            (len(menu_ids) + i + 1) * ORDINAL_STEP,
        )
    return ids


def seed_roles(db: Session, perm_ids: dict[str, int]) -> None:
    """内置 8 角色；super_admin 挂全部权限（超管边界：is_super_admin 用户直通，角色赋权兜底）。"""
    for i, spec in enumerate(user_perms.BUILTIN_ROLES):
        role = db.scalar(select(Role).where(Role.code == spec["code"]))
        if role is None:
            role = Role(code=spec["code"])
            db.add(role)
        role.name = spec["name"]
        role.description = spec["description"]
        role.is_builtin = True
        role.data_scope = spec["data_scope"]
        db.flush()

        if spec["code"] == "super_admin":
            existing = set(
                db.scalars(
                    select(RolePermission.permission_id).where(
                        RolePermission.role_id == role.id
                    )
                )
            )
            for pid in perm_ids.values():
                if pid not in existing:
                    db.add(RolePermission(role_id=role.id, permission_id=pid))


def seed_approval_flows(db: Session) -> None:
    """审批流定义 + 节点（按 code 幂等；节点全删重建避免 step 漂移残留）。"""
    for spec in APPROVAL_FLOWS:
        flow = db.scalar(select(ApprovalFlowDef).where(ApprovalFlowDef.code == spec["code"]))
        if flow is None:
            flow = ApprovalFlowDef(code=spec["code"])
            db.add(flow)
        flow.name = spec["name"]
        flow.description = spec["description"]
        flow.version = 1
        flow.status = 10
        db.flush()

        # 节点重建（幂等：删旧插新）
        db.query(ApprovalFlowNode).filter(
            ApprovalFlowNode.flow_def_id == flow.id
        ).delete(synchronize_session=False)
        db.flush()
        for node in spec["nodes"]:
            db.add(
                ApprovalFlowNode(
                    flow_def_id=flow.id,
                    step=node["step"],
                    name=node["name"],
                    approver_role_code=node["approver_role_code"],
                    approver_scope=10,
                    or_sign=True,
                )
            )


def seed_super_admin(db: Session) -> None:
    """内置超管账号 admin（首登强制改密；不可经界面删除）。"""
    admin = db.scalar(select(User).where(User.username == "admin"))
    if admin is None:
        admin = User(username="admin")
        db.add(admin)
    admin.name = "超级管理员"
    admin.email = "admin@whdb.local"
    admin.password_hash = pwd_context.hash(ADMIN_INIT_PASSWORD)
    admin.gender = 0
    admin.status = 10
    admin.is_super_admin = True
    admin.must_change_password = True
    db.flush()

    # 超管同时挂 super_admin 角色（界面展示用；权限判断 is_super_admin 直通）
    role = db.scalar(select(Role).where(Role.code == "super_admin"))
    exists = db.scalar(
        select(UserRole).where(
            UserRole.user_id == admin.id, UserRole.role_id == role.id
        )
    )
    if not exists:
        db.add(UserRole(user_id=admin.id, role_id=role.id))


def main() -> None:
    with SessionLocal() as db:
        with db.begin():
            menu_ids = seed_menus(db)
            perm_ids = seed_permissions(db, menu_ids)
            seed_roles(db, perm_ids)
            seed_approval_flows(db)
            seed_super_admin(db)
    total_perms = len(perm_ids)
    print(f"seed 完成：8 内置角色 / {total_perms} 权限 / {len(menu_ids)} 菜单权限 / {len(APPROVAL_FLOWS)} 审批流 / 超管 admin")
    print(f"超管初始密码：{ADMIN_INIT_PASSWORD}（首登强制改密）")


if __name__ == "__main__":
    main()
