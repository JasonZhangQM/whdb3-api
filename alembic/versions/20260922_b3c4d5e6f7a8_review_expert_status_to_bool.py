"""review_expert_status_to_bool

v1.9.2：ReviewExpert.status 从 SmallInteger(0/1) 升级为 Boolean(True/False)。
MySQL 的 TINYINT(1) 是 BOOLEAN 的底层存储，数据天然兼容（0→False, 1→True）。

revision: b3c4d5e6f7a8
down_revision: e7f8a9b0c1d2
"""

from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'appraisal_review_experts', 'status',
        existing_type=sa.SmallInteger(),
        type_=sa.Boolean(),
        existing_nullable=False,
        postgresql_using=None,
        existing_server_default=sa.text("1"),
        server_default=sa.text("1"),
    )


def downgrade() -> None:
    op.alter_column(
        'appraisal_review_experts', 'status',
        existing_type=sa.Boolean(),
        type_=sa.SmallInteger(),
        existing_nullable=False,
        existing_server_default=sa.text("1"),
        server_default=sa.text("1"),
    )
