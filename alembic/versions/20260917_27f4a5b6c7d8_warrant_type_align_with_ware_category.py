"""WarrantType 数值对齐 WareCategory（担保物类别统一编码）

Revision ID: 27f4a5b6c7d8
Revises: b1c2d3e4f5g6
Create Date: 2026-09-17 16:30:00.000000

----- 映射表（WarrantType 旧值 → 新值，对齐 WareCategory） -----
HOUSE:        1  → 11
GROUND:       5  → 14
CONSTRUCTION: 6  → 16
RECEIVABLE:   11 → 21
STOCK:        21 → 41
DRAFT:        31 → 31  (不变，两个枚举本来就相同)
VEHICLE:      41 → 51
CHATTEL:      51 → 61
OTHER:        55 → 91
HYPOTHEC:     99 → 99  (不变，WarrantType 独有，WareCategory 无对应)

核心注意：必须用单条 CASE WHEN UPDATE，不能多条按顺序执行——
因为 STOCK 旧值=21 是 RECEIVABLE 新值，顺序更新会把刚改过的行再次污染。

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27f4a5b6c7d8'
down_revision: Union[str, None] = 'b1c2d3e4f5g6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None]


# ----- WarrantType 旧值 → 新值 映射 -----
_WT_OLD_TO_NEW = {
    1: 11,    # HOUSE
    5: 14,    # GROUND
    6: 16,    # CONSTRUCTION
    11: 21,   # RECEIVABLE
    21: 41,   # STOCK
    41: 51,   # VEHICLE
    51: 61,   # CHATTEL
    55: 91,   # OTHER
    # 31(DRAFT) 和 99(HYPOTHEC) 保持不变
}


def _migrate_data(conn) -> None:
    """一条 CASE WHEN 搞定所有 warrants.warrant_type 数据迁移。

    不用多条 UPDATE 顺序执行：旧值 21(STOCK) 恰好是 RECEIVABLE 的新值，
    先改 STOCK→41 不影响，但如果顺序反了（先改 RECEIVABLE→21）就会污染 STOCK 行。
    CASE WHEN 基于原始行值匹配，天然避免此问题。
    """
    cases = " ".join(
        f"WHEN {old} THEN {new}" for old, new in _WT_OLD_TO_NEW.items()
    )
    old_values = ", ".join(str(v) for v in _WT_OLD_TO_NEW.keys())
    conn.execute(
        sa.text(
            f"UPDATE warrants "
            f"SET warrant_type = CASE warrant_type {cases} ELSE warrant_type END "
            f"WHERE warrant_type IN ({old_values})"
        )
    )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 先做数据迁移（改数值）
    _migrate_data(conn)

    # 2. 更新列注释（同步 WareCategory 编码）
    op.alter_column(
        'warrants', 'warrant_type',
        existing_type=sa.SmallInteger(),
        existing_comment='1房产5土地6在建11应收21股权31票据41车辆51动产55其他99他权',
        comment='11房产14土地16在建21应收31票据41股权51车辆61动产91其他99他权',
        existing_nullable=False,
    )


def downgrade() -> None:
    conn = op.get_bind()

    # 1. 反向数据迁移（新值 → 旧值）
    _WT_NEW_TO_OLD = {new: old for old, new in _WT_OLD_TO_NEW.items()}
    cases = " ".join(
        f"WHEN {new} THEN {old}" for new, old in _WT_NEW_TO_OLD.items()
    )
    new_values = ", ".join(str(v) for v in _WT_NEW_TO_OLD.keys())
    conn.execute(
        sa.text(
            f"UPDATE warrants "
            f"SET warrant_type = CASE warrant_type {cases} ELSE warrant_type END "
            f"WHERE warrant_type IN ({new_values})"
        )
    )

    # 2. 还原列注释
    op.alter_column(
        'warrants', 'warrant_type',
        existing_type=sa.SmallInteger(),
        existing_comment='11房产14土地16在建21应收31票据41股权51车辆61动产91其他99他权',
        comment='1房产5土地6在建11应收21股权31票据41车辆51动产55其他99他权',
        existing_nullable=False,
    )
