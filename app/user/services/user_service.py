"""用户服务：CRUD / 状态 / 重置密码 / 分配角色 / 移交 + 超管边界校验。"""

import logging
from datetime import datetime

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.core.security import PasswordService, TokenService
from app.user.enums import UserStatus
from app.user.models import OperationLog, Role, User, UserRole
from app.user.schemas.user import (
    TransferReport,
    TransferReq,
    UserCreate,
    UserListItem,
    UserStatusReq,
    UserUpdate,
)
from app.user.services import auth_service, context_service

logger = logging.getLogger(__name__)

STATUS_DISPLAY = {10: "启用", 20: "停用", 30: "离职"}


def _get_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise BizError(4041, "用户不存在")
    return user


def check_super_admin_boundary(db: Session, operator: AuthContext, target: User,
                               new_role_ids: list[int] | None = None) -> None:
    """超管三规则（详设 §8.3），被 update/assign_roles 复用。"""
    # 规则 3：非超管请求中出现 super_admin 角色 id → 拒绝
    if new_role_ids is not None and not operator.is_super_admin:
        sa_role = db.scalar(select(Role).where(Role.code == "super_admin"))
        if sa_role and sa_role.id in new_role_ids:
            raise BizError(4031, "不可分配超级管理员角色")

    # 规则 1：非超管不可修改任何持 super_admin 角色的用户
    if not operator.is_super_admin:
        target_is_sa = db.scalar(
            select(UserRole).where(
                UserRole.user_id == target.id,
                UserRole.role_id == select(Role.id).where(Role.code == "super_admin").scalar_subquery(),
            )
        )
        if target.is_super_admin or target_is_sa:
            raise BizError(4031, "无权修改超级管理员")

    # 规则 2：任何用户不可给自己分配/移除角色（超管除外）
    if new_role_ids is not None and operator.user_id == target.id and not operator.is_super_admin:
        raise BizError(4031, "不可修改自己的角色")


def _roles_of(db: Session, user_id: int) -> list[Role]:
    return list(db.scalars(
        select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user_id)
    ))


def get_my_profile(db: Session, ctx: AuthContext):
    """/users/me：一次性返回用户信息 + 权限上下文 + 菜单树。"""
    from app.user.models import Department
    from app.user.schemas.auth import UserProfile
    from app.user.services import menu_service

    user = db.get(User, ctx.user_id)
    if user is None:
        raise BizError(4041, "用户不存在")

    dept_path: list[str] = []
    dept_id = user.dept_id
    while dept_id:
        d = db.get(Department, dept_id)
        if not d:
            break
        dept_path.insert(0, d.name)
        dept_id = d.parent_id

    roles = _roles_of(db, ctx.user_id)
    return UserProfile(
        id=user.id, username=user.username, name=user.name, email=user.email,
        phone=user.phone, avatar_url=user.avatar_url, gender=user.gender,
        position=user.position, status=user.status,
        status_display=STATUS_DISPLAY.get(user.status, ""),
        dept_id=user.dept_id,
        dept_name=dept_path[-1] if dept_path else None,
        dept_path_name="/".join(dept_path) if dept_path else None,
        roles=[dict(id=r.id, code=r.code, name=r.name, data_scope=r.data_scope) for r in roles],
        permission_codes=sorted(ctx.permission_codes),
        data_scope=ctx.data_scope,
        data_scope_dept_ids=ctx.dept_scope_ids or [],
        menus=menu_service.tree_for_user(db, ctx),
        is_super_admin=ctx.is_super_admin,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
    )


def update_my_profile(db: Session, ctx: AuthContext, req) -> User:
    """修改本人基础信息（白名单字段，不含角色/部门/权限）。"""
    user = db.get(User, ctx.user_id)
    if user is None:
        raise BizError(4041, "用户不存在")
    with db.begin_nested():
        # phone 唯一约束 uk_users_phone 预检（否则 IntegrityError 落 5001）
        if req.phone and req.phone != user.phone:
            if db.scalar(select(User).where(User.phone == req.phone, User.id != ctx.user_id)):
                raise BizError(4090, "手机号已被其他用户使用")
        for f in ("name", "phone", "avatar_url", "gender"):
            v = getattr(req, f)
            if v is not None:
                setattr(user, f, v)
    db.commit()
    return user


