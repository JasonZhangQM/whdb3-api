"""健康检查：GET /api/v1/health（进程）+ GET /api/v1/health/db（MySQL/Redis 探活）。"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.db import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"code": 0, "message": "ok", "data": {"env": "dev"}}


@router.get("/health/db")
def health_db() -> dict:
    checks = {}

    # MySQL 探活
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["mysql"] = "up"
    except Exception:
        logger.exception("MySQL health check failed")
        checks["mysql"] = "down"

    # Redis 探活（M0 仅连通性；key 前缀 whdb_api: 见总体方案 §4.6）
    try:
        import redis as redis_lib

        from app.core.config import get_settings

        client = redis_lib.Redis.from_url(get_settings().redis_url, socket_timeout=2)
        client.ping()
        client.close()
        checks["redis"] = "up"
    except Exception:
        logger.exception("Redis health check failed")
        checks["redis"] = "down"

    code = 0 if all(v == "up" for v in checks.values()) else 5001
    return {"code": code, "message": "ok" if code == 0 else "degraded", "data": checks}
