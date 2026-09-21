"""drop expert_category_fk_and_deleted_at

模型对齐：ReviewExpert 模型删除 category_id FK（专家类别降维到字典但
保留表）+ 删除 deleted_at（改用 status=0 停用）。remark 字段保留。

revision: e5f7a9b1c3d4
down_revision: d0e1f2a3b4c5
"""

from alembic import op
import sqlalchemy as sa

revision = 'e5f7a9b1c3d4'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 删 FK
    op.drop_constraint(
        'appraisal_review_experts_ibfk_1',
        'appraisal_review_experts',
        type_='foreignkey',
    )
    # 2. 删列
    op.drop_column('appraisal_review_experts', 'category_id')
    op.drop_column('appraisal_review_experts', 'deleted_at')


def downgrade() -> None:
    op.add_column(
        'appraisal_review_experts',
        sa.Column('deleted_at', sa.DateTime(), nullable=True, comment='软删时间'),
    )
    op.add_column(
        'appraisal_review_experts',
        sa.Column('category_id', sa.BigInteger(), nullable=True, comment='专家类别'),
    )
    op.create_foreign_key(
        'appraisal_review_experts_ibfk_1',
        'appraisal_review_experts',
        'appraisal_expert_categories',
        ['category_id'], ['id'],
        ondelete='RESTRICT',
    )
