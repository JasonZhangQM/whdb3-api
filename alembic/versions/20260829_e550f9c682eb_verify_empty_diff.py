"""customers.created_by 收尾：NULL 化 + 索引改名对齐列名

Revision ID: e550f9c682eb
Revises: 08f492f00f99
Create Date: 2026-08-29 21:18:14.350945

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e550f9c682eb'
down_revision: Union[str, None] = '08f492f00f99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable + 去 comment（原 create_by 列遗留属性）
    op.execute("ALTER TABLE customers MODIFY created_by BIGINT NULL COMMENT ''")
    # 原 create_by 的 FK 自动索引名与列名不一致（RENAME COLUMN 不改索引名），
    # 改名对齐后 alembic 将其识别为 FK 隐含索引，不再报 diff
    op.execute("ALTER TABLE customers RENAME INDEX create_by TO created_by")


def downgrade() -> None:
    op.execute("ALTER TABLE customers RENAME INDEX created_by TO create_by")
    op.execute("ALTER TABLE customers MODIFY created_by BIGINT NOT NULL COMMENT '创建人'")
