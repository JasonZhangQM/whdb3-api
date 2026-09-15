from app.core.db import SessionLocal
from sqlalchemy import text
s = SessionLocal()
print('=== 字典相关表 ===')
for r in s.execute(text("SHOW TABLES LIKE '%dict%'")).fetchall(): print(' ', r[0])
print()

# 查所有包含 credit_model 条目的表
for tbl_row in s.execute(text("SHOW TABLES")).fetchall():
    tbl = tbl_row[0]
    try:
        cols = [c[0] for c in s.execute(text(f"SHOW COLUMNS FROM `{tbl}`")).fetchall()]
        if 'dict_type' in cols or 'type' in cols:
            print(f'\n尝试 {tbl}...')
            for dtype_col in ['dict_type', 'type']:
                try:
                    rows = s.execute(text(f"SELECT * FROM `{tbl}` WHERE `{dtype_col}`='credit_model'")).fetchall()
                    if rows:
                        print(f'  {tbl}.{dtype_col} = credit_model -> {len(rows)} rows')
                        for r in rows: print('   ', r)
                except Exception:
                    pass
    except Exception:
        pass

# 现有 single_quotas credit_model 值
print('\n=== 现有 single_quotas credit_model ===')
for r in s.execute(text('SELECT DISTINCT credit_model FROM article_single_quotas')).fetchall():
    print(' ', r[0])
s.close()
