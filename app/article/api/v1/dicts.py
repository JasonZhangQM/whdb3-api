"""项目模块字典接口（无 data_scope，登录即可）。

§5.2 约定：只读字典类接口只要求 get_current_user。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.enums import LABELS
from app.article.models import ArticleProduct
from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.response import ok

router = APIRouter(prefix="/dicts", tags=["article-dict"])


def _enum(group: str) -> list[dict]:
    return [{"value": v, "label": l} for v, l in LABELS.get(group, {}).items()]


@router.get("/article")
def article_dict(_=Depends(get_current_user)):
    """项目模块全部枚举。"""
    return ok({
        "article_state": _enum("article_state"),
        "article_product": _enum("article_product"),
        "repay_method": _enum("repay_method"),
        "propose": _enum("propose"),
        "credit_model": _enum("credit_model"),
        "sure_type": _enum("sure_type"),
        "change_view": _enum("change_view"),
    })


@router.get("/article-products")
def article_products(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """产品字典（种子数据，只读）。"""
    rows = db.scalars(
        select(ArticleProduct).order_by(ArticleProduct.sort)
    ).all()
    return ok([{
        "id": r.id,
        "name": r.name,
        "difficulty_score": float(r.difficulty_score),
        "sort": r.sort,
    } for r in rows])
