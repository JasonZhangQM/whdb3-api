"""M2: 行政区域迁入 user 模块（customer_regions → user_regions）

Revision ID: b5e2f8a7c3d1
Revises: 1aa1b11ec9a9
Create Date: 2026-08-29 18:05:00.000000

说明：
- MySQL 的 ALTER TABLE ... RENAME 会自动更新引用该表的外键
  （customers.region_id → user_regions.id），无需重建 FK 约束。
- 索引名同步改为新表名前缀，保持与模型 index=True 的命名一致。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b5e2f8a7c3d1'
down_revision: Union[str, None] = '1aa1b11ec9a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('customer_regions', 'user_regions')
    op.execute(
        'ALTER TABLE user_regions RENAME INDEX ix_customer_regions_parent_id '
        'TO ix_user_regions_parent_id'
    )


def downgrade() -> None:
    op.execute(
        'ALTER TABLE user_regions RENAME INDEX ix_user_regions_parent_id '
        'TO ix_customer_regions_parent_id'
    )
    op.rename_table('user_regions', 'customer_regions')
