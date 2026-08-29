"""排查：MySQL 中各库的 customer_extra_tags 表行数 + 活跃连接分布。"""
import pymysql

conn = pymysql.connect(host='127.0.0.1', port=3306, user='root', password='32243466')
cur = conn.cursor()

print("=== 活跃连接（按库分组）===")
cur.execute("SELECT db, COUNT(*) FROM information_schema.processlist WHERE db IS NOT NULL GROUP BY db")
for row in cur.fetchall():
    print(f"库 {row[0]}: {row[1]} 个连接")

print("\n=== customer_extra_tags 表分布 ===")
cur.execute(
    "SELECT table_schema, table_rows FROM information_schema.tables "
    "WHERE table_name = 'customer_extra_tags'"
)
for row in cur.fetchall():
    print(f"库 {row[0]}: 约 {row[1]} 行")

conn.close()
