"""warrant_ownerships.warrant_id FK 恢复 CASCADE

Revision ID: b8c9d0e1f2a3
Revises: 20260922_rename_experts_table
Create Date: 2026-09-23

 撤销 a1b2c3d4e5f7：warrant_ownerships.warrant_id 由 RESTRICT 改回
 ondelete=CASCADE，与其余 warrant 子表（house/ground/...）保持一致——
 warrant_service.delete 依赖 DB 级联清理全部子表，RESTRICT 会导致
 删除带所有权记录的权证时抛 FK 异常。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = '20260922_rename_experts_table'
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
    # RESTRICT → CASCADE
    _recreate_fk('warrant_ownerships', 'warrant_id', ondelete='CASCADE')


def downgrade() -> None:
    # CASCADE → RESTRICT（隐式 None = RESTRICT）
    _recreate_fk('warrant_ownerships', 'warrant_id', ondelete=None)
