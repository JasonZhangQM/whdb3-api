"""评审模块 FK ondelete 收敛 + AppraisalComment 字段重命名

模型同步（2026-09-22）：
1. AppraisalComment: comment_type→comment, concrete→detail
2. AppraisalComment.article_id FK: ondelete CASCADE → 默认 RESTRICT
3. AppraisalArticle.article_id FK: ondelete CASCADE → 默认 RESTRICT
（Appraisal.compere_id / AppraisalComment.expert_id 原就是 RESTRICT，
 模型去 ondelete 无实际变化，无需迁移）

FK 改动采用 warrant_ownership_fk_no_cascade 的 introspect 模式动态
查找约束名，兼容 MySQL/PostgreSQL。

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-09-22 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


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


def _recreate_fk(table: str, column: str, ref_table: str, ref_column: str, ondelete: str | None) -> None:
    fk_name = _find_fk_name(table, column, ref_table, ref_column)
    op.drop_constraint(fk_name, table, type_='foreignkey')
    op.create_foreign_key(
        fk_name, table, ref_table,
        [column], [ref_column],
        ondelete=ondelete,
    )


def upgrade() -> None:
    # ============ 1. AppraisalComment 字段重命名 ============
    op.alter_column(
        'appraisal_comments', 'comment_type',
        new_column_name='comment',
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
        existing_server_default=sa.text('0'),
    )
    op.alter_column(
        'appraisal_comments', 'concrete',
        new_column_name='detail',
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    # ============ 2. FK CASCADE → 默认 RESTRICT ============
    _recreate_fk('appraisal_comments', 'article_id', 'articles', 'id', ondelete=None)
    _recreate_fk('appraisal_articles', 'article_id', 'articles', 'id', ondelete=None)


def downgrade() -> None:
    # ============ 1. FK 恢复 CASCADE ============
    _recreate_fk('appraisal_articles', 'article_id', 'articles', 'id', ondelete='CASCADE')
    _recreate_fk('appraisal_comments', 'article_id', 'articles', 'id', ondelete='CASCADE')

    # ============ 2. AppraisalComment 字段回滚 ============
    op.alter_column(
        'appraisal_comments', 'comment',
        new_column_name='comment_type',
        existing_type=sa.SmallInteger(),
        existing_nullable=False,
        existing_server_default=sa.text('0'),
    )
    op.alter_column(
        'appraisal_comments', 'detail',
        new_column_name='concrete',
        existing_type=sa.Text(),
        existing_nullable=True,
    )
