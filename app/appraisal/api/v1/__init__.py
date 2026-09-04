"""评审模块路由聚合。"""

from fastapi import APIRouter

from app.appraisal.api.v1 import appraisals, dicts

router = APIRouter()
router.include_router(dicts.router)
router.include_router(appraisals.router)
