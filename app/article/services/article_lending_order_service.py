"""放款次序 service（ArticleLendingOrder 表）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.models import Article, ArticleLendingOrder
from app.article.schemas import LendingOrderCreate
from app.core.exceptions import BizError


def _get_article_or_404(db: Session, article_id: int) -> Article:
    """查主表，不存在抛 404。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def add_lending_order(
    db: Session, article_id: int, body: LendingOrderCreate, user_id: int
) -> None:
    """添加放款次序。"""
    article = _get_article_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可添加放款次序")

    if db.scalar(
        select(ArticleLendingOrder).where(
            ArticleLendingOrder.article_id == article_id,
            ArticleLendingOrder.seq == body.seq,
        )
    ):
        raise BizError(4091, f"次序 {body.seq} 已存在")

    db.add(ArticleLendingOrder(
        article_id=article_id,
        seq=body.seq,
        order_amount=body.order_amount,
        remark=body.remark,
        state=article.article_state,
    ))
    db.commit()
