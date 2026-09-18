"""rename-appraisal-supplyor-id-to-supplier-id

Revision ID: e21b4b2dceb1
Revises: 9d44ceed5e7e
Create Date: 2026-09-18 11:00:00.000000

P1：修复拼写错误（supplyor → supplier），仅 appraisal_supplies 表。
MySQL RENAME COLUMN 会自动处理 FK 引用，无需手动操作约束。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e21b4b2dceb1'
down_revision: Union[str, None] = '9d44ceed5e7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE appraisal_supplies "
        "RENAME COLUMN supplyor_id TO supplier_id"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appraisal_supplies "
        "RENAME COLUMN supplier_id TO supplyor_id"
    )
