"""一次性清理：删除早期迭代遗留表（当前模型中不存在的表）。

判定标准：SHOW TABLES 结果 - Base.metadata 表集合 - alembic_version。
"""
from sqlalchemy import text

# 与 alembic/env.py 相同的模型发现入口
import app.user.models  # noqa: F401
import app.approval.models  # noqa: F401
import app.attachment.models  # noqa: F401
import app.institution.models  # noqa: F401
import app.customer.models  # noqa: F401
import app.warrant.models  # noqa: F401

from app.core.db import Base, SessionLocal

db = SessionLocal()
model_tables = set(Base.metadata.tables.keys())
db_tables = {r[0] for r in db.execute(text("SHOW TABLES")).fetchall()}
legacy = sorted(db_tables - model_tables - {"alembic_version"})

print(f"模型表 {len(model_tables)} 张 / 库表 {len(db_tables)} 张 / 遗留 {len(legacy)} 张：")
total_rows = 0
for t in legacy:
    count = db.execute(text(f"SELECT COUNT(*) FROM `{t}`")).fetchone()[0]
    total_rows += count
    print(f"  {t}: {count} 行")
print(f"遗留表总行数: {total_rows}")

# 删除（遗留表间可能存在外键互引，先关闭检查）
db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
for t in legacy:
    db.execute(text(f"DROP TABLE `{t}`"))
    print(f"已删除: {t}")
db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
db.commit()

remaining = {r[0] for r in db.execute(text("SHOW TABLES")).fetchall()}
print("剩余表数:", len(remaining))
print("仍存在的非模型表:", remaining - model_tables - {"alembic_version"} or "无")
db.close()
