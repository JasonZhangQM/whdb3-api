"""add-warrant-house-apps-category

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20 11:00:00.000000

P1：warrant_house_apps 字典表新增 category 列，用于按分类(住宅/办公/商业/厂房/其他)分组。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'warrant_house_apps',
        sa.Column('category', sa.SmallInteger(), nullable=True, comment='分类(11住宅21办公31商业41厂房91其他)'),
    )


def downgrade() -> None:
    op.drop_column('warrant_house_apps', 'category')
