"""baseline: user 模块 9 表

Revision ID: 0001
Revises:
Create Date: 2026-08-26

用户模块全量建表（表名带模块前缀 user_；users 与模块名一致免前缀）。
循环外键处理：user_departments 先建（不带 leader FK）→ users → ALTER 补加。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS_CREATED = {"server_default": sa.text("CURRENT_TIMESTAMP"), "nullable": False}
_TS_UPDATED = {
    "server_default": sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    "nullable": False,
}


def upgrade() -> None:
    # ---- 拓扑序：无依赖表先行（leader FK 延后 ALTER）----
    op.create_table(
        "user_departments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, comment="0=顶级"),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("leader_user_id", sa.BigInteger(), comment="负责人"),
        sa.Column("ordery", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False, comment="10启用20停用"),
        sa.Column("description", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.Column("updated_at", sa.DateTime(), **_TS_UPDATED),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_departments_parent_id", "user_departments", ["parent_id"])

    op.create_table(
        "user_menus",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, comment="0=顶级"),
        sa.Column("caption", sa.String(64), nullable=False, comment="菜单名"),
        sa.Column("icon", sa.String(64)),
        sa.Column("path", sa.String(255), comment="前端路由"),
        sa.Column("component", sa.String(255), comment="前端组件路径"),
        sa.Column("ordery", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.SmallInteger(), nullable=False, comment="10目录20菜单30按钮"),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("keep_alive", sa.Boolean(), nullable=False),
        sa.Column("redirect", sa.String(255)),
        sa.Column("permission_code", sa.String(128), comment="菜单级权限点，前端鉴权单通道"),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.Column("updated_at", sa.DateTime(), **_TS_UPDATED),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_menus_parent_id", "user_menus", ["parent_id"])

    op.create_table(
        "user_roles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(64), nullable=False, comment="super_admin/dept_manager/..."),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255)),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, comment="内置角色不可删"),
        sa.Column(
            "data_scope", sa.SmallInteger(), nullable=False,
            comment="10本人20本部门30本部门及下级40全部50自定义",
        ),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.Column("updated_at", sa.DateTime(), **_TS_UPDATED),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uk_user_roles_code"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False, comment="登录名"),
        sa.Column("name", sa.String(64), nullable=False, comment="姓名"),
        sa.Column("email", sa.String(255), nullable=False, comment="邮箱"),
        sa.Column("phone", sa.String(20), comment="手机号"),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("gender", sa.SmallInteger(), nullable=False, comment="1男2女0未知"),
        sa.Column("dept_id", sa.BigInteger()),
        sa.Column("position", sa.String(64), comment="职务"),
        sa.Column("status", sa.SmallInteger(), nullable=False, comment="10启用20停用30离职"),
        sa.Column("is_super_admin", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, comment="首登强制改密"),
        sa.Column("login_fail_count", sa.SmallInteger(), nullable=False, comment="展示统计；锁定控制流走 Redis 滑窗"),
        sa.Column("last_login_at", sa.DateTime()),
        sa.Column("last_login_ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.Column("updated_at", sa.DateTime(), **_TS_UPDATED),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uk_users_username"),
        sa.UniqueConstraint("email", name="uk_users_email"),
        sa.UniqueConstraint("phone", name="uk_users_phone"),
        sa.ForeignKeyConstraint(["dept_id"], ["user_departments.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_users_dept_id", "users", ["dept_id"])
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("idx_users_dept_status", "users", ["dept_id", "status"])

    # 循环外键：departments.leader_user_id → users.id（建表后补加）
    op.create_foreign_key(
        "fk_dept_leader_user", "user_departments", "users", ["leader_user_id"], ["id"]
    )

    op.create_table(
        "user_login_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("username", sa.String(64)),
        sa.Column("login_type", sa.String(32), comment="login/logout/refresh/lock"),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("status", sa.SmallInteger(), nullable=False, comment="10成功20失败"),
        sa.Column("message", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_login_logs_user_id", "user_login_logs", ["user_id"])
    op.create_index("ix_user_login_logs_username", "user_login_logs", ["username"])
    op.create_index("ix_user_login_logs_created_at", "user_login_logs", ["created_at"])

    op.create_table(
        "user_operation_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("username", sa.String(64)),
        sa.Column("user_name", sa.String(64)),
        sa.Column("dept_id", sa.Integer()),
        sa.Column("module", sa.String(32), comment="user/customer/..."),
        sa.Column("action", sa.String(32), comment="create/update/delete/..."),
        sa.Column("target_type", sa.String(64), comment="操作对象类型"),
        sa.Column("target_id", sa.String(64)),
        sa.Column("target_name", sa.String(255)),
        sa.Column("method", sa.String(16)),
        sa.Column("path", sa.String(512)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("before_data", mysql.JSON()),
        sa.Column("after_data", mysql.JSON()),
        sa.Column("diff", mysql.JSON()),
        sa.Column("status", sa.SmallInteger(), nullable=False, comment="10成功20失败"),
        sa.Column("message", sa.String(512), comment="失败原因"),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_operation_logs_user_id", "user_operation_logs", ["user_id"])
    op.create_index("ix_user_operation_logs_module", "user_operation_logs", ["module"])
    op.create_index("ix_user_operation_logs_target_id", "user_operation_logs", ["target_id"])
    op.create_index("ix_user_operation_logs_created_at", "user_operation_logs", ["created_at"])

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(128), nullable=False, comment="资源:操作，如 customer:create"),
        sa.Column("name", sa.String(64), nullable=False, comment="显示名"),
        sa.Column("module", sa.String(32), nullable=False, comment="所属模块"),
        sa.Column("type", sa.SmallInteger(), nullable=False, comment="10菜单20操作30数据"),
        sa.Column("menu_id", sa.BigInteger(), comment="type=10 时挂菜单"),
        sa.Column("ordery", sa.BigInteger(), nullable=False, comment="排序（避开 order 关键字）"),
        sa.Column("created_at", sa.DateTime(), **_TS_CREATED),
        sa.Column("updated_at", sa.DateTime(), **_TS_UPDATED),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uk_user_permissions_code"),
        sa.ForeignKeyConstraint(["menu_id"], ["user_menus.id"]),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_user_permissions_module", "user_permissions", ["module"])

    op.create_table(
        "user_user_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["user_roles.id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("idx_user_roles_role", "user_user_roles", ["role_id"])

    op.create_table(
        "user_role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        sa.ForeignKeyConstraint(["role_id"], ["user_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["user_permissions.id"], ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )


def downgrade() -> None:
    # 逆序 drop；先撤循环外键
    op.drop_table("user_role_permissions")
    op.drop_table("user_user_roles")
    op.drop_table("user_permissions")
    op.drop_table("user_operation_logs")
    op.drop_table("user_login_logs")
    op.drop_constraint("fk_dept_leader_user", "user_departments", type_="foreignkey")
    op.drop_table("users")
    op.drop_table("user_roles")
    op.drop_table("user_menus")
    op.drop_table("user_departments")
