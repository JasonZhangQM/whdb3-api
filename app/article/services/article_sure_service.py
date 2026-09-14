"""反担保措施 service（ArticleSure + ArticleSureCustomer）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.models import (
    Article, ArticleSure, ArticleSureCustomer,
)
from app.article.schemas import SureCreate
from app.core.exceptions import BizError


def _get_article_or_404(db: Session, article_id: int) -> Article:
    """查主表，不存在抛 404。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def upsert_sure(
    db: Session, article_id: int, body: SureCreate, user_id: int
) -> None:
    """添加/更新反担保措施（upsert by article_id + sure_type）。"""
    article = _get_article_or_404(db, article_id)
    if article.article_state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "当前状态不允许设置反担保措施")

    sure = db.scalar(
        select(ArticleSure).where(
            ArticleSure.article_id == article_id,
            ArticleSure.sure_type == body.sure_type,
        )
    )
    if sure is None:
        sure = ArticleSure(article_id=article_id, sure_type=body.sure_type)
        db.add(sure)

    sure.remark = body.remark
    db.flush()

    # 保证类：反担保人 M2M 全量替换
    if body.sure_type in (1, 2):
        db.execute(
            ArticleSureCustomer.__table__.delete().where(
                ArticleSureCustomer.sure_id == sure.id
            )
        )
        for cid in body.customer_ids:
            db.add(ArticleSureCustomer(sure_id=sure.id, customer_id=cid))

    db.commit()
