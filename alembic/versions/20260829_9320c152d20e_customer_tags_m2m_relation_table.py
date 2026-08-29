"""customer tags m2m relation table

Revision ID: 9320c152d20e
Revises: b5e2f8a7c3d1
Create Date: 2026-08-29 20:14:13.643372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '9320c152d20e'
down_revision: Union[str, None] = 'b5e2f8a7c3d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('customer_tag_relations',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('customer_id', sa.BigInteger(), nullable=False),
    sa.Column('tag_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['customer_extra_tags.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('customer_id', 'tag_id', name='uq_customer_tag')
    )
    op.create_index(op.f('ix_customer_tag_relations_customer_id'), 'customer_tag_relations', ['customer_id'], unique=False)
    op.create_index(op.f('ix_customer_tag_relations_tag_id'), 'customer_tag_relations', ['tag_id'], unique=False)
    # 数据迁移：customers.tags JSON 数组 → 中间表行（幂等：INSERT IGNORE 跳过已存在/无效 tag id）
    op.execute(
        "INSERT IGNORE INTO customer_tag_relations (customer_id, tag_id) "
        "SELECT c.id, jt.tag_id "
        "FROM customers c "
        "JOIN JSON_TABLE(c.tags, '$[*]' COLUMNS (tag_id BIGINT PATH '$')) jt "
        "JOIN customer_extra_tags t ON t.id = jt.tag_id "
        "WHERE c.tags IS NOT NULL AND JSON_TYPE(c.tags) = 'ARRAY'"
    )
    op.drop_column('customers', 'tags')


def downgrade() -> None:
    op.add_column('customers', sa.Column('tags', mysql.JSON(), nullable=True, comment='标签 id 数组'))
    # 回滚数据迁移：中间表行 → JSON 数组（按客户聚合）
    op.execute(
        "UPDATE customers c SET tags = ("
        "  SELECT CAST(CONCAT('[', GROUP_CONCAT(r.tag_id ORDER BY r.tag_id), ']') AS JSON) "
        "  FROM customer_tag_relations r WHERE r.customer_id = c.id)"
    )
    op.drop_index(op.f('ix_customer_tag_relations_tag_id'), table_name='customer_tag_relations')
    op.drop_index(op.f('ix_customer_tag_relations_customer_id'), table_name='customer_tag_relations')
    op.drop_table('customer_tag_relations')
