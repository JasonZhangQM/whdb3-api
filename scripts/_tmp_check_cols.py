"""临时脚本：核对库中 id/created_by/created_at/updated_at 列的可空性与默认值。"""
from sqlalchemy import create_engine, text

from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
sql = text(
    "SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA "
    "FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA = DATABASE() "
    "AND COLUMN_NAME IN ('id', 'created_by', 'created_at', 'updated_at') "
    "ORDER BY TABLE_NAME, COLUMN_NAME"
)
with engine.connect() as conn:
    for row in conn.execute(sql):
        print(f"{row[0]:35s} {row[1]:12s} nullable={row[2]:3s} default={row[3]!r:30s} extra={row[4]}")
