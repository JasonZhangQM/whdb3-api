"""drop article_single_quotas table

Revision ID: 20260915_f8a9b0c1d2e3
Revises: 20260915_e2f3a4b5c6d7
Create Date: 2026-09-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260915_f8a9b0c1d2e3"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL 自动删除相关 FK 和 Index
    op.drop_table("article_single_quotas")


def downgrade() -> None:
    op.create_table(
        "article_single_quotas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("credit_model", sa.SmallInteger(), nullable=False, comment="授信类型"),
        sa.Column("credit_amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("flow_rate", sa.Text(), comment="费率（文本）"),
        sa.Column("remark", sa.Text()),
        sa.Column("created_by", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.UniqueConstraint("article_id", "credit_model", name="uq_single_quota_article_model"),
    )
