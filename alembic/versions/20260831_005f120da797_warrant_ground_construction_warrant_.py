"""warrant_ground_construction_warrant_drop_unique

Revision ID: 005f120da797
Revises: 449c7112a19e
Create Date: 2026-08-31 18:58:23.720409

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '005f120da797'
down_revision: Union[str, None] = '449c7112a19e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None]


def upgrade() -> None:
    # DROP FK first (MySQL FK depends on the unique index), then DROP unique index.
    # Grounds
    op.drop_constraint('warrant_grounds_ibfk_2', 'warrant_grounds', type_='foreignkey')
    op.drop_index('warrant_id', table_name='warrant_grounds')
    op.create_foreign_key(
        'warrant_grounds_ibfk_2', 'warrant_grounds', 'warrants',
        ['warrant_id'], ['id'], ondelete='CASCADE',
    )
    # Constructions
    op.drop_constraint('warrant_constructions_ibfk_2', 'warrant_constructions', type_='foreignkey')
    op.drop_index('warrant_id', table_name='warrant_constructions')
    op.create_foreign_key(
        'warrant_constructions_ibfk_2', 'warrant_constructions', 'warrants',
        ['warrant_id'], ['id'], ondelete='CASCADE',
    )
    # Column comment tweak
    op.alter_column(
        'warrant_grounds', 'ground_app',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=128),
        comment='土地用途',
        existing_comment='土地坐落/宗地号',
        existing_nullable=True,
    )


def downgrade() -> None:
    # Constructions
    op.drop_constraint('warrant_constructions_ibfk_2', 'warrant_constructions', type_='foreignkey')
    op.create_index('warrant_id', 'warrant_constructions', ['warrant_id'], unique=True)
    op.create_foreign_key(
        'warrant_constructions_ibfk_2', 'warrant_constructions', 'warrants',
        ['warrant_id'], ['id'], ondelete='CASCADE',
    )
    # Grounds
    op.drop_constraint('warrant_grounds_ibfk_2', 'warrant_grounds', type_='foreignkey')
    op.create_index('warrant_id', 'warrant_grounds', ['warrant_id'], unique=True)
    op.create_foreign_key(
        'warrant_grounds_ibfk_2', 'warrant_grounds', 'warrants',
        ['warrant_id'], ['id'], ondelete='CASCADE',
    )
    op.alter_column(
        'warrant_grounds', 'ground_app',
        existing_type=mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=128),
        comment='土地坐落/宗地号',
        existing_comment='土地用途',
        existing_nullable=True,
    )
