"""drop-warrant-houses-house-name

Revision ID: a1b2c3d4e5f6
Revises: e21b4b2dceb1
Create Date: 2026-09-20 10:00:00.000000

P1：删除 warrant_houses 表的 house_name（楼盘名）列，业务不再需要。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e21b4b2dceb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('warrant_houses', 'house_name')


def downgrade() -> None:
    op.add_column(
        'warrant_houses',
        sa.Column('house_name', sa.String(length=128), nullable=True, comment='楼盘名'),
    )
