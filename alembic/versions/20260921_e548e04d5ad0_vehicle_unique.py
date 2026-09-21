"""vehicle_unique

Revision ID: e548e04d5ad0
Revises: a1b2c3d4e5f7
Create Date: 2026-09-21 11:53:22.638508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e548e04d5ad0'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # remark 从 VARCHAR(255) → VARCHAR(128)（与 model 对齐）
    op.alter_column(
        'warrant_vehicles', 'remark',
        existing_type=sa.String(length=255),
        type_=sa.String(length=128),
        existing_nullable=True,
    )
    # frame_num + plate_num 加唯一约束
    op.create_unique_constraint('uq_warrant_vehicles_frame_num', 'warrant_vehicles', ['frame_num'])
    op.create_unique_constraint('uq_warrant_vehicles_plate_num', 'warrant_vehicles', ['plate_num'])


def downgrade() -> None:
    op.drop_constraint('uq_warrant_vehicles_plate_num', 'warrant_vehicles', type_='unique')
    op.drop_constraint('uq_warrant_vehicles_frame_num', 'warrant_vehicles', type_='unique')
    op.alter_column(
        'warrant_vehicles', 'remark',
        existing_type=sa.String(length=128),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
