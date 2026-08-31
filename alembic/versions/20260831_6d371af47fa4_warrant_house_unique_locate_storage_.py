"""P0 修复：房产坐落全局唯一约束 + StorageType 注销枚举注释同步。

Revision ID: 6d371af47fa4
Revises: b7f312e8a4d5
Create Date: 2026-08-31 09:28:46.929691

P0-1: warrant_houses.house_locate 加 UNIQUE（修复读-写竞态风险）
P0-3: warrant_storages.storage_type 注释同步加入 990=注销（枚举层已加）
      ground_app nullable 差异为既有模型-DB 不一致，已通过模型 nullable=True 匹配修复
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6d371af47fa4'
down_revision: Union[str, None] = 'b7f312e8a4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # P0-1: 房产坐落全局唯一约束
    op.create_unique_constraint('uq_house_locate', 'warrant_houses', ['house_locate'])
    # P0-3: 同步注释加入新枚举值
    op.alter_column(
        'warrant_storages', 'storage_type',
        comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交990注销',
        existing_type=sa.SmallInteger(),
        existing_comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交',
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'warrant_storages', 'storage_type',
        comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交',
        existing_type=sa.SmallInteger(),
        existing_comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交990注销',
        existing_nullable=False,
    )
    op.drop_constraint('uq_house_locate', 'warrant_houses', type_='unique')
