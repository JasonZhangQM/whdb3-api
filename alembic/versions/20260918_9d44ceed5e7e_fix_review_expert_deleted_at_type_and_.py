"""fix-review-expert-deleted-at-type-and-add-supply-resolved-at

Revision ID: 9d44ceed5e7e
Revises: 27f4a5b6c7d8
Create Date: 2026-09-18 09:22:18.682186

v1.2 评审模块变更（仅 2 项，其余差异已排除）：
1. appraisal_review_experts.deleted_at: VARCHAR(32) → DATETIME（AGENTS.md §4.1 对齐）
2. appraisal_supplies: 新增 resolved_at DATETIME（补调完成登记时间）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = '9d44ceed5e7e'
down_revision: Union[str, None] = '27f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 软删字段类型修正：String(32) → DateTime
    op.alter_column(
        'appraisal_review_experts', 'deleted_at',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32),
        type_=sa.DateTime(),
        comment='软删时间（有引用时停用）',
        existing_comment='软删时间',
        existing_nullable=True,
    )
    # 2. 补调完成登记时间列
    op.add_column(
        'appraisal_supplies',
        sa.Column('resolved_at', sa.DateTime(), nullable=True, comment='完成登记时间'),
    )


def downgrade() -> None:
    op.drop_column('appraisal_supplies', 'resolved_at')
    op.alter_column(
        'appraisal_review_experts', 'deleted_at',
        existing_type=sa.DateTime(),
        type_=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32),
        comment='软删时间',
        existing_comment='软删时间（有引用时停用）',
        existing_nullable=True,
    )
