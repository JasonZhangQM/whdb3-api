"""warrants.created_by 覆写移除：显式索引转 FK 隐含索引

Revision ID: b3a07d2c91e4
Revises: e550f9c682eb
Create Date: 2026-08-29 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3a07d2c91e4'
down_revision: Union[str, None] = 'e550f9c682eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 一条原子语句：删 FK + 删显式索引 + 重加 FK。
    # 重加 FK 时 MySQL 自动重建名为 created_by 的支撑索引，
    # 该索引被反射识别为 FK 隐含索引，alembic autogenerate 不再报 diff，
    # 模型侧即可统一使用 Base.created_by（无索引版本）。
    op.execute(
        "ALTER TABLE warrants "
        "DROP FOREIGN KEY warrants_ibfk_1, "
        "DROP INDEX ix_warrants_created_by, "
        "ADD CONSTRAINT fk_warrants_created_by_user FOREIGN KEY (created_by) REFERENCES users (id)"
    )


def downgrade() -> None:
    # 逆向：恢复显式索引（模型需重新加上 index=True 覆写）
    op.execute(
        "ALTER TABLE warrants "
        "DROP FOREIGN KEY fk_warrants_created_by_user, "
        "DROP INDEX created_by, "
        "ADD INDEX ix_warrants_created_by (created_by), "
        "ADD CONSTRAINT warrants_ibfk_1 FOREIGN KEY (created_by) REFERENCES users (id)"
    )
