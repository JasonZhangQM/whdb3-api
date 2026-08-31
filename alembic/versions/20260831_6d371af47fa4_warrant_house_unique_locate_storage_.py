"""权证模块 P0 约束修正：房产坐落不应唯一（换证场景同坐落多证），
产权证编号（ownership_num）才是全局唯一键。

Revision ID: 6d371af47fa4
Revises: b7f312e8a4d5
Create Date: 2026-08-31 09:28:46.929691

修正记录:
  初始版本: warrant_houses.house_locate 加 UNIQUE（P0-1）+ storage_type 注释加 990（P0-3）
  2026-08-31 修正: 拆 house_locate UNIQUE（换证后同坐落出现多套证）
                   加 warrant_ownerships.ownership_num UNIQUE（产权证编号应全局唯一）
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
    # 2026-08-31 修正：拆掉 P0-1 错加的 house_locate unique（换证场景同坐落多证）
    # 幂等：手动脚本可能已清掉；生产环境直接 apply 时有此约束
    try:
        op.drop_constraint('uq_house_locate', 'warrant_houses', type_='unique')
    except Exception:
        pass

    # P0-3 同步注释加入新枚举值（保持 DB 注释与模型一致）
    op.alter_column(
        'warrant_storages', 'storage_type',
        comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交990注销',
        existing_type=sa.SmallInteger(),
        existing_comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交',
        existing_nullable=False,
    )

    # 2026-08-31 修正：产权证编号应全局唯一（唯一正确的业务键）
    op.create_unique_constraint(
        'uq_ownership_num', 'warrant_ownerships', ['ownership_num']
    )


def downgrade() -> None:
    op.drop_constraint('uq_ownership_num', 'warrant_ownerships', type_='unique')

    op.alter_column(
        'warrant_storages', 'storage_type',
        comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交',
        existing_type=sa.SmallInteger(),
        existing_comment='10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交990注销',
        existing_nullable=False,
    )

    op.create_unique_constraint('uq_house_locate', 'warrant_houses', ['house_locate'])
