"""Alembic 环境：模型发现入口 + 迁移执行。

模型发现约定：每新增业务模块，在下方 MODELS_IMPORTS 登记一行
`import app.<module>.models`（总体方案 §4.5 单一发现入口）。
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.db import Base

# ---- 模型发现：新增模块在此登记 ----
import app.user.models  # noqa: F401,E402
import app.approval.models  # noqa: F401,E402
import app.attachment.models  # noqa: F401,E402
import app.institution.models  # noqa: F401,E402
import app.customer.models  # noqa: F401,E402
import app.warrant.models  # noqa: F401,E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 迁移使用的连接串来自应用配置（.env），与运行时同源
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL（--sql）。"""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连数据库执行。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
