"""drop evaluate/auction/inquiry columns from warrants main table

Revision ID: e8b4f2a912c0
Revises: c7a3e91f0d24
Create Date: 2026-09-02

warrants 主表只保留基本信息（warrant_num/warrant_type/remark）与入库状态 warrant_state。
评估历史走 warrant_evaluates 子表；出入库走 warrant_storages 子表；
查封拍卖/inquiry/auction 全部删除（后续如需独立模块再建）。
"""

import sqlalchemy as sa
from alembic import op

revision = "e8b4f2a912c0"
down_revision = "c7a3e91f0d24"
branch_labels = None
depends_on = None

# 要删除的列清单（按 safe drop 顺序）
_DROP_COLUMNS = [
    "evaluate_method",
    "evaluate_value",
    "evaluate_date",
    "evaluate_explain",
    "evaluate_company",
    "meeting_date",
    "storage_explain",
    "inquiry_date",
    "inquiry_detail",
    "auction_date",
    "listing_price",
    "auction_remark",
    "transaction_date",
    "auction_amount",
]


def upgrade() -> None:
    # auction_state 有显式索引，先删索引再删列
    op.drop_index("ix_warrants_auction_state", table_name="warrants")
    op.drop_column("warrants", "auction_state")
    for col in _DROP_COLUMNS:
        op.drop_column("warrants", col)


def downgrade() -> None:
    op.add_column("warrants", sa.Column("evaluate_method", sa.SmallInteger(), nullable=True))
    op.add_column("warrants", sa.Column("evaluate_value", sa.Numeric(18, 2), nullable=True))
    op.add_column("warrants", sa.Column("evaluate_date", sa.Date(), nullable=True))
    op.add_column("warrants", sa.Column("evaluate_explain", sa.String(255), nullable=True))
    op.add_column("warrants", sa.Column("evaluate_company", sa.String(128), nullable=True))
    op.add_column("warrants", sa.Column("meeting_date", sa.Date(), nullable=True))
    op.add_column("warrants", sa.Column("storage_explain", sa.String(255), nullable=True))
    op.add_column("warrants", sa.Column("inquiry_date", sa.Date(), nullable=True))
    op.add_column("warrants", sa.Column("inquiry_detail", sa.String(255), nullable=True))
    op.add_column("warrants", sa.Column("auction_date", sa.Date(), nullable=True))
    op.add_column("warrants", sa.Column("listing_price", sa.Numeric(18, 2), nullable=True))
    op.add_column("warrants", sa.Column("auction_remark", sa.String(255), nullable=True))
    op.add_column("warrants", sa.Column("transaction_date", sa.Date(), nullable=True))
    op.add_column("warrants", sa.Column("auction_amount", sa.Numeric(18, 2), nullable=True))
    op.add_column(
        "warrants",
        sa.Column("auction_state", sa.SmallInteger(), nullable=False, server_default=sa.text("10")),
    )
    op.create_index("ix_warrants_auction_state", "warrants", ["auction_state"])
