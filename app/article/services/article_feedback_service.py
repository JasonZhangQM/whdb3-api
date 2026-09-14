"""风控反馈 service。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.enums import ArticleState
from app.article.models import Article, ArticleFeedback
from app.article.schemas import FeedbackCreate
from app.core.exceptions import BizError


def submit_feedback(
    db: Session, article_id: int, body: FeedbackCreate, user_id: int
) -> None:
    """提交风控反馈（upsert，提交后状态 → 20 已反馈）。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (10, 20):
        raise BizError(4031, "当前状态不允许提交反馈")

    feedback = db.scalar(
        select(ArticleFeedback).where(ArticleFeedback.article_id == article_id)
    )
    if feedback is None:
        feedback = ArticleFeedback(article_id=article_id, created_by=user_id)
        db.add(feedback)

    feedback.propose = body.propose
    feedback.analysis = body.analysis
    feedback.suggestion = body.suggestion

    article.article_state = ArticleState.FEEDBACK_DONE.value
    db.commit()