def list_users(db: Session, ctx: AuthContext, page: int, page_size: int,
               q: str | None = None, status: int | None = None,
               dept_id: int | None = None, position: str | None = None,
               role: str | None = None) -> tuple[list, int]:
    """列表（data_scope 过滤 + 分页）。role 为角色 code（如 pm/controler）时按拥有该角色过滤。"""
    stmt = select(User)
    # data_scope 过滤：非全量时按部门范围（用户表的归属字段即 dept_id）
    from app.core.deps import apply_data_scope_filter
    from app.user.models import Department

    stmt = apply_data_scope_filter(db, stmt, ctx, owner_field="id", dept_field="dept_id")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.username.like(like), User.name.like(like), User.email.like(like)))
    if status:
        stmt = stmt.where(User.status == status)
    if dept_id:
        stmt = stmt.where(User.dept_id == dept_id)
    if position:
        stmt = stmt.where(User.position == position)
    if role:
        # EXISTS 子查询：用户拥有指定 code 的角色（含多角色并集场景）
        stmt = stmt.where(exists(
            select(UserRole.id).where(
                UserRole.user_id == User.id,
                UserRole.role_id == Role.id,
                Role.code == role,
            )
        ))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    users = list(db.scalars(
        stmt.order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    ))
    # 批量取创建人姓名（列表尾列展示，避免 N+1）
    creator_ids = {u.created_by for u in users if u.created_by}
    creator_names = dict(
        db.execute(select(User.id, User.name).where(User.id.in_(creator_ids))).all()
    ) if creator_ids else {}
    items = []
    for u in users:
        roles = _roles_of(db, u.id)
        dept = db.get(Department, u.dept_id) if u.dept_id else None
        items.append(UserListItem(
            id=u.id, username=u.username, name=u.name, email=u.email, phone=u.phone,
            avatar_url=u.avatar_url, gender=u.gender, status=u.status,
            status_display=STATUS_DISPLAY.get(u.status, str(u.status)),
            position=u.position, dept_id=u.dept_id, dept_name=dept.name if dept else None,
            role_names=[r.name for r in roles], is_super_admin=u.is_super_admin,
            last_login_at=u.last_login_at, created_at=u.created_at,
            created_by_name=creator_names.get(u.created_by) or "",
        ))
    return items, total or 0


def get_detail(db: Session, user_id: int):
    user = _get_or_404(db, user_id)
    roles = _roles_of(db, user_id)
    from app.user.models import Department

    dept_path = []
    dept_id = user.dept_id
    while dept_id:
        d = db.get(Department, dept_id)
        if not d:
            break
        dept_path.insert(0, d.name)
        dept_id = d.parent_id
    recent_logs = list(db.scalars(
        select(OperationLog).where(OperationLog.user_id == user_id)
        .order_by(OperationLog.id.desc()).limit(10)
    ))
    from app.user.schemas.log import OperationLogBrief
    from app.user.schemas.user import UserDetail

    # 取创建人姓名供详情展示（列表页已复用，详情补一次）
    creator_names = {}
    if user.created_by:
        cu = db.get(User, user.created_by)
        if cu:
            creator_names[user.created_by] = cu.name

    return UserDetail(
        id=user.id, username=user.username, name=user.name, email=user.email,
        phone=user.phone, avatar_url=user.avatar_url, gender=user.gender,
        status=user.status, status_display=STATUS_DISPLAY.get(user.status, ""),
        position=user.position, dept_id=user.dept_id,
        dept_name=dept_path[-1] if dept_path else None,
        dept_path_name="/".join(dept_path) if dept_path else None,
        role_names=[r.name for r in roles], is_super_admin=user.is_super_admin,
        last_login_at=user.last_login_at, created_at=user.created_at,
        created_by_name=creator_names.get(user.created_by) or "",
        roles=[{"id": r.id, "code": r.code, "name": r.name, "data_scope": r.data_scope} for r in roles],
        permission_count=0,  # 见 context 缓存口径，详情页实时算代价高，M1 简化
        recent_logs=[OperationLogBrief(
            id=l.id, module=l.module, action=l.action, target_name=l.target_name,
            status=l.status, created_at=l.created_at,
        ) for l in recent_logs],
    )


def create(db: Session, req: UserCreate) -> dict:
    """创建用户：默认密码策略校验 + 至少一角色 + 唯一性。"""
    if db.scalar(select(User).where(User.username == req.username)):
        raise BizError(4090, "登录名已存在")
    if db.scalar(select(User).where(User.email == req.email)):
        raise BizError(4090, "邮箱已存在")
    if req.phone and db.scalar(select(User).where(User.phone == req.phone)):
        raise BizError(4090, "手机号已存在")

    roles = list(db.scalars(select(Role).where(Role.id.in_(req.role_ids))))
    if len(roles) != len(set(req.role_ids)):
        raise BizError(4041, "包含不存在的角色")

    raw_password = req.default_password or auth_service.generate_random_password()
    if err := PasswordService.validate_policy(raw_password):
        raise BizError(4001, f"默认密码不符合策略：{err}")

    with db.begin_nested():
        user = User(
            username=req.username, name=req.name, email=req.email, phone=req.phone,
            gender=req.gender, dept_id=req.dept_id, position=req.position,
            password_hash=PasswordService.hash(raw_password),
            status=UserStatus.ACTIVE.value, must_change_password=True,
        )
        db.add(user)
        db.flush()
        for rid in req.role_ids:
            db.add(UserRole(user_id=user.id, role_id=rid))
    db.commit()
    return {"id": user.id, "initial_password": raw_password}


