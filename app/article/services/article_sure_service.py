"""反担保措施 service（ArticleSure + ArticleSureCustomer + ArticleSureWarrant）。

旧系统对应 LendingSures + LendingCustoms + LendingWarrants：
- ArticleSure          ← LendingSures（从 FK Articles 改 FK ArticleOrder）
- ArticleSureCustomer  ← LendingCustoms（O2O 改 M2M 中间表）
- ArticleSureWarrant   ← LendingWarrants（O2O 改 M2M 中间表，新增）
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.models import (
    Article,
    ArticleOrder,
    ArticleSure,
    ArticleSureCustomer,
    ArticleSureWarrant,
)
from app.article.schemas import SureCreate
from app.core.exceptions import BizError


def _get_lending_or_404(
    db: Session, article_id: int, order_id: int
) -> ArticleOrder:
    """查放款次序，校验归属项目。"""
    order = db.get(ArticleOrder, order_id)
    if order is None:
        raise BizError(4041, "放款次序不存在")
    if order.article_id != article_id:
        raise BizError(4031, "放款次序不属于该项目")
    return order


def upsert_sure(
    db: Session, article_id: int, body: SureCreate, user_id: int
) -> None:
    """添加/更新反担保措施（upsert by order_id + ware_category + method_category）。

    保证类同时写入 ArticleSureCustomer；抵质押类同时写入 ArticleSureWarrant。
    同一 ArticleSure 下可追加多个客户/权证（M2M 追加，不替换）。
    """
    from app.article.enums import WareCategory

    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    # 状态门槛：待反馈/待变更可设置反担保措施
    if article.article_state not in (10, 61):
        raise BizError(4031, "待反馈/待变更状态可设置反担保措施")

    # 校验放款次序归属
    _get_lending_or_404(db, article_id, body.order_id)

    # upsert sure（唯一键落在 order_id + ware_category + method_category）
    sure = db.scalar(
        select(ArticleSure).where(
            ArticleSure.order_id == body.order_id,
            ArticleSure.ware_category == body.ware_category,
            ArticleSure.method_category == body.method_category,
        )
    )
    created = False
    if sure is None:
        sure = ArticleSure(
            order_id=body.order_id,
            article_id=article_id,
            ware_category=body.ware_category,
            method_category=body.method_category,
            remark=body.remark,  # 仅新建时写 remark
        )
        db.add(sure)
        created = True

    db.flush()  # 拿到 sure.id

    # M2M 追加：不删旧的，只加不存在的（避免重复撞唯一约束）
    if body.ware_category == WareCategory.GUARANTOR.value:
        existing_cids = set(
            db.scalars(
                select(ArticleSureCustomer.customer_id).where(
                    ArticleSureCustomer.sure_id == sure.id,
                )
            ).all()
        )
        for cid in body.customer_ids:
            if cid not in existing_cids:
                db.add(ArticleSureCustomer(sure_id=sure.id, customer_id=cid))
    else:
        existing_wids = set(
            db.scalars(
                select(ArticleSureWarrant.warrant_id).where(
                    ArticleSureWarrant.sure_id == sure.id,
                )
            ).all()
        )
        for wid in body.warrant_ids:
            if wid not in existing_wids:
                db.add(ArticleSureWarrant(sure_id=sure.id, warrant_id=wid))

    db.commit()
