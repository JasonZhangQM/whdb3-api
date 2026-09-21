"""customer_groups.parent_id 加自引用 FK ON DELETE SET NULL

Revision ID: d0e1f2a3b4c5
Revises: c7d8e9f0a1b2
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = 'fk_customer_groups_parent_id'


def upgrade() -> None:
    op.create_foreign_key(
        FK_NAME,
        'customer_groups', 'customer_groups',
        ['parent_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, 'customer_groups', type_='foreignkey')
