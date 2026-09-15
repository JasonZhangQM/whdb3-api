"""article_sures.remark Text -> String(256)

Revision ID: 20260915_b2c3d4e5f6a7
Revises: 20260915_a1b2c3d4e5f6
Create Date: 2026-09-15 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260915_b2c3d4e5f6a7"
down_revision = "20260915_a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Text 收窄为 VARCHAR(256)：备注为短文本，收窄前数据均远小于 256
    op.alter_column(
        "article_sures",
        "remark",
        existing_type=sa.Text(),
        type_=sa.String(length=256),
        existing_nullable=True,
        comment="备注",
    )


def downgrade() -> None:
    op.alter_column(
        "article_sures",
        "remark",
        existing_type=sa.String(length=256),
        type_=sa.Text(),
        existing_nullable=True,
        existing_comment="备注",
    )
