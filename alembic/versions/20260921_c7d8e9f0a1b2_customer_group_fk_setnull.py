"""customers.group_id FK → SET NULL（删集团自动清空客户 group_id）

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_fk_name(table: str, column: str, ref_table: str, ref_column: str) -> str:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if (
            fk.get('constrained_columns') == [column]
            and fk.get('referred_table') == ref_table
            and fk.get('referred_columns') == [ref_column]
        ):
            name = fk.get('name')
            if not name:
                raise RuntimeError(f"FK {table}.{column}->{ref_table}.{ref_column} 无名字")
            return name
    raise RuntimeError(f"未找到 FK {table}.{column}->{ref_table}.{ref_column}")


def upgrade() -> None:
    fk_name = _find_fk_name('customers', 'group_id', 'customer_groups', 'id')
    op.drop_constraint(fk_name, 'customers', type_='foreignkey')
    op.create_foreign_key(
        fk_name,
        'customers', 'customer_groups',
        ['group_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    fk_name = _find_fk_name('customers', 'group_id', 'customer_groups', 'id')
    op.drop_constraint(fk_name, 'customers', type_='foreignkey')
    # 恢复默认 RESTRICT
    op.create_foreign_key(
        fk_name,
        'customers', 'customer_groups',
        ['group_id'], ['id'],
    )
