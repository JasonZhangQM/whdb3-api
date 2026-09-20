"""drop-warrant-house-apps-parent-id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-20 11:45:00.000000

P1：方案 B，warrant_house_apps 放弃树形，改用扁平列表+category 分组。
删除 parent_id 列和对应的索引。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_warrant_house_apps_parent_id'), 'warrant_house_apps')
    op.drop_column('warrant_house_apps', 'parent_id')


def downgrade() -> None:
    op.add_column(
        'warrant_house_apps',
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(op.f('ix_warrant_house_apps_parent_id'), 'warrant_house_apps', ['parent_id'], unique=False)
