"""fix_customer_contacts_timestamp_defaults

Revision ID: 7d3e9f8a2b15
Revises: f3b7c9d2e1a4
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7d3e9f8a2b15'
down_revision: Union[str, None] = 'f3b7c9d2e1a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # customer_contacts 表建表迁移遗漏 DEFAULT，导致 INSERT 时报
    # "Field 'created_at' doesn't have a default value"
    op.execute(
        "ALTER TABLE customer_contacts "
        "MODIFY COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "MODIFY COLUMN updated_at DATETIME NOT NULL "
        "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
    )


def downgrade() -> None:
    # 回滚时也得把 DEFAULT 去掉——不建议回滚该迁移
    op.execute(
        "ALTER TABLE customer_contacts "
        "MODIFY COLUMN created_at DATETIME NOT NULL, "
        "MODIFY COLUMN updated_at DATETIME NOT NULL"
    )
