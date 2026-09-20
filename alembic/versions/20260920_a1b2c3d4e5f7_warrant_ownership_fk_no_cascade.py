"""warrant_ownerships.warrant_id FK 去掉 CASCADE，改为 RESTRICT

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-20

 WarrantOwnership 是唯一带 ondelete=CASCADE 的"所有权"中间表，
语义上权证所有权应该受 RESTRICT 保护（删除权证前必须先清理所有权，
防止级联删除导致产权记录丢失）。其余 warrant 子表保持 CASCADE 不变。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
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
                raise RuntimeError(f"FK {table}.{column}->{ref_table}.{ref_column} 没有名字")
            return name
    raise RuntimeError(f"没找到 FK {table}.{column}->{ref_table}.{ref_column}")


def _recreate_fk(table: str, column: str, ondelete: str | None) -> None:
    fk_name = _find_fk_name(table, column, 'warrants', 'id')
    op.drop_constraint(fk_name, table, type_='foreignkey')
    op.create_foreign_key(
        fk_name,
        table,
        'warrants',
        [column],
        ['id'],
        ondelete=ondelete,
    )


def upgrade() -> None:
    # CASCADE → RESTRICT（隐式 None = RESTRICT）
    _recreate_fk('warrant_ownerships', 'warrant_id', ondelete=None)


def downgrade() -> None:
    # RESTRICT → CASCADE
    _recreate_fk('warrant_ownerships', 'warrant_id', ondelete='CASCADE')
