"""warrant_ext_region_required

Revision ID: 82398b20829c
Revises: 314d12a01aeb
Create Date: 2026-09-01 07:42:45.212152

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '82398b20829c'
down_revision: Union[str, None] = '314d12a01aeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 存量数据：region_id 为 NULL 的填充默认区域 97665
    op.execute("UPDATE warrant_houses SET region_id = 97665 WHERE region_id IS NULL")
    op.execute("UPDATE warrant_grounds SET region_id = 97665 WHERE region_id IS NULL")
    op.execute("UPDATE warrant_constructions SET region_id = 97665 WHERE region_id IS NULL")

    # MySQL 要求 SET NULL FK 必须引用可空列，必须先 DROP FK 再改 NOT NULL，最后重建 FK
    # 1) DROP 旧 SET NULL FK
    op.drop_constraint(op.f('warrant_houses_ibfk_3'), 'warrant_houses', type_='foreignkey')
    op.drop_constraint(op.f('warrant_grounds_ibfk_3'), 'warrant_grounds', type_='foreignkey')
    op.drop_constraint(op.f('warrant_constructions_ibfk_3'), 'warrant_constructions', type_='foreignkey')

    # 2) ALTER 列改 NOT NULL
    op.alter_column('warrant_houses', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=False,
               comment='行政区域（必填，方便按区域统计）',
               existing_comment='行政区域（方便按区域统计）')
    op.alter_column('warrant_grounds', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=False,
               comment='行政区域（必填，方便按区域统计）',
               existing_comment='行政区域（方便按区域统计）')
    op.alter_column('warrant_constructions', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=False,
               comment='行政区域（必填，方便按区域统计）',
               existing_comment='行政区域（方便按区域统计）')

    # 3) 重建 RESTRICT FK
    op.create_foreign_key(None, 'warrant_houses', 'user_regions', ['region_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(None, 'warrant_grounds', 'user_regions', ['region_id'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(None, 'warrant_constructions', 'user_regions', ['region_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    # 回退：DROP RESTRICT FK → ALTER 列 NULL → 重建 SET NULL FK
    op.drop_constraint(None, 'warrant_houses', type_='foreignkey')
    op.drop_constraint(None, 'warrant_grounds', type_='foreignkey')
    op.drop_constraint(None, 'warrant_constructions', type_='foreignkey')

    op.alter_column('warrant_houses', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=True,
               comment='行政区域（方便按区域统计）',
               existing_comment='行政区域（必填，方便按区域统计）')
    op.alter_column('warrant_grounds', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=True,
               comment='行政区域（方便按区域统计）',
               existing_comment='行政区域（必填，方便按区域统计）')
    op.alter_column('warrant_constructions', 'region_id',
               existing_type=mysql.BIGINT(),
               nullable=True,
               comment='行政区域（方便按区域统计）',
               existing_comment='行政区域（必填，方便按区域统计）')

    op.create_foreign_key(op.f('warrant_houses_ibfk_3'), 'warrant_houses', 'user_regions', ['region_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('warrant_grounds_ibfk_3'), 'warrant_grounds', 'user_regions', ['region_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('warrant_constructions_ibfk_3'), 'warrant_constructions', 'user_regions', ['region_id'], ['id'], ondelete='SET NULL')
