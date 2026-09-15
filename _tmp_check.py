import re, os
from app.core.db import SessionLocal
from sqlalchemy import text

s = SessionLocal()
print('=== 表存在? ===')
rows = s.execute(text("SHOW TABLES LIKE 'article_single_quotas'")).fetchall()
print(rows)
print(f'表行数: {s.execute(text("SELECT COUNT(*) FROM article_single_quotas")).fetchone()[0] if rows else 0}')

print('\n=== 各文件关键词计数 ===')
files = {
    'models': 'c:/mysite/whdb3/whdb3-api/app/article/models/__init__.py',
    'schemas': 'c:/mysite/whdb3/whdb3-api/app/article/schemas/__init__.py',
    'service': 'c:/mysite/whdb3/whdb3-api/app/article/services/article_service.py',
    'router': 'c:/mysite/whdb3/whdb3-api/app/article/api/v1/articles.py',
    'svc_file': 'c:/mysite/whdb3/whdb3-api/app/article/services/article_single_quota_service.py',
}
for name, path in files.items():
    if os.path.exists(path):
        with open(path) as f:
            c = f.read()
        hits = [(kw, c.count(kw)) for kw in ['ArticleSingleQuota','article_single_quotas','SingleQuota','single_quotas','single_quota','single-quotas'] if c.count(kw) > 0]
        print(f'  {name}: {hits}')
    else:
        print(f'  {name}: 文件已删除')

# 前端
print('\n=== 前端 ===')
for p in ['c:/mysite/whdb3/whdb3-web/apps/web-antd/src/api/basic/article.ts',
          'c:/mysite/whdb3/whdb3-web/apps/web-antd/src/views/article/index.vue']:
    with open(p) as f:
        c = f.read()
    hits = [(kw, c.count(kw)) for kw in ['single_quota','quotaColumns','addQuotaRow','removeQuotaRow','single-quotas','SingleQuota','creditModelOpts'] if c.count(kw) > 0]
    print(f'  {os.path.basename(p)}: {hits}')
s.close()
