"""权限上下文引擎：组装 AuthContext + Redis 缓存 + 写点失效链。

缓存：whdb_api:perms:{user_id}（JSON，TTL 30min）；部门树：whdb_api:dept_tree（TTL 1h）。
失效原则：事务提交后 DEL（先持久后失效，把旧权限窗口压到 Redis 往返级）。
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import ERR_TOKEN_INVALID, BizError
from app.core.security import redis_client
from app.user.enums import DataScope, UserStatus
from app.user.models import Department, Permission, Role, RolePermission, User, UserRole

logger = logging.getLogger(__name__)

KEY_PERMS = "whdb_api:perms:{user_id}"
KEY_DEPT_TREE = "whdb_api:dept_tree"
PERMS_TTL = 30 * 60
DEPT_TREE_TTL = 3600


# ---------- 部门树（缓存 + BFS 子树展开） ----------

def _load_dept_tree(db: Session) -> dict[int, list[int]]:
    """{dept_id: [child_ids]}，带 Redis 缓存。"""
    cached = redis_client.get(KEY_DEPT_TREE)
    if cached:
        return {int(k): v for k, v in json.loads(cached).items()}
    rows = db.execute(select(Department.id, Department.parent_id)).all()
    tree: dict[int, list[int]] = {}
    for dept_id, parent_id in rows:
        tree.setdefault(parent_id, []).append(dept_id)
        tree.setdefault(dept_id, [])
    try:
        redis_client.setex(KEY_DEPT_TREE, DEPT_TREE_TTL, json.dumps(tree))
    except Exception:
        logger.warning("dept_tree cache write failed", exc_info=True)
    return tree


def _descendants(tree: dict[int, list[int]], dept_id: int | None) -> list[int]:
    """内存 BFS：dept_id 及其全部下级。"""
    if dept_id is None:
        return []
    result, queue = [dept_id], list(tree.get(dept_id, []))
    while queue:
        node = queue.pop(0)
        result.append(node)
        queue.extend(tree.get(node, []))
    return result


def invalidate_dept_tree() -> None:
    """部门增删改后调用。"""
    try:
        redis_client.delete(KEY_DEPT_TREE)
    except Exception:
        logger.warning("dept_tree cache invalidate failed", exc_info=True)


# ---------- 权限上下文 ----------

def _load_uncached(db: Session, user: User) -> tuple[set[str], set[str], int]:
    """三表联查：角色码并集 / 权限码并集 / data_scope 取最大。"""
    rows = db.execute(
        select(Role.code, Role.data_scope, Permission.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user.id)
    ).all()
    role_codes = {r[0] for r in rows}
    perm_codes = {r[2] for r in rows}
    max_scope = max((r[1] for r in rows), default=DataScope.SELF.value)
    return role_codes, perm_codes, max_scope


def load_auth_context(db: Session, user_id: int) -> AuthContext:
    """get_current_user 每请求调用：用户行实时读库 + 权限上下文走缓存。"""
    user = db.get(User, user_id)
    if user is None:
        raise BizError(ERR_TOKEN_INVALID, "用户不存在")
    if user.status != UserStatus.ACTIVE.value:
        raise BizError(4013, "账号已停用或离职")

    cached = redis_client.get(KEY_PERMS.format(user_id=user_id))
    if cached:
        data = json.loads(cached)
        return AuthContext(
            user_id=user.id,
            username=user.username,
            role_codes=set(data["role_codes"]),
            permission_codes=set(data["permission_codes"]),
            data_scope=data["data_scope"],
            dept_scope_ids=data["dept_scope_ids"],
            is_super_admin=user.is_super_admin or "super_admin" in data["role_codes"],
        )

    role_codes, perm_codes, data_scope = _load_uncached(db, user)
    if user.is_super_admin:
        data_scope = DataScope.ALL.value

    # data_scope 展开部门子树（三态语义见详设 §5.3）
    if data_scope == DataScope.SELF.value:
        dept_scope_ids: list[int] | None = []
    elif data_scope == DataScope.DEPT.value:
        dept_scope_ids = [user.dept_id] if user.dept_id else []
    elif data_scope == DataScope.DEPT_AND_CHILD.value:
        dept_scope_ids = _descendants(_load_dept_tree(db), user.dept_id)
    else:  # ALL / CUSTOM
        dept_scope_ids = None

    ctx = AuthContext(
        user_id=user.id,
        username=user.username,
        role_codes=role_codes,
        permission_codes=perm_codes,
        data_scope=data_scope,
        dept_scope_ids=dept_scope_ids,
        is_super_admin=user.is_super_admin or "super_admin" in role_codes,
    )
    try:
        redis_client.setex(
            KEY_PERMS.format(user_id=user_id),
            PERMS_TTL,
            json.dumps({
                "role_codes": sorted(role_codes),
                "permission_codes": sorted(perm_codes),
                "data_scope": data_scope,
                "dept_scope_ids": dept_scope_ids,
                "is_super_admin": ctx.is_super_admin,
            }),
        )
    except Exception:
        logger.warning("perms cache write failed", exc_info=True)
    return ctx


# ---------- 写点失效（详设 §5.4 穷举清单） ----------

def invalidate(user_id: int) -> None:
    try:
        redis_client.delete(KEY_PERMS.format(user_id=user_id))
    except Exception:
        logger.warning("perms invalidate failed user=%s", user_id, exc_info=True)


def invalidate_users(user_ids: list[int]) -> None:
    """批量失效（角色权限变更 -> 全部绑定用户）。>100 按 500/批 pipeline。"""
    try:
        for i in range(0, len(user_ids), 500):
            pipe = redis_client.pipeline()
            for uid in user_ids[i : i + 500]:
                pipe.delete(KEY_PERMS.format(user_id=uid))
            pipe.execute()
    except Exception:
        logger.warning("perms batch invalidate failed", exc_info=True)


def invalidate_role(db: Session, role_id: int) -> None:
    """角色权限变化 -> 反查绑定用户批量失效。"""
    user_ids = db.scalars(
        select(UserRole.user_id).where(UserRole.role_id == role_id)
    ).all()
    if user_ids:
        invalidate_users(list(user_ids))


def invalidate_dept_subtree(db: Session, dept_id: int) -> None:
    """部门树变动 -> 该部门子树内所有用户 + 全站 dept_tree。"""
    invalidate_dept_tree()
    tree = _load_dept_tree(db)
    dept_ids = set(_descendants(tree, dept_id))
    if not dept_ids:
        return
    user_ids = db.scalars(
        select(User.id).where(User.dept_id.in_(dept_ids))
    ).all()
    if user_ids:
        invalidate_users(list(user_ids))
