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
        # 保证类：先收集同放款次序下所有 SureCustomer，防止同一客户在同一次序里重复
        all_order_cids: set[int] = set()
        all_order_cids.update(
            db.scalars(
                select(ArticleSureCustomer.customer_id)
                .join(ArticleSure, ArticleSure.id == ArticleSureCustomer.sure_id)
                .where(ArticleSure.order_id == body.order_id)
            ).all()
        )
        existing_cids: set[int] = set(
            db.scalars(
                select(ArticleSureCustomer.customer_id).where(
                    ArticleSureCustomer.sure_id == sure.id,
                )
            ).all()
        )
        for cid in body.customer_ids:
            if cid in existing_cids:
                continue
            if cid in all_order_cids:
                raise BizError(
                    4001,
                    "同一放款次序下同一客户不能重复作为反担保人，"
                    "请在对应的反担保措施里删除后再添加",
                )
            db.add(ArticleSureCustomer(sure_id=sure.id, customer_id=cid))
    else:
        # 抵质押类：先收集同放款次序下所有 SureWarrant，防止同一权证在同一次序里重复
        all_order_wids: set[int] = set()
        all_order_wids.update(
            db.scalars(
                select(ArticleSureWarrant.warrant_id)
                .join(ArticleSure, ArticleSure.id == ArticleSureWarrant.sure_id)
                .where(ArticleSure.order_id == body.order_id)
            ).all()
        )
        existing_wids: set[int] = set(
            db.scalars(
                select(ArticleSureWarrant.warrant_id).where(
                    ArticleSureWarrant.sure_id == sure.id,
                )
            ).all()
        )
        for wid in body.warrant_ids:
            if wid in existing_wids:
                continue
            if wid in all_order_wids:
                raise BizError(
                    4001,
                    "同一放款次序下同一权证不能重复作为反担保物，"
                    "请在对应的反担保措施里删除后再添加",
                )
            db.add(ArticleSureWarrant(sure_id=sure.id, warrant_id=wid))

    db.commit()


def delete_sure_row(
    db: Session, article_id: int, sure_id: int, row_type: str, row_id: int
) -> None:
    """从 M2M 中间表删除一条反担保关联（单行删除）。

    - row_type='customer' → ArticleSureCustomer
    - row_type='warrant'  → ArticleSureWarrant
    删完后若该 Sure 无任何关联（两边中间表都空），则级联删除 ArticleSure 本身。
    """
    from app.core.exceptions import BizError

    # 校验 sure 归属
    sure = db.get(ArticleSure, sure_id)
    if sure is None:
        raise BizError(4041, "反担保措施不存在")
    if sure.article_id != article_id:
        raise BizError(4031, "反担保措施不属于该项目")

    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (10, 61):
        raise BizError(4031, "待反馈/待变更状态可删除反担保措施")

    if row_type == 'customer':
        db.execute(
            ArticleSureCustomer.__table__.delete().where(
                ArticleSureCustomer.sure_id == sure_id,
                ArticleSureCustomer.customer_id == row_id,
            )
        )
    elif row_type == 'warrant':
        db.execute(
            ArticleSureWarrant.__table__.delete().where(
                ArticleSureWarrant.sure_id == sure_id,
                ArticleSureWarrant.warrant_id == row_id,
            )
        )
    else:
        raise BizError(4001, "row_type 必须是 customer 或 warrant")

    # 若 Sure 已无任何关联，级联删 Sure
    remaining_cust = db.scalar(
        select(ArticleSureCustomer).where(ArticleSureCustomer.sure_id == sure_id)
    )
    remaining_warrant = db.scalar(
        select(ArticleSureWarrant).where(ArticleSureWarrant.sure_id == sure_id)
    )
    if remaining_cust is None and remaining_warrant is None:
        db.delete(sure)

    db.commit()
