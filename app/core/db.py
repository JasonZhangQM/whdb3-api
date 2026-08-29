"""数据库引擎与会话：SQLAlchemy 2.0 同步模式。

事务边界约定：认证依赖已在会话上隐式开启事务（autobegin），
路由层直接调 service 后 `db.commit()`；异常时 get_db close 即回滚。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

from app.core.config import get_settings


class Base(DeclarativeBase):
    """全项目模型基类：统一 id 主键 + 审计四字段（AGENTS.md §4.1）。

    - 所有表（含中间表）统一 id BIGINT AUTO_INCREMENT 主键；
      复合键中间表用 UNIQUE 约束替代复合主键
    - created_by 可空：登录日志 / 系统任务等无自然创建人的场景
    - 基类声明的列会被复制到每个子类表（declarative 机制），子类
      可覆写同名列（如加索引），但不得删除
    """

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP")
    )
    # MySQL 8+：默认值 + 行更新时自动刷新，一条 server_default 表达
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


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
