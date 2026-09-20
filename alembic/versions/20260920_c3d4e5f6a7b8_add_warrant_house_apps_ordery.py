"""add-warrant-house-apps-ordery

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-20 11:30:00.000000

P1：warrant_house_apps 字典表新增 ordery 列（排序，避开 order 关键字）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'warrant_house_apps',
        sa.Column('ordery', sa.BigInteger(), nullable=False, server_default=sa.text('0'), comment='排序（避开 order 关键字）'),
    )


def downgrade() -> None:
    op.drop_column('warrant_house_apps', 'ordery')
