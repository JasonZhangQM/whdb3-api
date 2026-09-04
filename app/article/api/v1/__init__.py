"""项目模块路由聚合。"""

from fastapi import APIRouter

from app.article.api.v1 import articles, dicts

router = APIRouter()
router.include_router(dicts.router)
router.include_router(articles.router)
