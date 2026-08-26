"""全局配置：pydantic-settings 强类型，缺项启动即报错。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"

    # MySQL（同步驱动，naive datetime，utf8mb4）
    database_url: str

    # Redis（统一前缀 whdb_api:，URL 中密码需 percent-encode）
    redis_url: str

    # JWT
    jwt_secret: str
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
