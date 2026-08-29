"""drop builtin roles assistant reviewer, controler scope to self

Revision ID: c92090d6ea2c
Revises: 6552ff1b13e5
Create Date: 2026-08-30 00:05:09.847850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c92090d6ea2c'
down_revision: Union[str, None] = '6552ff1b13e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 删除内置角色 assistant / reviewer（外键 CASCADE 自动清理 user_user_roles / role_permissions）
    op.execute(
        "DELETE FROM user_roles WHERE code IN ('assistant', 'reviewer') AND is_builtin = 1"
    )
    # controler 数据范围：本部门(20) → 本人(10)
    op.execute(
        "UPDATE user_roles SET data_scope = 10 WHERE code = 'controler'"
    )


def downgrade() -> None:
    # 回滚：恢复 controler 数据范围，重建两个内置角色（角色权限分配不恢复，需重跑 seed）
    op.execute(
        "UPDATE user_roles SET data_scope = 20 WHERE code = 'controler'"
    )
    op.execute(
        "INSERT INTO user_roles (code, name, data_scope, is_builtin, description, created_at, updated_at) "
        "VALUES ('assistant', '项目助理', 10, 1, '本人', NOW(), NOW()), "
        "('reviewer', '保后专员', 20, 1, '本部门', NOW(), NOW()) "
        "ON DUPLICATE KEY UPDATE data_scope = VALUES(data_scope)"
    )
