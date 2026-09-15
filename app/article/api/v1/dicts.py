"""项目模块字典接口（无 data_scope，登录即可）。

§5.2 约定：只读字典类接口只要求 get_current_user。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.article.enums import LABELS
from app.article.models import Article, ArticleProduct
from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.response import ok
from app.customer.models import Customer

router = APIRouter(prefix="/dicts", tags=["article-dict"])


def _enum(group: str) -> list[dict]:
    return [{"value": v, "label": l} for v, l in LABELS.get(group, {}).items()]


@router.get("/article")
def article_dict(_=Depends(get_current_user)):
    """项目模块全部枚举。"""
    return ok({
        "article_state": _enum("article_state"),
        "credit_term_unit": _enum("credit_term_unit"),
        "propose": _enum("propose"),
        "sure_type": _enum("sure_type"),
        "change_view": _enum("change_view"),
        "product_category": _enum("product_category"),
    })


@router.get("/article-products")
def article_products(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """产品字典（种子数据，只读）。"""
    rows = db.scalars(
        select(ArticleProduct).order_by(ArticleProduct.sort)
    ).all()
    # 从全局 LABELS 取 product_category 映射，与 _enum() 同源
    cat_map = LABELS.get("product_category", {})
    return ok([{
        "id": r.id,
        "name": r.name,
        "category": r.category,
        "category_display": cat_map.get(r.category, ""),
        "sort": r.sort,
    } for r in rows])


@router.get("/articles")
def articles_dict(
    q: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """项目下拉字典（表单选择用，如评审关联项目）。无 data_scope——
    业务模块选项目时需要看到全量，不应被归属过滤。
    """
    stmt = select(Article.id, Article.article_num, Customer.name).outerjoin(
        Customer, Customer.id == Article.customer_id
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Article.article_num.like(like))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {"id": aid, "article_num": num, "customer_name": cname}
        for aid, num, cname in rows
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})
