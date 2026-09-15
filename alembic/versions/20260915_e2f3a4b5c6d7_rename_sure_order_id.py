"""rename article_sures.lending_order_id → order_id

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-15 19:00:00.000000

MySQL RENAME COLUMN 会自动：
- 更新引用该列的 FK 的 referencing column 名
- 更新 UniqueConstraint 的列名（uq_sure_order_type 覆盖该列）
目标表 article_order 是新名（上一个迁移已 RENAME），不动。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'article_sures', 'lending_order_id',
        new_column_name='order_id',
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_comment='放款次序',
    )


def downgrade() -> None:
    op.alter_column(
        'article_sures', 'order_id',
        new_column_name='lending_order_id',
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_comment='放款次序',
    )
