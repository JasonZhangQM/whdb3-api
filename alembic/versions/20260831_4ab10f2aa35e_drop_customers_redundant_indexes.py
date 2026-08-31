"""drop_customers_redundant_indexes

Revision ID: 4ab10f2aa35e
Revises: b69d7e2b1c5e
Create Date: 2026-08-31 16:19:41.426670

Drop 5 个 Customer 表低基数 / LIKE 匹配场景下无用的非 FK 索引。
4 个 FK 列(region_id, credit_region_id, group_id, managementor_id)
的 index=True 保留——MySQL 硬约束要求 FK 列必须有索引。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ab10f2aa35e'
down_revision: Union[str, None] = 'b69d7e2b1c5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 非 FK 列，低基数 / LIKE %xxx% 模式，索引无用
    op.drop_index(op.f('ix_customers_genre'), table_name='customers')
    op.drop_index(op.f('ix_customers_custom_state'), table_name='customers')
    op.drop_index(op.f('ix_customers_is_core'), table_name='customers')
    op.drop_index(op.f('ix_customers_is_acceptor'), table_name='customers')
    op.drop_index(op.f('ix_customers_classification'), table_name='customers')


def downgrade() -> None:
    op.create_index(op.f('ix_customers_classification'), 'customers', ['classification'], unique=False)
    op.create_index(op.f('ix_customers_is_acceptor'), 'customers', ['is_acceptor'], unique=False)
    op.create_index(op.f('ix_customers_is_core'), 'customers', ['is_core'], unique=False)
    op.create_index(op.f('ix_customers_custom_state'), 'customers', ['custom_state'], unique=False)
    op.create_index(op.f('ix_customers_genre'), 'customers', ['genre'], unique=False)
