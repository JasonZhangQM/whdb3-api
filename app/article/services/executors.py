"""项目模块审批 executor：注册到 APPLY_EXECUTORS，审批通过时原子应用。

设计决策 A13：executor 只做项目状态+签批字段写入 + 放款次序联动。
旧方案的"写客户授信"、"写权证 meeting_date"已删除（A3/A4）。
"""

from sqlalchemy.orm import Session

from app.article.enums import ArticleState
from app.article.models import Article, ArticleLendingOrder
from app.approval.services import register_executor
from app.core.exceptions import BizError


def apply_sign(db: Session, instance) -> None:
    """签批通过 → 项目置 SIGNED + 放款次序 state→50。"""
    article = db.get(Article, instance.biz_id)
    if article is None:
        raise BizError(4041, "项目不存在")

    payload = instance.payload or {}
    article.sign_type = payload.get("sign_type")
    article.sign_date = payload.get("sign_date")
    article.rcd_opinion = payload.get("rcd_opinion")
    article.convenor_opinion = payload.get("convenor_opinion")
    article.sign_detail = payload.get("sign_detail")
    article.renewal = payload.get("renewal", article.renewal)
    article.augment = payload.get("augment", article.augment)
    article.article_state = ArticleState.SIGNED.value

    # 放款次序状态联动
    db.execute(
        ArticleLendingOrder.__table__.update().where(
            ArticleLendingOrder.article_id == article.id
        ).values(state=ArticleState.SIGNED.value)
    )


def apply_change(db: Session, instance) -> None:
    """变更申请通过 → 项目置 PENDING_CHANGE + 放款次序联动 + 写变更历史。"""
    article = db.get(Article, instance.biz_id)
    if article is None:
        raise BizError(4041, "项目不存在")

    article.article_state = ArticleState.PENDING_CHANGE.value
    # 放款次序状态联动
    db.execute(
        ArticleLendingOrder.__table__.update().where(
            ArticleLendingOrder.article_id == article.id
        ).values(state=ArticleState.PENDING_CHANGE.value)
    )


# ============ 注册到审批引擎 ============

register_executor("article_sign", apply_sign)
register_executor("article_change", apply_change)
