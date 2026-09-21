"""drop_appraisal_expert_categories_table

v1.9.1：ExpertCategory 模型已删除，对应表 appraisal_expert_categories 清空。
前置迁移 e5f7a9b1c3d4 已 drop FK + drop category_id 列 + drop deleted_at 列，
本次只需 DROP TABLE。

revision: e7f8a9b0c1d2
down_revision: e5f7a9b1c3d4
"""

from alembic import op

revision = 'e7f8a9b0c1d2'
down_revision = 'e5f7a9b1c3d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('appraisal_expert_categories')


def downgrade() -> None:
    import sqlalchemy as sa
    op.create_table(
        'appraisal_expert_categories',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False, comment='类别名称'),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('status', sa.SmallInteger(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
