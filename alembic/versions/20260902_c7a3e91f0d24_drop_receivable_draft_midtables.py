"""remove warrant_receivables / warrant_drafts, extends link warrants directly

Revision ID: c7a3e91f0d24
Revises: f94b64599896
Create Date: 2026-09-02

删除应收/票据中间表，两张 extend 明细表外键直连 warrants.id。
存量明细行数为 0，无需数据搬移。
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7a3e91f0d24"
down_revision = "f94b64599896"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- warrant_receive_extends: receivable_id -> warrant_id ---
    op.drop_constraint(
        "warrant_receive_extends_ibfk_2", "warrant_receive_extends", type_="foreignkey"
    )
    op.drop_index("uq_receive_extend_unit", table_name="warrant_receive_extends")
    op.drop_column("warrant_receive_extends", "receivable_id")
    op.add_column(
        "warrant_receive_extends",
        sa.Column("warrant_id", sa.BigInteger(), nullable=False),
    )
    op.create_foreign_key(
        "warrant_receive_extends_ibfk_6",
        "warrant_receive_extends",
        "warrants",
        ["warrant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_receive_extend_unit", "warrant_receive_extends", ["warrant_id", "receive_unit"]
    )

    # --- warrant_draft_extends: draft_id -> warrant_id ---
    op.drop_constraint(
        "warrant_draft_extends_ibfk_4", "warrant_draft_extends", type_="foreignkey"
    )
    op.drop_column("warrant_draft_extends", "draft_id")
    op.add_column(
        "warrant_draft_extends",
        sa.Column("warrant_id", sa.BigInteger(), nullable=False),
    )
    op.create_foreign_key(
        "warrant_draft_extends_ibfk_6",
        "warrant_draft_extends",
        "warrants",
        ["warrant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- 删除两张中间表 ---
    op.drop_table("warrant_receivables")
    op.drop_table("warrant_drafts")


def downgrade() -> None:
    # 逆向仅重建表结构（明细行不回迁）
    op.create_table(
        "warrant_receivables",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("warrant_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("receivable_detail", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["warrant_id"], ["warrants.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "warrant_drafts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("warrant_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("draft_detail", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["warrant_id"], ["warrants.id"], ondelete="CASCADE"),
    )
