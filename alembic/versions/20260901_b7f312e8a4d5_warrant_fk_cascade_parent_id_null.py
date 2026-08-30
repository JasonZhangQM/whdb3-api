"""warrant FK cascade + parent_id null + ground_app comment fix

Revision ID: b7f312e8a4d5
Revises: c92090d6ea2c
Create Date: 2026-09-01

真实 FK 名称取自 information_schema.KEY_COLUMN_USAGE（MySQL 自动生成 ibfk 后缀）。
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f312e8a4d5'
down_revision: Union[str, None] = 'c92090d6ea2c'
branch_labels: Union[str, list[str], None] = None
depends_on: Union[str, list[str], None] = None


def upgrade() -> None:
    # ---- WarrantHouseApp.parent_id: 0 → NULL ----
    op.execute("UPDATE warrant_house_apps SET parent_id = NULL WHERE parent_id = 0")
    op.alter_column(
        'warrant_house_apps', 'parent_id',
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    # ---- WarrantGround.ground_app 注释修正 ----
    op.alter_column(
        'warrant_grounds', 'ground_app',
        existing_type=sa.String(length=128),
        comment='土地坐落/宗地号',
    )

    # ---- 所有权证子表 FK 加 ON DELETE CASCADE ----
    # drop 旧 FK + 重建（真实 FK 名从 information_schema.KEY_COLUMN_USAGE 查询）
    _recreate_fk('warrant_ownerships', 'warrant_id', 'warrants', 'id', 'warrant_ownerships_ibfk_3')
    _recreate_fk('warrant_houses', 'warrant_id', 'warrants', 'id', 'warrant_houses_ibfk_2')
    _recreate_fk('warrant_grounds', 'warrant_id', 'warrants', 'id', 'warrant_grounds_ibfk_2')
    _recreate_fk('warrant_constructions', 'warrant_id', 'warrants', 'id', 'warrant_constructions_ibfk_2')
    _recreate_fk('warrant_receivables', 'warrant_id', 'warrants', 'id', 'warrant_receivables_ibfk_2')
    _recreate_fk('warrant_stocks', 'warrant_id', 'warrants', 'id', 'warrant_stocks_ibfk_2')
    _recreate_fk('warrant_drafts', 'warrant_id', 'warrants', 'id', 'warrant_drafts_ibfk_2')
    _recreate_fk('warrant_vehicles', 'warrant_id', 'warrants', 'id', 'warrant_vehicles_ibfk_2')
    _recreate_fk('warrant_chattels', 'warrant_id', 'warrants', 'id', 'warrant_chattels_ibfk_2')
    _recreate_fk('warrant_others', 'warrant_id', 'warrants', 'id', 'warrant_others_ibfk_2')
    _recreate_fk('warrant_storages', 'warrant_id', 'warrants', 'id', 'warrant_storages_ibfk_3')
    _recreate_fk('warrant_evaluates', 'warrant_id', 'warrants', 'id', 'warrant_evaluates_ibfk_2')
    # 级联子表的子表
    _recreate_fk('warrant_receive_extends', 'receivable_id', 'warrant_receivables', 'id', 'warrant_receive_extends_ibfk_2')
    _recreate_fk('warrant_draft_extends', 'draft_id', 'warrant_drafts', 'id', 'warrant_draft_extends_ibfk_4')
    _recreate_fk('warrant_patents', 'other_id', 'warrant_others', 'id', 'warrant_patents_ibfk_2')
    _recreate_fk('warrant_softwares', 'other_id', 'warrant_others', 'id', 'warrant_softwares_ibfk_2')
    _recreate_fk('warrant_evaluate_rechecks', 'evaluate_id', 'warrant_evaluates', 'id', 'warrant_evaluate_rechecks_ibfk_2')


def downgrade() -> None:
    # 移除 CASCADE：drop + 重建不带 CASCADE
    _recreate_fk('warrant_evaluate_rechecks', 'evaluate_id', 'warrant_evaluates', 'id', 'warrant_evaluate_rechecks_ibfk_2', ondelete=None)
    _recreate_fk('warrant_softwares', 'other_id', 'warrant_others', 'id', 'warrant_softwares_ibfk_2', ondelete=None)
    _recreate_fk('warrant_patents', 'other_id', 'warrant_others', 'id', 'warrant_patents_ibfk_2', ondelete=None)
    _recreate_fk('warrant_draft_extends', 'draft_id', 'warrant_drafts', 'id', 'warrant_draft_extends_ibfk_4', ondelete=None)
    _recreate_fk('warrant_receive_extends', 'receivable_id', 'warrant_receivables', 'id', 'warrant_receive_extends_ibfk_2', ondelete=None)
    _recreate_fk('warrant_evaluates', 'warrant_id', 'warrants', 'id', 'warrant_evaluates_ibfk_2', ondelete=None)
    _recreate_fk('warrant_storages', 'warrant_id', 'warrants', 'id', 'warrant_storages_ibfk_3', ondelete=None)
    _recreate_fk('warrant_others', 'warrant_id', 'warrants', 'id', 'warrant_others_ibfk_2', ondelete=None)
    _recreate_fk('warrant_chattels', 'warrant_id', 'warrants', 'id', 'warrant_chattels_ibfk_2', ondelete=None)
    _recreate_fk('warrant_vehicles', 'warrant_id', 'warrants', 'id', 'warrant_vehicles_ibfk_2', ondelete=None)
    _recreate_fk('warrant_drafts', 'warrant_id', 'warrants', 'id', 'warrant_drafts_ibfk_2', ondelete=None)
    _recreate_fk('warrant_stocks', 'warrant_id', 'warrants', 'id', 'warrant_stocks_ibfk_2', ondelete=None)
    _recreate_fk('warrant_receivables', 'warrant_id', 'warrants', 'id', 'warrant_receivables_ibfk_2', ondelete=None)
    _recreate_fk('warrant_constructions', 'warrant_id', 'warrants', 'id', 'warrant_constructions_ibfk_2', ondelete=None)
    _recreate_fk('warrant_grounds', 'warrant_id', 'warrants', 'id', 'warrant_grounds_ibfk_2', ondelete=None)
    _recreate_fk('warrant_houses', 'warrant_id', 'warrants', 'id', 'warrant_houses_ibfk_2', ondelete=None)
    _recreate_fk('warrant_ownerships', 'warrant_id', 'warrants', 'id', 'warrant_ownerships_ibfk_3', ondelete=None)

    # parent_id: NULL 回填 0
    op.alter_column(
        'warrant_house_apps', 'parent_id',
        existing_type=sa.BigInteger(),
        nullable=False,
        server_default=sa.text('0'),
    )
    op.execute("UPDATE warrant_house_apps SET parent_id = 0 WHERE parent_id IS NULL")

    # ground_app 注释回退
    op.alter_column(
        'warrant_grounds', 'ground_app',
        existing_type=sa.String(length=128),
        comment='土地用途',
    )


def _recreate_fk(
    table: str,
    column: str,
    ref_table: str,
    ref_column: str,
    fk_name: str,
    ondelete: str | None = 'CASCADE',
) -> None:
    """drop 旧 FK + 重建（可选 ondelete）。"""
    op.drop_constraint(fk_name, table, type_='foreignkey')
    op.create_foreign_key(
        fk_name,
        table,
        ref_table,
        [column],
        [ref_column],
        ondelete=ondelete,
    )
