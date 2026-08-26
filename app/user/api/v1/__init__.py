"""用户模块路由聚合（main.py 注册入口）。"""

from fastapi import APIRouter

from app.user.api.v1 import (
    auth,
    departments,
    dicts,
    logs,
    menus,
    roles,
    users,
)

router = APIRouter()
for sub in (auth, users, departments, roles, menus, logs, dicts):
    router.include_router(sub.router)
