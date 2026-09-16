"""sure_type -> ware_category + method_category（含数据迁移）

Revision ID: 2afcebd456e8
Revises: 20260915_b2c3d4e5f6a7
Create Date: 2026-09-16 11:52:17.306783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2afcebd456e8'
down_revision: Union[str, None] = '20260915_b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None]


# ----- sure_type → (ware_category, method_category) 映射 -----
# 旧 SureType 原值 → 新 WareCategory / MethodCategory（2026-09-16 重排数值）
# WareCategory: GUARANTOR=1 HOUSE=11 GROUND=14 CONSTRUCTION=16 RECEIVABLE=21
#               DRAFT=31 STOCK=41 VEHICLE=51 CHATTEL=61 OTHER=91
# MethodCategory: COMPANY=1 PERSONAL=2 MORTGAGE=11 SUCCESSION=15
#                 PLEDGE=21 SUPERVISE=31 PRESALE=61 OTHER=91
_SURE_TO_WARE = {
    # 保证类
    1: 1, 2: 1,
    # 房产 HOUSE=11
    11: 11, 21: 11, 42: 11, 52: 11,
    # 土地 GROUND=14
    12: 14, 22: 14, 43: 14, 53: 14,
    # 在建工程 CONSTRUCTION=16
    14: 16, 23: 16,
    # 应收账款 RECEIVABLE=21
    31: 21,
    # 票据 DRAFT=31
    33: 31, 44: 31,
    # 股权 STOCK=41
    32: 41, 51: 41,
    # 车辆 VEHICLE=51
    15: 51,
    # 动产 CHATTEL=61
    13: 61, 24: 61, 34: 61, 47: 61,
    # 其他 OTHER=91
    39: 91, 49: 91, 59: 91, 61: 91,
}
_SURE_TO_METHOD = {
    # 企业保证 → COMPANY=1；个人保证 → PERSONAL=2
    1: 1, 2: 2,
    # 抵押 MORTGAGE=11
    11: 11, 12: 11, 13: 11, 14: 11, 15: 11,
    # 顺位抵押 SUCCESSION=15
    21: 15, 22: 15, 23: 15, 24: 15,
    # 质押 PLEDGE=21
    31: 21, 32: 21, 33: 21, 34: 21, 39: 21,
    # 监管 SUPERVISE=31
    42: 31, 43: 31, 44: 31, 47: 31, 49: 31,
    # 预售 PRESALE=61
    51: 61, 52: 61, 53: 61,
    # 其他 OTHER=91
    59: 91, 61: 91,
}


def _migrate_data(conn) -> None:
    """把 article_sures.sure_type 映射到 ware_category + method_category。"""
    for sure_t, ware in _SURE_TO_WARE.items():
        method = _SURE_TO_METHOD[sure_t]
        conn.execute(
            sa.text(
                "UPDATE article_sures "
                "SET ware_category = :ware, method_category = :method "
                "WHERE sure_type = :sure"
            ),
            {"ware": ware, "method": method, "sure": sure_t},
        )
    # 兜底处理没在映射表里的 sure_type（NULL / 未知值）
    conn.execute(
        sa.text(
            "UPDATE article_sures SET ware_category = 91, method_category = 91 "
            "WHERE ware_category IS NULL OR method_category IS NULL"
        )
    )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 加两列（临时允许 NULL）
    op.add_column(
        'article_sures',
        sa.Column('ware_category', sa.SmallInteger(), nullable=True,
                  comment='担保物类别（WareCategory）'),
    )
    op.add_column(
        'article_sures',
        sa.Column('method_category', sa.SmallInteger(), nullable=True,
                  comment='担保方式类别（MethodCategory）'),
    )

    # 2. 数据迁移：sure_type → (ware_category, method_category)
    _migrate_data(conn)

    # 3. 用 raw SQL 把两列改成 NOT NULL + 加新唯一约束 + 删旧约束 + 删旧列
    conn.execute(sa.text(
        "ALTER TABLE article_sures "
        "MODIFY ware_category SMALLINT NOT NULL COMMENT '担保物类别（WareCategory）', "
        "MODIFY method_category SMALLINT NOT NULL COMMENT '担保方式类别（MethodCategory）', "
        "DROP INDEX uq_sure_order_type, "
        "ADD UNIQUE KEY uq_sure_order_ware_method (order_id, ware_category, method_category), "
        "DROP COLUMN sure_type"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # 1. 先加回 sure_type 列
    op.add_column(
        'article_sures',
        sa.Column('sure_type', sa.SmallInteger(), nullable=True,
                  comment='反担保类型'),
    )

    # 2. 反向数据迁移：(ware_category, method_category) → sure_type
    #    按新枚举值反向合成（2026-09-16 重排后）
    ware_method_to_st = {
        (1, 1): 1,    # 企业保证
        (1, 2): 2,    # 个人保证
        # 房产 HOUSE=11
        (11, 11): 11, (11, 15): 21, (11, 31): 42, (11, 61): 52,
        # 土地 GROUND=14
        (14, 11): 12, (14, 15): 22, (14, 31): 43, (14, 61): 53,
        # 在建工程 CONSTRUCTION=16
        (16, 11): 14, (16, 15): 23,
        # 应收账款 RECEIVABLE=21
        (21, 21): 31,
        # 票据 DRAFT=31
        (31, 21): 33, (31, 31): 44,
        # 股权 STOCK=41
        (41, 21): 32, (41, 61): 51,
        # 车辆 VEHICLE=51
        (51, 11): 15,
        # 动产 CHATTEL=61
        (61, 11): 13, (61, 15): 24, (61, 21): 34, (61, 31): 47,
        # 其他 OTHER=91
        (91, 21): 39, (91, 31): 49, (91, 91): 59,
    }
    for (w, m), st in ware_method_to_st.items():
        conn.execute(
            sa.text(
                "UPDATE article_sures SET sure_type = :st "
                "WHERE ware_category = :w AND method_category = :m"
            ),
            {"st": st, "w": w, "m": m},
        )
    # 兜底
    conn.execute(
        sa.text("UPDATE article_sures SET sure_type = 59 WHERE sure_type IS NULL")
    )

    # 3. sure_type 改成 NOT NULL
    op.alter_column('article_sures', 'sure_type', nullable=False)

    # 4. 换回旧唯一约束，删新列
    op.drop_constraint('uq_sure_order_ware_method', 'article_sures', type_='unique')
    op.create_unique_constraint(
        'uq_sure_order_type', 'article_sures', ['order_id', 'sure_type'],
    )
    op.drop_column('article_sures', 'ware_category')
    op.drop_column('article_sures', 'method_category')
