"""appraisal_review_experts → appraisal_experts 表名重命名

模型：ReviewExpert.__tablename__ + 2 处 ForeignKey 目标名同步修改。
MySQL RENAME TABLE 会自动更新 FK 引用，无需手动 drop/add FK。
"""

from alembic import op
import sqlalchemy as sa

revision = "20260922_rename_experts_table"
down_revision = "20260922_compere_fk"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("appraisal_review_experts", "appraisal_experts")


def downgrade():
    op.rename_table("appraisal_experts", "appraisal_review_experts")
