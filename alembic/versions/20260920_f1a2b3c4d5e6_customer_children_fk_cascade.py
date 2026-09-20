"""客户自有子表 FK customers.id → CASCADE

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-20

把 5 张客户自有子表的 customer_id 外键从隐式 RESTRICT 改为 CASCADE，
这样 db.delete(customer) 才能级联清理，否则会撞 IntegrityError 5001。

涉及表：
- customer_company_profiles
- customer_personal_profiles
- customer_extends
- customer_core_limits
- customer_core_histories
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_fk_name(table: str, column: str, ref_table: str, ref_column: str) -> str:
    """通过 SQLAlchemy inspector 查出外键约束名（MySQL 自动命名为 xxx_ibfk_N）。"""
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


def _recreate_fk_cascade(table: str, column: str) -> None:
    """drop 旧 FK + 重建为 CASCADE。"""
    fk_name = _find_fk_name(table, column, 'customers', 'id')
    op.drop_constraint(fk_name, table, type_='foreignkey')
    op.create_foreign_key(
        fk_name,
        table,
        'customers',
        [column],
        ['id'],
        ondelete='CASCADE',
    )


def upgrade() -> None:
    for table, column in [
        ('customer_company_profiles', 'customer_id'),
        ('customer_personal_profiles', 'customer_id'),
        ('customer_extends', 'customer_id'),
        ('customer_core_limits', 'customer_id'),
        ('customer_core_histories', 'customer_id'),
    ]:
        _recreate_fk_cascade(table, column)


def downgrade() -> None:
    for table, column in [
        ('customer_core_histories', 'customer_id'),
        ('customer_core_limits', 'customer_id'),
        ('customer_extends', 'customer_id'),
        ('customer_personal_profiles', 'customer_id'),
        ('customer_company_profiles', 'customer_id'),
    ]:
        fk_name = _find_fk_name(table, column, 'customers', 'id')
        op.drop_constraint(fk_name, table, type_='foreignkey')
        # 恢复默认（隐式 RESTRICT）
        op.create_foreign_key(
            fk_name,
            table,
            'customers',
            [column],
            ['id'],
            ondelete=None,
        )
