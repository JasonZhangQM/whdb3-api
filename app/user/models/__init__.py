# 导出本模块全部模型（alembic 与跨模块引用的单一发现入口）
from app.user.models.region import Region
from app.user.models.user import (
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

__all__ = [
    "User",
    "Role",
    "UserRole",
    "Permission",
    "RolePermission",
    "Menu",
    "Department",
    "OperationLog",
    "LoginLog",
    "Region",
]
