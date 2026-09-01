"""客户模块合并迁移：CustomerContact 一对多 + license_num/license_addr 统一到 Customer 主表

包含（全部幂等，可重复执行）：
1. 创建 customer_contacts 表（无 job 字段）
2. customers 删旧列 linkman/contact_num/contact_addr/core_rate/core_remark
3. customer_company_profiles 删 credit_code/registered_addr
4. customer_personal_profiles 删 license_num/license_addr
（数据已由旧迁移迁移到 customers.license_num/license_addr，此处仅做结构对齐）
"""
from alembic import op
import sqlalchemy as sa

revision: str = '0a0c1e2e4d5f'
down_revision: str = '314d12a01aeb'
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    """检查列是否存在（幂等删除的前提）。"""
    cur = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}' AND COLUMN_NAME = '{column}'"
    ))
    return cur.fetchone()[0] > 0


def _drop_column_if_exists(table: str, column: str) -> None:
    if _column_exists(op.get_bind(), table, column):
        op.drop_column(table, column)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. customer_contacts 表（已存在则跳过）
    conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS customer_contacts ("
        "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
        "customer_id BIGINT NOT NULL, "
        "created_by BIGINT NOT NULL, "
        "name VARCHAR(32) NOT NULL, "
        "phone VARCHAR(16) NOT NULL, "
        "email VARCHAR(128) NULL, "
        "addr VARCHAR(255) NULL, "
        "is_primary TINYINT(1) NOT NULL DEFAULT 0, "
        "remark VARCHAR(255) NULL, "
        "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, "
        "INDEX ix_customer_contacts_customer_id (customer_id), "
        "CONSTRAINT customer_contacts_ibfk_1 FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    ))

    # 2. customers 旧联系人列 → 若数据存在先搬再删（列已删则跳过）
    if _column_exists(conn, 'customers', 'linkman'):
        conn.execute(sa.text(
            "INSERT INTO customer_contacts (customer_id, name, phone, addr, is_primary, created_by, created_at, updated_at) "
            "SELECT id, COALESCE(linkman, ''), COALESCE(contact_num, ''), contact_addr, 1, "
            "COALESCE(created_by, 1), NOW(), NOW() "
            "FROM customers WHERE COALESCE(linkman, '') != '' OR COALESCE(contact_num, '') != ''"
        ))
    for col in ('linkman', 'contact_num', 'contact_addr', 'core_rate', 'core_remark'):
        _drop_column_if_exists('customers', col)

    # 3. 证照字段统一：先回填数据到主表（子表列存在时），再删子表列
    #    主表 license_num/license_addr 由旧迁移已建好；此处仅兜底补列
    if not _column_exists(conn, 'customers', 'license_num'):
        op.add_column('customers', sa.Column('license_num', sa.String(32), nullable=True, comment='信用代码/身份证号'))
    if not _column_exists(conn, 'customers', 'license_addr'):
        op.add_column('customers', sa.Column('license_addr', sa.String(255), nullable=True, comment='注册地址/身份证地址'))
    # 建唯一索引（任意名称的同列唯一索引已存在则跳过）
    cur = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customers' "
        "AND COLUMN_NAME = 'license_num' AND NON_UNIQUE = 0"
    ))
    if cur.fetchone()[0] == 0:
        conn.execute(sa.text("ALTER TABLE customers ADD CONSTRAINT uq_customers_license_num UNIQUE (license_num)"))

    # 企业：credit_code/registered_addr → 主表（主表为空才回填）
    if _column_exists(conn, 'customer_company_profiles', 'credit_code'):
        conn.execute(sa.text(
            "UPDATE customers c JOIN customer_company_profiles cp ON cp.customer_id = c.id "
            "SET c.license_num = cp.credit_code, c.license_addr = cp.registered_addr "
            "WHERE (c.license_num IS NULL OR c.license_num = '') AND COALESCE(cp.credit_code, '') != ''"
        ))
        _drop_column_if_exists('customer_company_profiles', 'credit_code')
        _drop_column_if_exists('customer_company_profiles', 'registered_addr')
    # 个人：license_num/license_addr → 主表
    if _column_exists(conn, 'customer_personal_profiles', 'license_num'):
        conn.execute(sa.text(
            "UPDATE customers c JOIN customer_personal_profiles pp ON pp.customer_id = c.id "
            "SET c.license_num = pp.license_num, c.license_addr = pp.license_addr "
            "WHERE (c.license_num IS NULL OR c.license_num = '') AND COALESCE(pp.license_num, '') != ''"
        ))
        _drop_column_if_exists('customer_personal_profiles', 'license_num')
        _drop_column_if_exists('customer_personal_profiles', 'license_addr')


def downgrade() -> None:
    """回滚：字段归位到子表，恢复旧联系人列。"""
    conn = op.get_bind()

    # 企业子表恢复
    if not _column_exists(conn, 'customer_company_profiles', 'credit_code'):
        op.add_column('customer_company_profiles', sa.Column('credit_code', sa.String(32), nullable=True))
        op.add_column('customer_company_profiles', sa.Column('registered_addr', sa.String(255), nullable=True))
        conn.execute(sa.text(
            "UPDATE customer_company_profiles cp JOIN customers c ON c.id = cp.customer_id "
            "SET cp.credit_code = c.license_num, cp.registered_addr = c.license_addr WHERE c.genre = 1"
        ))
    # 个人子表恢复
    if not _column_exists(conn, 'customer_personal_profiles', 'license_num'):
        op.add_column('customer_personal_profiles', sa.Column('license_num', sa.String(18), nullable=True))
        op.add_column('customer_personal_profiles', sa.Column('license_addr', sa.String(255), nullable=True))
        conn.execute(sa.text(
            "UPDATE customer_personal_profiles pp JOIN customers c ON c.id = pp.customer_id "
            "SET pp.license_num = c.license_num, pp.license_addr = c.license_addr WHERE c.genre = 2"
        ))
    # 主表删 license 列
    _drop_column_if_exists('customers', 'license_num')
    _drop_column_if_exists('customers', 'license_addr')

    # 恢复 customers 旧联系人列（取首选联系人）
    if not _column_exists(conn, 'customers', 'linkman'):
        op.add_column('customers', sa.Column('linkman', sa.String(64), nullable=True))
        op.add_column('customers', sa.Column('contact_num', sa.String(64), nullable=True))
        op.add_column('customers', sa.Column('contact_addr', sa.String(255), nullable=True))
        conn.execute(sa.text(
            "UPDATE customers c JOIN customer_contacts cc ON cc.customer_id = c.id AND cc.is_primary = 1 "
            "SET c.linkman = cc.name, c.contact_num = cc.phone, c.contact_addr = cc.addr"
        ))
        op.add_column('customers', sa.Column('core_rate', sa.Numeric(6, 2), nullable=True, comment='核心企业费率%'))
        op.add_column('customers', sa.Column('core_remark', sa.String(255), nullable=True, comment='核心企业备注'))
    # 删联系人表
    conn.execute(sa.text("DROP TABLE IF EXISTS customer_contacts"))