def update(db: Session, ctx: AuthContext, user_id: int, req: UserUpdate) -> None:
    user = _get_or_404(db, user_id)
    check_super_admin_boundary(db, ctx, user)
    before_dept = user.dept_id
    with db.begin_nested():
        if req.email and req.email != user.email:
            if db.scalar(select(User).where(User.email == req.email, User.id != user_id)):
                raise BizError(4090, "邮箱已存在")
            user.email = req.email
        # phone 唯一约束 uk_users_phone 预检（否则 IntegrityError 落 5001）
        if req.phone and req.phone != user.phone:
            if db.scalar(select(User).where(User.phone == req.phone, User.id != user_id)):
                raise BizError(4090, "手机号已被其他用户使用")
        for f in ("name", "phone", "gender", "dept_id", "position"):
            v = getattr(req, f)
            if v is not None:
                setattr(user, f, v)
    db.commit()
    # 部门变化影响 data_scope 展开 -> 失效
    context_service.invalidate(user_id)
    if req.dept_id is not None and req.dept_id != before_dept:
        context_service.invalidate(user_id)


def change_status(db: Session, ctx: AuthContext, user_id: int, req: UserStatusReq) -> None:
    user = _get_or_404(db, user_id)
    check_super_admin_boundary(db, ctx, user)
    with db.begin_nested():
        user.status = req.status
    db.commit()
    context_service.invalidate(user_id)  # 停用即踢出（配合用户行实时读，双保险）
    if req.status != UserStatus.ACTIVE.value:
        TokenService.revoke_all(user_id)


def reset_password(db: Session, user_id: int, new_password: str | None) -> str:
    """管理员重置密码：返回新密码；踢出全部会话 + 强制改密。"""
    user = _get_or_404(db, user_id)
    raw = new_password or auth_service.generate_random_password()
    if err := PasswordService.validate_policy(raw):
        raise BizError(4001, f"密码不符合策略：{err}")
    with db.begin_nested():
        user.password_hash = PasswordService.hash(raw)
        user.must_change_password = True
    db.commit()
    context_service.invalidate(user_id)
    TokenService.revoke_all(user_id)
    return raw


def assign_roles(db: Session, ctx: AuthContext, user_id: int, role_ids: list[int]) -> None:
    """全量替换用户角色（FOR UPDATE 防并发分配丢失更新）。"""
    user = _get_or_404(db, user_id)
    check_super_admin_boundary(db, ctx, user, new_role_ids=role_ids)
    roles = list(db.scalars(select(Role).where(Role.id.in_(role_ids))))
    if len(roles) != len(set(role_ids)):
        raise BizError(4041, "包含不存在的角色")

    from sqlalchemy import text

    with db.begin_nested():
        db.execute(text("SELECT id FROM users WHERE id=:id FOR UPDATE"), {"id": user_id})
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for rid in role_ids:
            db.add(UserRole(user_id=user_id, role_id=rid))
    db.commit()
    context_service.invalidate(user_id)


def delete(db: Session, ctx: AuthContext, user_id: int) -> None:
    """逻辑删除（status=20 停用）。"""
    user = _get_or_404(db, user_id)
    check_super_admin_boundary(db, ctx, user)
    with db.begin_nested():
        user.status = UserStatus.DISABLED.value
    db.commit()
    context_service.invalidate(user_id)
    TokenService.revoke_all(user_id)


def transfer(db: Session, ctx: AuthContext, from_user_id: int, req: TransferReq) -> TransferReport:
    """批量移交业务资源（M1 骨架：校验 + 报告；业务模块接入点留 TODO）。"""
    from sqlalchemy import text

    _get_or_404(db, from_user_id)
    to_user = _get_or_404(db, req.to_user_id)
    if from_user_id == req.to_user_id:
        raise BizError(4001, "移交目标不能是本人")

    counts: dict[str, int] = {}
    with db.begin_nested():
        # 防两管理员并发对同一人发起移交
        db.execute(text("SELECT id FROM users WHERE id=:id FOR UPDATE"), {"id": from_user_id})
        # TODO(M2+)：各业务模块 batch_reassign 接入点
        # customer_service.batch_reassign(...) / article_service... / approval...
        for key in ("managed_customers", "directed_articles", "controlled_articles",
                    "review_todos", "pending_approvals", "created_customers"):
            if getattr(req.resources, key):
                counts[key] = 0
    db.commit()
    return TransferReport(from_user_id=from_user_id, to_user_id=to_user.id, counts=counts)
