"""放款次序 service（ArticleOrder + 嵌套反担保措施聚合）。

提供：
- add_order:         新增放款次序
- list_orders:       按 article_id 查询全部放款次序，每条嵌套 sures 列表（含客户/权证名称）
- update_order:      更新金额/备注（seq 不允许改）
- delete_order:      删除放款次序 + 级联清理 sures / sure_customers / sure_warrants
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.enums import WareCategory, MethodCategory
from app.article.models import (
    Article,
    ArticleOrder,
    ArticleSure,
    ArticleSureCustomer,
    ArticleSureWarrant,
)
from app.article.schemas import LendingOrderCreate, LendingOrderUpdate
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.models import Warrant

# 枚举 value → label 字典（替代旧 SureType）
WARE_MAP = {w.value: w.label for w in WareCategory}
METHOD_MAP = {m.value: m.label for m in MethodCategory}


def _get_article_or_404(db: Session, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def _get_order_or_404(
    db: Session, article_id: int, order_id: int
) -> ArticleOrder:
    order = db.scalar(
        select(ArticleOrder).where(
            ArticleOrder.id == order_id,
            ArticleOrder.article_id == article_id,
        )
    )
    if order is None:
        raise BizError(4041, "放款次序不存在")
    return order


def _build_sures_for_order(db: Session, order_id: int) -> list[dict]:
    """查某放款次序下的所有反担保措施 + 客户/权证名称，按 (ware_category, method_category) 排序返回 dict 列表。"""
    sures = db.scalars(
        select(ArticleSure).where(ArticleSure.order_id == order_id)
    ).all()
    if not sures:
        return []

    sure_ids = [s.id for s in sures]

    # 批量查 M2M
    cust_rows = db.execute(
        select(ArticleSureCustomer.sure_id, ArticleSureCustomer.customer_id).where(
            ArticleSureCustomer.sure_id.in_(sure_ids)
        )
    ).all()
    warrant_rows = db.execute(
        select(ArticleSureWarrant.sure_id, ArticleSureWarrant.warrant_id).where(
            ArticleSureWarrant.sure_id.in_(sure_ids)
        )
    ).all()

    # 分组
    cust_map: dict[int, list[int]] = {}
    for sid, cid in cust_rows:
        cust_map.setdefault(sid, []).append(cid)
    warrant_map: dict[int, list[int]] = {}
    for sid, wid in warrant_rows:
        warrant_map.setdefault(sid, []).append(wid)

    # 批量查名称
    all_cids = {cid for cids in cust_map.values() for cid in cids}
    all_wids = {wid for wids in warrant_map.values() for wid in wids}
    cust_names: dict[int, str] = {}
    warrant_names: dict[int, str] = {}
    if all_cids:
        for c in db.scalars(select(Customer).where(Customer.id.in_(all_cids))).all():
            cust_names[c.id] = c.name or c.license_num or ''
    if all_wids:
        for w in db.scalars(select(Warrant).where(Warrant.id.in_(all_wids))).all():
            warrant_names[w.id] = w.warrant_num or ''

    # 组装
    result = []
    for s in sorted(sures, key=lambda x: (x.ware_category, x.method_category)):
        cids = cust_map.get(s.id, [])
        wids = warrant_map.get(s.id, [])
        result.append({
            'ware_category': s.ware_category,
            'ware_category_display': WARE_MAP.get(s.ware_category, f'担保物{s.ware_category}'),
            'method_category': s.method_category,
            'method_category_display': METHOD_MAP.get(s.method_category, f'担保方式{s.method_category}'),
            'remark': s.remark,
            'customer_ids': cids,
            'customer_names': [cust_names[c] for c in cids],
            'warrant_ids': wids,
            'warrant_names': [warrant_names[w] for w in wids],
        })
    return result


# ============ CRUD ============

def add_order(
    db: Session, article_id: int, body: LendingOrderCreate, user_id: int
) -> None:
    """添加放款次序。

    序号由后端自动分配（当前项目最大 seq + 1，从 1 起），
    同时校验新增后 Σ 放款金额 ≤ 项目 renewal + augment。
    """
    from decimal import Decimal

    article = _get_article_or_404(db, article_id)
    if article.article_state not in (10, 61):
        raise BizError(4031, "待反馈/待变更状态可添加放款次序")

    # 自动分配 seq：当前项目最大 seq + 1，没有任何次序时从 1 起
    max_seq = db.scalar(
        select(ArticleOrder.seq)
        .where(ArticleOrder.article_id == article_id)
        .order_by(ArticleOrder.seq.desc())
        .limit(1)
    )
    next_seq = (max_seq or 0) + 1

    # 校验 Σ 放款金额 ≤ renewal + augment
    existing_orders = db.scalars(
        select(ArticleOrder).where(ArticleOrder.article_id == article_id)
    ).all()
    total = sum((o.order_amount for o in existing_orders), Decimal('0'))
    new_total = total + body.order_amount
    limit = (article.renewal or Decimal('0')) + (article.augment or Decimal('0'))
    if new_total > limit:
        raise BizError(
            4031,
            f"放款次序累计金额 {new_total} 已超过项目授信额度 {limit}（续贷 {article.renewal or 0} + 新增 {article.augment or 0}）",
        )

    db.add(ArticleOrder(
        article_id=article_id,
        seq=next_seq,
        order_amount=body.order_amount,
        remark=body.remark,
        state=article.article_state,
    ))
    db.commit()


def list_orders(db: Session, article_id: int) -> list[dict]:
    """查询某项目的全部放款次序（按 seq 升序），每条嵌套 sures 列表。"""
    _get_article_or_404(db, article_id)

    orders = db.scalars(
        select(ArticleOrder)
        .where(ArticleOrder.article_id == article_id)
        .order_by(ArticleOrder.seq.asc())
    ).all()

    result = []
    for o in orders:
        sures = _build_sures_for_order(db, o.id)
        result.append({
            'id': o.id,
            'seq': o.seq,
            'order_amount': o.order_amount,
            'state': o.state,
            'remark': o.remark,
            'sures': sures,
        })
    return result


def update_order(
    db: Session, article_id: int, order_id: int, body: LendingOrderUpdate
) -> None:
    """更新放款次序（仅金额 + 备注，seq 不允许改；状态同文章状态同步）。"""
    from decimal import Decimal

    article = _get_article_or_404(db, article_id)
    order = _get_order_or_404(db, article_id, order_id)

    # 状态保护：只有非终态才允许修改
    if order.state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "放款已进行/已结清的次序不允许修改")

    if body.order_amount is not None:
        # 校验：修改后 Σ 放款金额 ≤ renewal + augment
        other_orders = db.scalars(
            select(ArticleOrder).where(
                ArticleOrder.article_id == article_id,
                ArticleOrder.id != order_id,
            )
        ).all()
        total_without_this = sum((o.order_amount for o in other_orders), Decimal('0'))
        new_total = total_without_this + body.order_amount
        limit = (article.renewal or Decimal('0')) + (article.augment or Decimal('0'))
        if new_total > limit:
            raise BizError(
                4031,
                f"放款次序累计金额 {new_total} 已超过项目授信额度 {limit}（续贷 {article.renewal or 0} + 新增 {article.augment or 0}）",
            )
        order.order_amount = body.order_amount
    if body.remark is not None:
        order.remark = body.remark

    db.commit()


def delete_order(db: Session, article_id: int, order_id: int) -> None:
    """删除放款次序 + 级联清理其下所有反担保措施及 M2M。"""
    _get_article_or_404(db, article_id)
    order = _get_order_or_404(db, article_id, order_id)

    # 终态保护
    if order.state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "放款已进行/已结清的次序不允许删除")

    # 收集 sure_id
    sure_ids = db.scalars(
        select(ArticleSure.id).where(ArticleSure.order_id == order_id)
    ).all()

    if sure_ids:
        sid_list = list(sure_ids)
        db.execute(
            ArticleSureCustomer.__table__.delete().where(
                ArticleSureCustomer.sure_id.in_(sid_list)
            )
        )
        db.execute(
            ArticleSureWarrant.__table__.delete().where(
                ArticleSureWarrant.sure_id.in_(sid_list)
            )
        )
        db.execute(
            ArticleSure.__table__.delete().where(ArticleSure.id.in_(sid_list))
        )

    db.delete(order)
    db.commit()
