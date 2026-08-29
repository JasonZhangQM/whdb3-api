"""部门 / 角色 / 权限菜单 / 日志 / 字典服务。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.user.enums import DataScope, UserStatus
from app.user.models import (
    Department,
    LoginLog,
    Menu,
    OperationLog,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.user.schemas.org import (
    DeptCreate,
    DeptNode,
    DeptUpdate,
    MenuCreate,
    MenuUpdate,
    RoleCreate,
    RoleDetail,
    RoleListItem,
    RoleUpdate,
)
from app.user.services import context_service

SCOPE_DISPLAY = {10: "本人", 20: "本部门", 30: "本部门及下级", 40: "全部", 50: "自定义"}
STATUS_DISPLAY = {10: "启用", 20: "停用"}


# ================= 部门 =================

def _dept_member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(User.dept_id, func.count(User.id))
        .where(User.status != UserStatus.RESIGNED.value, User.dept_id.isnot(None))
        .group_by(User.dept_id)
    ).all()
    return {r[0]: r[1] for r in rows}


def dept_tree(db: Session) -> list[DeptNode]:
    depts = list(db.scalars(select(Department).order_by(Department.ordery, Department.id)))
    counts = _dept_member_counts(db)
    by_id = {d.id: d for d in depts}
    # 批量取创建人姓名（列表尾列展示，避免 N+1）
    creator_ids = {d.created_by for d in depts if d.created_by}
    creator_names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()
    ) if creator_ids else {}

    def assemble(parent_id: int) -> list[DeptNode]:
        nodes = []
        for d in depts:
            if d.parent_id != parent_id:
                continue
            leader = by_id.get(d.leader_user_id)
            nodes.append(DeptNode(
                id=d.id, parent_id=d.parent_id, name=d.name,
                leader_user_id=d.leader_user_id,
                leader_name=None,  # 负责人姓名需查 users 表，M1 列表页不展示
                ordery=d.ordery, status=d.status,
                status_display=STATUS_DISPLAY.get(d.status, ""),
                description=d.description, member_count=counts.get(d.id, 0),
                created_by_name=creator_names.get(d.created_by) or "",
                children=assemble(d.id),
            ))
        return nodes

    return assemble(0)


def _get_dept_or_404(db: Session, dept_id: int) -> Department:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise BizError(4041, "部门不存在")
    return dept


def get_dept_detail(db: Session, dept_id: int) -> dict:
    """部门详情：基础信息 + 在职成员列表 + 直接下级部门。"""
    dept = _get_dept_or_404(db, dept_id)
    members = list(db.scalars(
        select(User).where(User.dept_id == dept_id, User.status != UserStatus.RESIGNED.value)
        .order_by(User.id)
    ))
    children = list(db.scalars(
        select(Department).where(Department.parent_id == dept_id).order_by(Department.ordery)
    ))
    counts = _dept_member_counts(db)
    return dict(
        id=dept.id, parent_id=dept.parent_id, name=dept.name,
        leader_user_id=dept.leader_user_id, ordery=dept.ordery,
        status=dept.status, status_display=STATUS_DISPLAY.get(dept.status, ""),
        description=dept.description, member_count=counts.get(dept.id, 0),
        members=[dict(id=u.id, username=u.username, name=u.name,
                      position=u.position, status=u.status) for u in members],
        child_departments=[dict(id=c.id, name=c.name, member_count=counts.get(c.id, 0))
                           for c in children],
    )


def _check_parent_cycle(db: Session, dept_id: int, new_parent_id: int) -> None:
    """防把部门挂到自己子孙节点下（成环）。"""
    cursor = new_parent_id
    while cursor:
        if cursor == dept_id:
            raise BizError(4091, "父部门不能是自身或其子部门")
        parent = db.get(Department, cursor)
        cursor = parent.parent_id if parent else 0


def create_dept(db: Session, req: DeptCreate) -> int:
    if req.parent_id:
        _get_dept_or_404(db, req.parent_id)
    dept = Department(**req.model_dump())
    db.add(dept)
    db.commit()
    context_service.invalidate_dept_tree()
    return dept.id


def update_dept(db: Session, dept_id: int, req: DeptUpdate) -> None:
    dept = _get_dept_or_404(db, dept_id)
    if req.parent_id is not None and req.parent_id != dept.parent_id:
        _check_parent_cycle(db, dept_id, req.parent_id)
    for f, v in req.model_dump(exclude_none=True).items():
        setattr(dept, f, v)
    db.commit()
    # 全站 dept_tree + 该部门子树内所有用户（30 范围展开变化）
    context_service.invalidate_dept_subtree(db, dept_id)


def delete_dept(db: Session, dept_id: int) -> None:
    dept = _get_dept_or_404(db, dept_id)
    if db.scalar(select(func.count(User.id)).where(User.dept_id == dept_id)):
        raise BizError(4091, "部门下仍有成员")
    if db.scalar(select(func.count(Department.id)).where(Department.parent_id == dept_id)):
        raise BizError(4091, "部门下仍有子部门")
    db.delete(dept)
    db.commit()
    context_service.invalidate_dept_tree()


# ================= 角色 =================

def list_roles(db: Session) -> list[RoleListItem]:
    roles = list(db.scalars(select(Role).order_by(Role.id)))
    user_counts = dict(db.execute(
        select(UserRole.role_id, func.count(UserRole.user_id)).group_by(UserRole.role_id)
    ).all())
    perm_counts = dict(db.execute(
        select(RolePermission.role_id, func.count(RolePermission.permission_id))
        .group_by(RolePermission.role_id)
    ).all())
    # 批量取创建人姓名（列表尾列展示，避免 N+1）
    creator_ids = {r.created_by for r in roles if r.created_by}
    creator_names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()
    ) if creator_ids else {}
    return [RoleListItem(
        id=r.id, code=r.code, name=r.name, description=r.description,
        is_builtin=r.is_builtin, data_scope=r.data_scope,
        data_scope_display=SCOPE_DISPLAY.get(r.data_scope, ""),
        user_count=user_counts.get(r.id, 0),
        permission_count=perm_counts.get(r.id, 0),
        created_at=r.created_at,
        created_by_name=creator_names.get(r.created_by) or "",
    ) for r in roles]


def get_role_detail(db: Session, role_id: int) -> RoleDetail:
    role = db.get(Role, role_id)
    if role is None:
        raise BizError(4041, "角色不存在")
    base = [r for r in list_roles(db) if r.id == role_id][0]
    bound_users = list(db.scalars(
        select(User).join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == role_id).order_by(User.id)
    ))
    return RoleDetail(
        **base.model_dump(),
        permission_codes=list(db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )),
        users=[dict(id=u.id, username=u.username, name=u.name,
                    dept_name=None, position=u.position) for u in bound_users],
    )


def create_role(db: Session, req: RoleCreate) -> int:
    if db.scalar(select(Role).where(Role.code == req.code)):
        raise BizError(4090, "角色编码已存在")
    role = Role(**req.model_dump(), is_builtin=False)
    db.add(role)
    db.commit()
    return role.id


def update_role(db: Session, role_id: int, req: RoleUpdate) -> None:
    """内置角色仅允许改 name/description/data_scope。"""
    role = db.get(Role, role_id)
    if role is None:
        raise BizError(4041, "角色不存在")
    if not role.is_builtin or req.name is not None:
        if req.name is not None:
            role.name = req.name
    if req.description is not None:
        role.description = req.description
    if req.data_scope is not None:
        role.data_scope = req.data_scope
    db.commit()
    context_service.invalidate_role(db, role_id)


def delete_role(db: Session, role_id: int) -> None:
    role = db.get(Role, role_id)
    if role is None:
        raise BizError(4041, "角色不存在")
    if role.is_builtin:
        raise BizError(4092, "内置角色不可删除")
    if db.scalar(select(func.count(UserRole.user_id)).where(UserRole.role_id == role_id)):
        raise BizError(4092, "角色仍有绑定用户")
    db.delete(role)
    db.commit()


def assign_role_perms(db: Session, role_id: int, permission_ids: list[int]) -> None:
    """全量替换角色权限（事务内删旧插新；提交后批量失效绑定用户缓存）。"""
    from sqlalchemy import text

    role = db.get(Role, role_id)
    if role is None:
        raise BizError(4041, "角色不存在")
    with db.begin_nested():
        db.execute(text("SELECT id FROM user_roles WHERE id=:id FOR UPDATE"), {"id": role_id})
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        for pid in permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=pid))
    db.commit()
    # 先持久后失效：角色权限变化 -> 反查绑定用户批量 DEL（TTL 兜底，失败仅告警）
    context_service.invalidate_role(db, role_id)


def assign_role_users(db: Session, role_id: int, user_ids: list[int]) -> None:
    """批量给角色绑定用户（增量，不替换）。"""
    role = db.get(Role, role_id)
    if role is None:
        raise BizError(4041, "角色不存在")
    existing = set(db.scalars(
        select(UserRole.user_id).where(UserRole.role_id == role_id)
    ))
    with db.begin_nested():
        for uid in user_ids:
            if uid not in existing and db.get(User, uid):
                db.add(UserRole(user_id=uid, role_id=role_id))
    db.commit()
    context_service.invalidate_role(db, role_id)


# ================= 权限 & 菜单 =================

def list_permissions(db: Session) -> list[dict]:
    perms = list(db.scalars(select(Permission).order_by(Permission.module, Permission.ordery)))
    type_display = {10: "菜单", 20: "操作", 30: "数据"}
    return [dict(
        id=p.id, code=p.code, name=p.name, module=p.module, type=p.type,
        type_display=type_display.get(p.type, ""), menu_id=p.menu_id, ordery=p.ordery,
    ) for p in perms]


def list_menus(db: Session) -> list[dict]:
    """全部菜单树（配置页用，含按钮）。"""
    menus = list(db.scalars(select(Menu).order_by(Menu.ordery, Menu.id)))
    # 批量取创建人姓名（列表尾列展示，避免 N+1）
    creator_ids = {m.created_by for m in menus if m.created_by}
    creator_names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()
    ) if creator_ids else {}

    def assemble(parent_id: int) -> list[dict]:
        nodes = []
        for m in menus:
            if m.parent_id != parent_id:
                continue
            nodes.append(dict(
                id=m.id, parent_id=m.parent_id, caption=m.caption, icon=m.icon,
                path=m.path, component=m.component, ordery=m.ordery, type=m.type,
                visible=m.visible, keep_alive=m.keep_alive, redirect=m.redirect,
                permission_code=m.permission_code,
                created_by_name=creator_names.get(m.created_by) or "",
                children=assemble(m.id),
            ))
        return nodes

    return assemble(0)


def _auto_perm_code(path: str | None, caption: str) -> str:
    """自动生成菜单权限码：path /system/users -> menus:system:users。"""
    parts = [p for p in (path or "").strip("/").split("/") if p]
    return ":".join(["menus", *parts]) if parts else f"menus:{caption}"


def create_menu(db: Session, req: MenuCreate) -> int:
    if req.parent_id:
        if db.get(Menu, req.parent_id) is None:
            raise BizError(4041, "父菜单不存在")
    perm_code = req.permission_code or _auto_perm_code(req.path, req.caption)
    with db.begin_nested():
        menu = Menu(**req.model_dump(exclude={"permission_code"}), permission_code=perm_code)
        db.add(menu)
        db.flush()
        # 自动同步生成菜单权限点（type=10 挂 menu_id）
        if not db.scalar(select(Permission).where(Permission.code == perm_code)):
            db.add(Permission(
                code=perm_code, name=f"{req.caption}（菜单）", module="menus",
                type=10, menu_id=menu.id, ordery=req.ordery,
            ))
    db.commit()
    return menu.id


def update_menu(db: Session, menu_id: int, req: MenuUpdate) -> None:
    menu = db.get(Menu, menu_id)
    if menu is None:
        raise BizError(4041, "菜单不存在")
    for f, v in req.model_dump(exclude_none=True).items():
        setattr(menu, f, v)
    db.commit()
    # 菜单变更不失效权限缓存：可见性由前端下次拉取自然更新


def delete_menu(db: Session, menu_id: int) -> None:
    menu = db.get(Menu, menu_id)
    if menu is None:
        raise BizError(4041, "菜单不存在")
    children = db.scalars(select(Menu.id).where(Menu.parent_id == menu_id)).all()
    if children:
        for cid in children:
            delete_menu(db, cid)  # 子级联动删
    perm = db.scalar(select(Permission).where(Permission.menu_id == menu_id))
    if perm and db.scalar(select(func.count(RolePermission.id)).where(RolePermission.permission_id == perm.id)):
        raise BizError(4091, "菜单权限已被角色引用，不可删除")
    with db.begin_nested():
        if perm:
            db.delete(perm)
        db.delete(menu)
    db.commit()


# ================= 日志 =================

def list_operation_logs(db: Session, page: int, page_size: int, **filters) -> tuple[list, int]:
    stmt = select(OperationLog)
    if filters.get("module"):
        stmt = stmt.where(OperationLog.module == filters["module"])
    if filters.get("username"):
        stmt = stmt.where(OperationLog.username.like(f"%{filters['username']}%"))
    if filters.get("target_id"):
        stmt = stmt.where(OperationLog.target_id == str(filters["target_id"]))
    if filters.get("start_time"):
        stmt = stmt.where(OperationLog.created_at >= filters["start_time"])
    if filters.get("end_time"):
        stmt = stmt.where(OperationLog.created_at <= filters["end_time"])
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    logs = list(db.scalars(stmt.order_by(OperationLog.id.desc())
                           .offset((page - 1) * page_size).limit(page_size)))
    return logs, total or 0


def get_operation_log(db: Session, log_id: int) -> OperationLog:
    log = db.get(OperationLog, log_id)
    if log is None:
        raise BizError(4041, "日志不存在")
    return log


def list_login_logs(db: Session, page: int, page_size: int,
                    username: str | None = None, status: int | None = None) -> tuple[list, int]:
    stmt = select(LoginLog)
    if username:
        stmt = stmt.where(LoginLog.username.like(f"%{username}%"))
    if status:
        stmt = stmt.where(LoginLog.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    logs = list(db.scalars(stmt.order_by(LoginLog.id.desc())
                           .offset((page - 1) * page_size).limit(page_size)))
    return logs, total or 0


# ================= 字典 =================

def list_user_options(db: Session, dept_id: int | None = None,
                      position: str | None = None) -> list[dict]:
    """员工下拉（在职）。"""
    from app.user.models import Department

    stmt = select(User, Department.name).outerjoin(
        Department, User.dept_id == Department.id
    ).where(User.status == UserStatus.ACTIVE.value)
    if dept_id:
        stmt = stmt.where(User.dept_id == dept_id)
    if position:
        stmt = stmt.where(User.position == position)
    rows = db.execute(stmt.order_by(User.id)).all()
    return [dict(id=u.id, username=u.username, name=u.name,
                 dept_name=dname, position=u.position) for u, dname in rows]
