"""customer_groups comment 同步

Revision ID: b1c2d3e4f5a6
Revises: e548e04d5ad0
Create Date: 2026-09-21

仅同步 customer_groups 表 4 列 comment 与 SQLAlchemy 模型声明一致，
无结构改动（无字段新增/删除/类型变更）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'e548e04d5ad0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # parent_customer_id: '母公司客户' → '母公司'
    op.alter_column(
        'customer_groups', 'parent_customer_id',
        existing_type=mysql.BIGINT(),
        comment='母公司',
        existing_comment='母公司客户',
        existing_nullable=True,
    )
    # credit_amount: '集团总授信额度' → '集信额度'
    op.alter_column(
        'customer_groups', 'credit_amount',
        existing_type=mysql.DECIMAL(precision=18, scale=2),
        comment='集信额度',
        existing_comment='集团总授信额度',
        existing_nullable=False,
    )
    # description: 无 comment → '备注'
    op.alter_column(
        'customer_groups', 'description',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255),
        comment='备注',
        existing_comment=None,
        existing_nullable=True,
    )
    # status: '10启用20停用' → '状态:CommonStatus'
    op.alter_column(
        'customer_groups', 'status',
        existing_type=mysql.SMALLINT(),
        comment='状态:CommonStatus',
        existing_comment='10启用20停用',
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'customer_groups', 'status',
        existing_type=mysql.SMALLINT(),
        comment='10启用20停用',
        existing_comment='状态:CommonStatus',
        existing_nullable=False,
    )
    op.alter_column(
        'customer_groups', 'description',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255),
        comment=None,
        existing_comment='备注',
        existing_nullable=True,
    )
    op.alter_column(
        'customer_groups', 'credit_amount',
        existing_type=mysql.DECIMAL(precision=18, scale=2),
        comment='集团总授信额度',
        existing_comment='集信额度',
        existing_nullable=False,
    )
    op.alter_column(
        'customer_groups', 'parent_customer_id',
        existing_type=mysql.BIGINT(),
        comment='母公司客户',
        existing_comment='母公司',
        existing_nullable=True,
    )
