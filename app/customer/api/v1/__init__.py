"""客户模块路由聚合：50 接口（字典 8 + 授信区域 7 + 集团 8 + 客户域 27）。

executors 的注册由 customers.py 顶层 import 触发（应用启动即生效）。
"""

from fastapi import APIRouter

from app.customer.api.v1 import credit_regions, customers, dicts, groups

router = APIRouter()
router.include_router(dicts.router)
router.include_router(credit_regions.router)
router.include_router(groups.router)
router.include_router(customers.router)
