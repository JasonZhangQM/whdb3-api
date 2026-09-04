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

from app.approval.models import ApprovalFlowDef, ApprovalFlowNode
from app.article.models import ArticleProduct  # noqa: E402
from app.approval import permissions as approval_perms  # noqa: E402
from app.article import permissions as article_perms  # noqa: E402  M3a 项目
from app.appraisal import permissions as appraisal_perms  # noqa: E402  M3a 评审
from app.core.db import SessionLocal  # noqa: E402
from app.customer import permissions as customer_perms  # noqa: E402
from app.institution import permissions as institution_perms  # noqa: E402
from app.user import permissions as user_perms  # noqa: E402
from app.user.enums import PermType  # noqa: E402
from app.user.models import (  # noqa: E402
    Department,
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

# 废弃菜单路径前缀（菜单结构调整时在此登记，seed 自动清理残留旧菜单）
LEGACY_MENU_PREFIXES: tuple[str, ...] = ("/basic",)  # M2：基础数据目录拆为模块一级目录

# ---- 模块聚合：新增模块的 permissions.py 在此登记 ----
ALL_MENUS: list[dict] = (
    user_perms.MENUS
    + approval_perms.MENUS
    + institution_perms.MENUS
    + customer_perms.MENUS
    + warrant_perms.MENUS
    + article_perms.MENUS
    + appraisal_perms.MENUS
)
ALL_ACTIONS: list[tuple[str, str]] = (
    user_perms.ACTION_PERMISSIONS
    + approval_perms.ACTION_PERMISSIONS
    + institution_perms.ACTION_PERMISSIONS
    + customer_perms.ACTION_PERMISSIONS
    + warrant_perms.ACTION_PERMISSIONS
    + article_perms.ACTION_PERMISSIONS
    + appraisal_perms.ACTION_PERMISSIONS
)

# 菜单权限（type=10）中文名：与各模块 MENUS 的 permission_code 对应
MENU_PERM_NAMES: dict[str, str] = {
    "user:list": "用户列表",
    "dept:list": "部门列表",
    "role:list": "角色列表",
    "menu:list": "菜单列表",
    "region:list": "行政区划查看",
    "log:operation": "操作日志查询",
    "log:login": "登录日志查询",
    "institution:list": "机构列表",
    "customer:list": "客户列表",
    "customer:tags_list": "客户标签",
    "customer:group_list": "集团管理",
    "warrant:list": "权证列表",
    "article:list": "项目列表",
    "appraisal:list": "评审会列表",
    "appraisal:expert_list": "专家库",
}

# 审批流定义（总体方案 §5.3：流程定义走代码版本管理）
# M3a 新增：项目签批 + 项目变更
APPROVAL_FLOWS: list[dict] = [
    {
        "code": "article_sign",
        "name": "项目签批",
        "description": "项目评审完成后发起签批，通过后方可放款",
        "nodes": [
            {"step": 1, "name": "部门负责人审批", "approver_role_code": "dept_manager"},
            {"step": 2, "name": "风控审批", "approver_role_code": "controler"},
            {"step": 3, "name": "总经理审批", "approver_role_code": "super_admin"},
        ],
    },
    {
        "code": "article_change",
        "name": "项目变更申请",
        "description": "已签批/已放款项目的变更申请",
        "nodes": [
            {"step": 1, "name": "风控审批", "approver_role_code": "controler"},
            {"step": 2, "name": "总经理审批", "approver_role_code": "super_admin"},
        ],
    },
    {
        "code": "warrant_release_out",
        "name": "权证解保出库",
        "description": "权证释放担保责任的解保出库审批",
        "nodes": [
            {"step": 1, "name": "部门负责人审批", "approver_role_code": "dept_manager"},
            {"step": 2, "name": "风控审批", "approver_role_code": "controler"},
            {"step": 3, "name": "总经理审批", "approver_role_code": "super_admin"},
        ],
    },
]


def seed_menus(db: Session) -> dict[str, int]:
    """递归建菜单（按 path 幂等），返回 permission_code -> menu_id 映射。"""

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


def cleanup_legacy_menus(db: Session) -> None:
    """删除废弃前缀下的旧菜单树。

    必须在 seed_permissions 之后执行：权限 menu_id 已重挂到新菜单，
    旧菜单无引用可安全删除（parent_id 无物理外键，直接按前缀批量删）。
    """
    for prefix in LEGACY_MENU_PREFIXES:
        deleted = (
            db.query(Menu)
            .filter(Menu.path.like(f"{prefix}%"))
            .delete(synchronize_session=False)
        )
        if deleted:
            print(f"已清理废弃菜单 {prefix}*：{deleted} 条")


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



# 审批测试用户规划：审批引擎 _resolve_approvers 查询条件要求
#   1) User.dept_id == submitter.dept_id  同部门
#   2) User.status == 10                  启用
#   3) Role.code == node.approver_role_code  角色匹配
#   4) User.id != submitted_by            不能自审
# 因此需要：统一 dept、多角色覆盖 article_sign 的 3 个节点、
#           每个角色至少 2 人（避免某角色单人时触发自审保护）。
APPROVAL_TEST_USERS: list[dict] = [
    {
        "username": "approval_gm",
        "name": "审批测试-总经理A",
        "roles": ["super_admin"],
        "is_super_admin": True,
    },
    {
        "username": "approval_gm2",
        "name": "审批测试-总经理B",
        "roles": ["super_admin"],
        "is_super_admin": False,  # 避免 GM 自审
    },
    {
        "username": "approval_dept_manager",
        "name": "审批测试-部门负责人",
        "roles": ["dept_manager"],
        "is_super_admin": False,
    },
    {
        "username": "approval_controler",
        "name": "审批测试-风控",
        "roles": ["controler"],
        "is_super_admin": False,
    },
]


def seed_approval_test_users(db: Session) -> None:
    """审批测试用户（幂等）。

    统一放到一个"测试一部"部门（优先用已存在 dept_id=1；不存在则创建）。
    同时把 admin 的 dept_id 也拉到这个部门，确保以 admin 身份发起的审批
    _resolve_approvers 能查到同部门的审批人。
    """
    # 1) 确保目标部门存在
    target_dept = db.scalar(select(Department).where(Department.name == "测试一部"))
    if target_dept is None:
        target_dept = Department(name="测试一部", status=10)
        db.add(target_dept)
        db.flush()
    dept_id = target_dept.id

    fixes: list[str] = []

    # 2) admin 也拉到这个部门（方便以 admin 身份发起审批走完整链路）
    admin = db.scalar(select(User).where(User.username == "admin"))
    if admin and admin.dept_id != dept_id:
        admin.dept_id = dept_id
        fixes.append("admin dept_id -> %d" % dept_id)

    # 3) 审批测试用户 upsert（按 username 定位）
    for spec in APPROVAL_TEST_USERS:
        u = db.scalar(select(User).where(User.username == spec["username"]))
        if u is None:
            u = User(username=spec["username"])
            db.add(u)
            fixes.append("+ user %s" % spec["username"])

        # 统一修正属性（新建时补齐非空字段）
        u.name = spec["name"]
        u.status = 10
        u.dept_id = dept_id
        u.is_super_admin = spec["is_super_admin"]
        u.email = spec["username"] + "@whdb.local"
        if u.password_hash is None:
            u.password_hash = pwd_context.hash("Approval@Test123")
        u.gender = 0
        db.flush()

        # 每个角色都绑定（幂等 upsert）
        for role_code in spec["roles"]:
            role = db.scalar(select(Role).where(Role.code == role_code))
            if role is None:
                raise RuntimeError(
                    "角色 %s 不存在，请先执行 seed_roles()" % role_code
                )
            exists = db.scalar(
                select(UserRole).where(
                    UserRole.user_id == u.id, UserRole.role_id == role.id
                )
            )
            if exists is None:
                db.add(UserRole(user_id=u.id, role_id=role.id))
                fixes.append("%s +role %s" % (spec["username"], role_code))

    if fixes:
        print("  审批测试用户 seed 修复 %d 处:" % len(fixes))
        for f in fixes:
            print("    %s" % f)
    else:
        print("  审批测试用户已就绪（4 人同部门 dept=%d）" % dept_id)


def seed_products(db: Session) -> None:
    """产品种子数据（幂等）。"""
    from decimal import Decimal
    existing = db.scalars(select(ArticleProduct)).all()
    if existing:
        return
    products = [
        ArticleProduct(name="流动资金贷款", difficulty_score=Decimal("60.00"), sort=10),
        ArticleProduct(name="银行承兑汇票", difficulty_score=Decimal("50.00"), sort=20),
        ArticleProduct(name="商业承兑汇票", difficulty_score=Decimal("55.00"), sort=30),
        ArticleProduct(name="信用证", difficulty_score=Decimal("65.00"), sort=40),
        ArticleProduct(name="保函", difficulty_score=Decimal("58.00"), sort=50),
        ArticleProduct(name="保理", difficulty_score=Decimal("52.00"), sort=60),
        ArticleProduct(name="固定资产贷款", difficulty_score=Decimal("70.00"), sort=70),
    ]
    db.add_all(products)

def main() -> None:
    with SessionLocal() as db:
        with db.begin():
            menu_ids = seed_menus(db)
            perm_ids = seed_permissions(db, menu_ids)
            cleanup_legacy_menus(db)
            seed_roles(db, perm_ids)
            seed_approval_flows(db)
            seed_super_admin(db)
            seed_approval_test_users(db)
            seed_products(db)
    total_perms = len(perm_ids)
    print(f"seed 完成：8 内置角色 / {total_perms} 权限 / {len(menu_ids)} 菜单权限 / {len(APPROVAL_FLOWS)} 审批流 / 超管 admin / 审批测试用户（4人同部门）")
    print(f"超管初始密码：{ADMIN_INIT_PASSWORD}（首登强制改密）")


if __name__ == "__main__":
    main()
