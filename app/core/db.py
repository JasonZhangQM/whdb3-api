"""数据库引擎与会话：SQLAlchemy 2.0 同步模式。

事务边界约定：service 层用 `with db.begin():` 包裹"校验+写入"整体。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """全项目模型基类，所有模块模型继承此类（alembic autogenerate 依赖）。"""


settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # MySQL 8 小时断连保护
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：请求级会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
