"""单项额度 service（ArticleSingleQuota 表）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.models import Article, ArticleSingleQuota
from app.article.schemas import SingleQuotaCreate
from app.core.exceptions import BizError


def _get_article_or_404(db: Session, article_id: int) -> Article:
    """查主表，不存在抛 404。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def add_single_quota(
    db: Session, article_id: int, body: SingleQuotaCreate, user_id: int
) -> None:
    """添加/更新单项额度（upsert by article_id + credit_model）。"""
    article = _get_article_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可设置额度")

    quota = db.scalar(
        select(ArticleSingleQuota).where(
            ArticleSingleQuota.article_id == article_id,
            ArticleSingleQuota.credit_model == body.credit_model,
        )
    )
    if quota is None:
        quota = ArticleSingleQuota(
            article_id=article_id, credit_model=body.credit_model
        )
        db.add(quota)

    quota.credit_amount = body.credit_amount
    quota.flow_rate = body.flow_rate
    quota.remark = body.remark
    db.commit()
