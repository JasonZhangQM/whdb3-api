"""article_sures reparent to lending_order + add article_sure_warrants M2M

Revision ID: c4d5e6f7g8a9
Revises: 9b3c4d5e6f01
Create Date: 2026-09-15 11:00:00.000000

旧系统对齐：
- LendingSures.lending → LendingOrder    ← ArticleSure.lending_order_id（新增 FK）
- LendingCustoms (O2O LendingSures)      ← ArticleSureCustomer 已是 M2M，不动
- LendingWarrants (O2O LendingSures + M2M Warrants) ← ArticleSureWarrant（新增 M2M 中间表）

article_sures 空表，直接改列改约束。
MySQL 约束处理：FK article_sures_ibfk_1 依赖 uq_sure_article_type 索引，
改 unique 顺序必须先 DROP FK → 再 DROP unique → 再加 INDEX 支撑 FK → 恢复 FK。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7g8a9'
down_revision: Union[str, None] = '9b3c4d5e6f01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 1. 加 lending_order_id 列 ===
    op.add_column(
        'article_sures',
        sa.Column('lending_order_id', sa.BigInteger(), nullable=False, comment='放款次序'),
    )

    # === 2. 加新 FK + 新 unique（lending_order_id, sure_type）===
    op.create_foreign_key(
        op.f('article_sures_ibfk_lending_order'),
        'article_sures', 'article_lending_orders',
        ['lending_order_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_unique_constraint(
        op.f('uq_sure_order_type'), 'article_sures',
        ['lending_order_id', 'sure_type'],
    )

    # === 3. MySQL FK article_sures_ibfk_1(article_id) 依赖 uq_sure_article_type ===
    # 顺序：DROP FK → DROP old unique → 加 INDEX(article_id) 支撑 FK → 恢复 FK
    op.drop_constraint(op.f('article_sures_ibfk_1'), 'article_sures', type_='foreignkey')
    op.drop_constraint(op.f('uq_sure_article_type'), 'article_sures', type_='unique')
    op.create_index('ix_article_sures_article_id', 'article_sures', ['article_id'])
    op.create_foreign_key(
        op.f('article_sures_ibfk_1'),
        'article_sures', 'articles',
        ['article_id'], ['id'],
        ondelete='CASCADE',
    )

    # === 4. 新建 article_sure_warrants（M2M sure_id ↔ warrant_id）===
    op.create_table(
        'article_sure_warrants',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('sure_id', sa.BigInteger(), nullable=False),
        sa.Column('warrant_id', sa.BigInteger(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['sure_id'], ['article_sures.id'],
            name=op.f('article_sure_warrants_ibfk_1'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['warrant_id'], ['warrants.id'],
            name=op.f('article_sure_warrants_ibfk_2'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('article_sure_warrants_ibfk_3'), ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('article_sure_warrants_pkey')),
        sa.UniqueConstraint('sure_id', 'warrant_id', name=op.f('uq_sure_warrant_sure_warrant')),
    )


def downgrade() -> None:
    # === 反向：删新表 → 恢复 unique → 删多余 INDEX + FK + 列 ===
    op.drop_table('article_sure_warrants')

    op.drop_constraint(op.f('uq_sure_order_type'), 'article_sures', type_='unique')
    op.drop_constraint(op.f('article_sures_ibfk_lending_order'), 'article_sures', type_='foreignkey')
    op.drop_column('article_sures', 'lending_order_id')

    op.drop_constraint(op.f('article_sures_ibfk_1'), 'article_sures', type_='foreignkey')
    op.drop_index('ix_article_sures_article_id', 'article_sures')
    op.create_unique_constraint(
        op.f('uq_sure_article_type'), 'article_sures',
        ['article_id', 'sure_type'],
    )
    op.create_foreign_key(
        op.f('article_sures_ibfk_1'),
        'article_sures', 'articles',
        ['article_id'], ['id'],
        ondelete='CASCADE',
    )
