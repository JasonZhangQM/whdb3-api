"""迁移状态检查（一次性诊断脚本）。"""
from sqlalchemy import create_engine, text

from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
conn = engine.connect()

print("version:", conn.execute(text("SELECT version_num FROM alembic_version")).scalar())

print("user_user_roles columns:")
for row in conn.execute(text("SHOW COLUMNS FROM user_user_roles")).mappings():
    print(" ", row["Field"], row["Type"], row["Null"], "KEY:", row["Key"])

print("customers created cols:")
for row in conn.execute(text("SHOW COLUMNS FROM customers")).mappings():
    if row["Field"] in ("created_by", "create_by"):
        print(" ", row["Field"], row["Null"])

print("warrants created_by:")
for row in conn.execute(text("SHOW COLUMNS FROM warrants")).mappings():
    if row["Field"] == "created_by":
        print(" ", row["Field"], row["Null"])

print("user_user_roles rows:", conn.execute(text("SELECT COUNT(*) FROM user_user_roles")).scalar())
print("user_role_permissions rows:", conn.execute(text("SELECT COUNT(*) FROM user_role_permissions")).scalar())
print("customers created_by sample:", conn.execute(text("SELECT created_by FROM customers LIMIT 1")).scalar())
