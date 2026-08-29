"""用户模块模型：9 张表（表名带模块前缀 user_）。

外键按 R1 规则用字符串表名，模型层不 import 其他模块的模型类。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名")
    name: Mapped[str] = mapped_column(String(64), comment="姓名")
    email: Mapped[str] = mapped_column(String(255), unique=True, comment="邮箱")
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, comment="手机号")
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    password_hash: Mapped[str] = mapped_column(String(255))
    gender: Mapped[int] = mapped_column(SmallInteger, default=0, comment="1男2女0未知")
    # 免前缀规则①：本表即 users；子表带前缀
    dept_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_departments.id"), index=True
    )
    position: Mapped[str | None] = mapped_column(String(64), comment="职务")
    status: Mapped[int] = mapped_column(SmallInteger, default=10, index=True, comment="10启用20停用30离职")
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, comment="首登强制改密")
    login_fail_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, comment="展示统计；锁定控制流走 Redis 滑窗"
    )
    last_login_at: Mapped[datetime | None]
    last_login_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        # 部门+状态复合索引（用户列表按部门筛选的常用组合，与 M1 baseline 对齐）
        Index("idx_users_dept_status", "dept_id", "status"),
    )


class Role(Base):
    __tablename__ = "user_roles"

    code: Mapped[str] = mapped_column(String(64), unique=True, comment="super_admin/dept_manager/...")
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255))
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, comment="内置角色不可删")
    data_scope: Mapped[int] = mapped_column(SmallInteger, default=20, comment="10本人20本部门30本部门及下级40全部50自定义")


class UserRole(Base):
    """用户-角色中间表（id 主键 + 复合唯一，统一 Base 审计字段）。"""

    __tablename__ = "user_user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("user_roles.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role_pair"),
        # role_id FK 的支撑索引（沿用 M1 名字）
        Index("idx_user_roles_role", "role_id"),
    )


class Permission(Base):
    __tablename__ = "user_permissions"

    code: Mapped[str] = mapped_column(String(128), unique=True, comment="资源:操作，如 customer:create")
    name: Mapped[str] = mapped_column(String(64), comment="显示名")
    module: Mapped[str] = mapped_column(String(32), index=True, comment="所属模块")
    type: Mapped[int] = mapped_column(SmallInteger, comment="10菜单20操作30数据")
    menu_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_menus.id"), comment="type=10 时挂菜单"
    )
    ordery: Mapped[int] = mapped_column(BigInteger, default=0, comment="排序（避开 order 关键字）")


class RolePermission(Base):
    """角色-权限中间表（id 主键 + 复合唯一，统一 Base 审计字段）。"""

    __tablename__ = "user_role_permissions"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("user_roles.id", ondelete="CASCADE"), index=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("user_permissions.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission_pair"),
    )


class Menu(Base):
    __tablename__ = "user_menus"

    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True, comment="0=顶级")
    caption: Mapped[str] = mapped_column(String(64), comment="菜单名")
    icon: Mapped[str | None] = mapped_column(String(64))
    path: Mapped[str | None] = mapped_column(String(255), comment="前端路由")
    component: Mapped[str | None] = mapped_column(String(255), comment="前端组件路径")
    ordery: Mapped[int] = mapped_column(BigInteger, default=0)
    type: Mapped[int] = mapped_column(SmallInteger, comment="10目录20菜单30按钮")
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    keep_alive: Mapped[bool] = mapped_column(Boolean, default=False)
    redirect: Mapped[str | None] = mapped_column(String(255))
    permission_code: Mapped[str | None] = mapped_column(
        String(128), comment="菜单级权限点，前端鉴权单通道"
    )


class Department(Base):
    __tablename__ = "user_departments"

    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True, comment="0=顶级")
    name: Mapped[str] = mapped_column(String(64))
    # use_alter：与 users.dept_id 互为循环外键，建表后 ALTER 补加（避免建表顺序死锁）
    leader_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", use_alter=True, name="fk_dept_leader_user"),
        comment="负责人",
    )
    ordery: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10启用20停用")
    description: Mapped[str | None] = mapped_column(String(255))


class OperationLog(Base):
    __tablename__ = "user_operation_logs"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    user_name: Mapped[str | None] = mapped_column(String(64))
    dept_id: Mapped[int | None]
    module: Mapped[str | None] = mapped_column(String(32), index=True, comment="user/customer/...")
    action: Mapped[str | None] = mapped_column(String(32), comment="create/update/delete/...")
    target_type: Mapped[str | None] = mapped_column(String(64), comment="操作对象类型")
    target_id: Mapped[str | None] = mapped_column(String(64), index=True)
    target_name: Mapped[str | None] = mapped_column(String(255))
    method: Mapped[str | None] = mapped_column(String(16))
    path: Mapped[str | None] = mapped_column(String(512))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    before_data: Mapped[dict | None] = mapped_column(JSON)
    after_data: Mapped[dict | None] = mapped_column(JSON)
    diff: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[int] = mapped_column(SmallInteger, comment="10成功20失败")
    message: Mapped[str | None] = mapped_column(String(512), comment="失败原因")
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP"), index=True
    )


class LoginLog(Base):
    __tablename__ = "user_login_logs"

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    login_type: Mapped[int | None] = mapped_column(String(32), comment="login/logout/refresh/lock")
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[int] = mapped_column(SmallInteger, comment="10成功20失败")
    message: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP"), index=True
    )


# 列表筛选复合索引（unique 约束已在各列定义内）
User.__table_args__ = (Index("idx_users_dept_status", "dept_id", "status"),)
