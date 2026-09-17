"""恢复 article_sures 三元组唯一约束，修复上次 drop 后的状态

Revision ID: b1c2d3e4f5g6
Revises: 2afcebd456e8
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, None] = '2afcebd456e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None]


def _dedup_sures(conn) -> None:
    """合并同一 (order_id, ware_category, method_category) 下的重复 ArticleSure 行。

    保留 id 最小的那条作为 keeper，把其余行的 M2M 关系迁过来，然后删除重复行。
    """
    # 1. 找出所有重复三元组
    dup_sql = sa.text("""
        SELECT order_id, ware_category, method_category,
               GROUP_CONCAT(id ORDER BY id) AS ids
        FROM article_sures
        GROUP BY order_id, ware_category, method_category
        HAVING COUNT(*) > 1
    """)
    rows = conn.execute(dup_sql).fetchall()

    for order_id, ware_cat, method_cat, ids_str in rows:
        ids = [int(x) for x in ids_str.split(',')]
        keeper_id = ids[0]       # 保留第一条
        dup_ids = ids[1:]          # 删除其余

        # 2. 把重复行的 M2M 迁到 keeper（customer）
        for dup_id in dup_ids:
            conn.execute(sa.text("""
                INSERT IGNORE INTO article_sure_customers (sure_id, customer_id)
                SELECT :keeper_id, customer_id
                FROM article_sure_customers WHERE sure_id = :dup_id
            """), {"keeper_id": keeper_id, "dup_id": dup_id})

            # 3. 把重复行的 M2M 迁到 keeper（warrant）
            conn.execute(sa.text("""
                INSERT IGNORE INTO article_sure_warrants (sure_id, warrant_id)
                SELECT :keeper_id, warrant_id
                FROM article_sure_warrants WHERE sure_id = :dup_id
            """), {"keeper_id": keeper_id, "dup_id": dup_id})

            # 4. 删除重复行（M2M 有 CASCADE，会自动清中间表）
            conn.execute(
                sa.text("DELETE FROM article_sures WHERE id = :sid"),
                {"sid": dup_id},
            )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. 去重（幂等：没有重复就什么都不做）
    _dedup_sures(conn)
    conn.commit()

    # 2. 恢复三元组唯一约束
    op.create_unique_constraint(
        'uq_sure_order_ware_method', 'article_sures',
        ['order_id', 'ware_category', 'method_category'],
    )

    # 3. 删掉 drop 那次为了绕过 MySQL FK 限制建的独立 order_id 索引
    #    恢复唯一约束后，复合索引的最左前缀会继续支撑 order_id 上的 FK
    op.drop_index('ix_article_sures_order_id', 'article_sures')


def downgrade() -> None:
    # 降级方向：先重建独立 order_id 索引，再删唯一约束
    op.create_index(
        'ix_article_sures_order_id', 'article_sures', ['order_id'], unique=False,
    )
    op.drop_constraint('uq_sure_order_ware_method', 'article_sures', type_='unique')
