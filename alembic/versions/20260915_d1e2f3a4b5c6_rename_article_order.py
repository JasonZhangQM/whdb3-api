"""rename article_lending_orders → article_order + model ArticleLendingOrder → ArticleOrder

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7g8a9
Create Date: 2026-09-15 18:00:00.000000

纯 RENAME TABLE，MySQL 会自动修正所有引用该表的 FK 的 referenced_table_name。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c4d5e6f7g8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table('article_lending_orders', 'article_order')


def downgrade() -> None:
    op.rename_table('article_order', 'article_lending_orders')
