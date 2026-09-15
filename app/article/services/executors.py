"""项目模块审批 executor：注册到 APPLY_EXECUTORS，审批通过时原子应用。

设计决策 A13：executor 只做项目状态+签批字段写入 + 放款次序联动。
旧方案的"写客户授信"、"写权证 meeting_date"已删除（A3/A4）。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.enums import ArticleState
from app.article.models import Article, ArticleApproval, ArticleOrder
from app.approval.services import register_executor
from app.core.exceptions import BizError


def _get_or_create_approval(db: Session, article_id: int) -> ArticleApproval:
    """取或新建 ArticleApproval（一对一，upsert 语义）。"""
    ap = db.scalar(select(ArticleApproval).where(ArticleApproval.article_id == article_id))
    if ap is None:
        ap = ArticleApproval(article_id=article_id)
        db.add(ap)
        db.flush()  # 让 ap.id 立即可用
    return ap


def apply_sign(db: Session, instance) -> None:
    """签批通过 → 项目置 SIGNED + 签批字段写 ArticleApproval + 放款次序 state→50。"""
    article = db.get(Article, instance.biz_id)
    if article is None:
        raise BizError(4041, "项目不存在")

    # 签批字段写一对一表
    payload = instance.payload or {}
    ap = _get_or_create_approval(db, article.id)
    ap.sign_type = payload.get("sign_type")
    ap.sign_date = payload.get("sign_date")
    ap.rcd_opinion = payload.get("rcd_opinion")
    ap.convenor_opinion = payload.get("convenor_opinion")
    ap.sign_detail = payload.get("sign_detail")

    # 主表业务字段（renewal/augment 是续贷/新增金额，不搬）
    article.renewal = payload.get("renewal", article.renewal)
    article.augment = payload.get("augment", article.augment)
    article.article_state = ArticleState.SIGNED.value

    # 放款次序状态联动
    db.execute(
        ArticleOrder.__table__.update().where(
            ArticleOrder.article_id == article.id
        ).values(state=ArticleState.SIGNED.value)
    )


# ============ 注册到审批引擎 ============

register_executor("article_bill_sign", apply_sign)
