"""drop_customers_custom_state

Revision ID: f3b7c9d2e1a4
Revises: ad9af5bd88d8
Create Date: 2026-09-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3b7c9d2e1a4'
down_revision: Union[str, None] = 'ad9af5bd88d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 客户注销功能随之移除：custom_state 不再承载逻辑注销语义
    op.drop_column('customers', 'custom_state')


def downgrade() -> None:
    op.add_column(
        'customers',
        sa.Column('custom_state', sa.SMALLINT(), autoincrement=False,
                  nullable=False, server_default='10',
                  comment='10正常20反担保30小贷90注销'),
    )
