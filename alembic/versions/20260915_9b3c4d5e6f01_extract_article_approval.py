"""extract_article_approval_one_to_one

Revision ID: 9b3c4d5e6f01
Revises: 0f093581a13d
Create Date: 2026-09-15 10:00:00.000000

将 Article 主表的评审/签批 9 个字段抽到一对一表 article_approvals。
顺序：建新表 → 数据迁移 → DROP 旧列（先 DROP unique 约束）。

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9b3c4d5e6f01'
down_revision: Union[str, None] = '0f093581a13d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 1. 建新表 article_approvals（一对一：article_id CASCADE + unique）===
    op.create_table(
        'article_approvals',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('review_date', sa.Date(), nullable=True, comment='上会日期'),
        sa.Column('summary_num', sa.String(length=32), nullable=True, comment='纪要编号'),
        sa.Column('summary', sa.Text(), nullable=True, comment='纪要'),
        sa.Column('opinion', sa.Text(), nullable=True, comment='项目意见'),
        sa.Column('rcd_opinion', sa.Text(), nullable=True, comment='风控部意见'),
        sa.Column('convenor_opinion', sa.Text(), nullable=True, comment='招集人意见'),
        sa.Column('sign_detail', sa.Text(), nullable=True, comment='签批人意见'),
        sa.Column('sign_type', sa.SmallInteger(), nullable=True, comment='签批结论 1同意 2不同意'),
        sa.Column('sign_date', sa.Date(), nullable=True, comment='签批日期'),
        sa.Column('article_id', sa.BigInteger(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['article_id'], ['articles.id'],
            name=op.f('article_approvals_ibfk_1'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('article_approvals_ibfk_2'), ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('article_approvals_pkey')),
        sa.UniqueConstraint('article_id', name=op.f('article_approvals_article_id_key')),
        sa.UniqueConstraint('summary_num', name=op.f('article_approvals_summary_num_key')),
    )

    # === 2. 数据迁移：从 articles 表复制非空记录 ===
    op.execute(
        """
        INSERT INTO article_approvals
            (article_id, review_date, summary_num, summary, opinion,
             rcd_opinion, convenor_opinion, sign_detail, sign_type, sign_date,
             created_at, updated_at)
        SELECT
            id, review_date, summary_num, summary, opinion,
            rcd_opinion, convenor_opinion, sign_detail, sign_type, sign_date,
            created_at, updated_at
        FROM articles
        WHERE review_date IS NOT NULL
           OR summary_num IS NOT NULL
           OR summary IS NOT NULL
           OR opinion IS NOT NULL
           OR rcd_opinion IS NOT NULL
           OR convenor_opinion IS NOT NULL
           OR sign_detail IS NOT NULL
           OR sign_type IS NOT NULL
           OR sign_date IS NOT NULL
        """
    )

    # === 3. DROP 旧列 ===
    # summary_num 在旧表有唯一约束，先 DROP 约束（MySQL 自动命名 unique 约束为列名）
    op.execute('ALTER TABLE articles DROP INDEX summary_num')
    op.drop_column('articles', 'summary_num')
    op.drop_column('articles', 'review_date')
    op.drop_column('articles', 'summary')
    op.drop_column('articles', 'opinion')
    op.drop_column('articles', 'rcd_opinion')
    op.drop_column('articles', 'convenor_opinion')
    op.drop_column('articles', 'sign_detail')
    op.drop_column('articles', 'sign_type')
    op.drop_column('articles', 'sign_date')


def downgrade() -> None:
    # === 反向：先加回旧列 ===
    op.add_column('articles', sa.Column('sign_date', sa.DATE(), nullable=True, comment='签批日期'))
    op.add_column('articles', sa.Column('sign_type', sa.SMALLINT(), nullable=True, comment='签批结论 1同意 2不同意'))
    op.add_column('articles', sa.Column('sign_detail', sa.TEXT(), nullable=True, comment='签批人意见'))
    op.add_column('articles', sa.Column('convenor_opinion', sa.TEXT(), nullable=True, comment='招集人意见'))
    op.add_column('articles', sa.Column('rcd_opinion', sa.TEXT(), nullable=True, comment='风控部意见'))
    op.add_column('articles', sa.Column('opinion', sa.TEXT(), nullable=True, comment='项目意见'))
    op.add_column('articles', sa.Column('summary', sa.TEXT(), nullable=True, comment='纪要'))
    op.add_column('articles', sa.Column('review_date', sa.DATE(), nullable=True, comment='上会日期(评审模块写入)'))
    op.add_column('articles', sa.Column('summary_num', sa.VARCHAR(length=32), nullable=True, comment='纪要编号(评审模块生成)'))
    op.create_unique_constraint(
        op.f('articles_summary_num_key'), 'articles', ['summary_num'],
    )

    # === 反向数据迁移 ===
    op.execute(
        """
        UPDATE articles a
        JOIN article_approvals ap ON ap.article_id = a.id
        SET a.review_date = ap.review_date,
            a.summary_num = ap.summary_num,
            a.summary = ap.summary,
            a.opinion = ap.opinion,
            a.rcd_opinion = ap.rcd_opinion,
            a.convenor_opinion = ap.convenor_opinion,
            a.sign_detail = ap.sign_detail,
            a.sign_type = ap.sign_type,
            a.sign_date = ap.sign_date
        """
    )

    # === 删新表 ===
    op.drop_table('article_approvals')
