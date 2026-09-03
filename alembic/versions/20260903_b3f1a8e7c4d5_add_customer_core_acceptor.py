"""add is_core and is_acceptor to customers

Revision ID: 20260903_b3f1a8e7c4d5
Revises: 450c3f059755
Create Date: 2026-09-03 17:30:00

之前的 ad9af5bd88d8 迁移删除了这两个字段（客户注销语义整体移除），
现在需要重新加回来作为普通业务标记。
"""

import sqlalchemy as sa
from alembic import op

revision = "20260903_b3f1a8e7c4d5"
down_revision = "450c3f059755"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("is_core", sa.Boolean, server_default=sa.text("0"), nullable=False, comment="是否核心企业"),
    )
    op.add_column(
        "customers",
        sa.Column("is_acceptor", sa.Boolean, server_default=sa.text("0"), nullable=False, comment="是否承兑人"),
    )


def downgrade() -> None:
    op.drop_column("customers", "is_core")
    op.drop_column("customers", "is_acceptor")
