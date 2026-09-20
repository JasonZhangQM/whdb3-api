"""warrant_house_apps-drop-and-warrant-houses-refactor

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-20 12:30:00.000000

P1：房产用途不再维护独立字典表，改为 WarrantHouse 上直接存用途名称 + 类型枚举。
- 删除 warrant_house_apps 表
- warrant_houses.house_app : BIGINT(字典FK) → VARCHAR(128)(用途名称)
- warrant_houses 新增 app_category : SMALLINT(类型枚举)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删除旧字典表
    op.drop_table('warrant_house_apps')

    # 2. warrant_houses.house_app : BIGINT → VARCHAR(128), nullable
    op.alter_column(
        'warrant_houses', 'house_app',
        existing_type=sa.BigInteger(),
        new_column_name='house_app',
        type_=sa.String(128),
        nullable=True,
        comment='产权用途',
        existing_nullable=False,
    )

    # 3. 新增 app_category
    op.add_column(
        'warrant_houses',
        sa.Column('app_category', sa.SmallInteger(), nullable=True, comment='类型(11住宅21办公31商业41厂房91其他)'),
    )


def downgrade() -> None:
    # 1. 重建字典表（最小必要字段）
    op.create_table(
        'warrant_house_apps',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('category', sa.SmallInteger(), nullable=True),
        sa.Column('ordery', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('status', sa.SmallInteger(), nullable=False, server_default=sa.text('10')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )

    # 2. 删 app_category
    op.drop_column('warrant_houses', 'app_category')

    # 3. house_app : VARCHAR(128) → BIGINT, NOT NULL
    op.alter_column(
        'warrant_houses', 'house_app',
        existing_type=sa.String(128),
        type_=sa.BigInteger(),
        nullable=False,
        comment='房产用途（字典）',
        existing_nullable=True,
    )
