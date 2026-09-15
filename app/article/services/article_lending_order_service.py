"""放款次序 service（ArticleLendingOrder + 嵌套反担保措施聚合）。

提供：
- add_lending_order:     新增放款次序（已有）
- list_lending_orders:   按 article_id 查询全部放款次序，每条嵌套 sures 列表（含客户/权证名称）
- update_lending_order:  更新金额/备注（seq 不允许改）
- delete_lending_order:  删除放款次序 + 级联清理 sures / sure_customers / sure_warrants
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.models import (
    Article,
    ArticleLendingOrder,
    ArticleSure,
    ArticleSureCustomer,
    ArticleSureWarrant,
)
from app.article.schemas import LendingOrderCreate, LendingOrderUpdate
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.models import Warrant


# 反担保类型字典（保证类 1/2，抵质押类 11-59；详情展示用）
SURE_TYPE_MAP = {
    1: '保证-法定代表人',
    2: '保证-实际控制人',
    11: '抵押-房产',
    12: '抵押-土地',
    13: '抵押-机器设备',
    14: '抵押-车辆',
    21: '质押-股权',
    22: '质押-应收账款',
    23: '质押-存货',
    31: '留置',
    41: '定金',
    51: '保理',
    52: '信用证',
    53: '保函',
    54: '保险',
    55: '仓储监管',
    56: '资产证券化',
    57: '融资租赁',
    58: '合作担保机构',
    59: '其他担保',
}


def _get_article_or_404(db: Session, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def _get_order_or_404(
    db: Session, article_id: int, order_id: int
) -> ArticleLendingOrder:
    order = db.scalar(
        select(ArticleLendingOrder).where(
            ArticleLendingOrder.id == order_id,
            ArticleLendingOrder.article_id == article_id,
        )
    )
    if order is None:
        raise BizError(4041, "放款次序不存在")
    return order


def _build_sures_for_order(db: Session, order_id: int) -> list[dict]:
    """查某放款次序下的所有反担保措施 + 客户/权证名称，按 sure_type 排序返回 dict 列表。"""
    sures = db.scalars(
        select(ArticleSure).where(ArticleSure.lending_order_id == order_id)
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
    for s in sorted(sures, key=lambda x: x.sure_type):
        cids = cust_map.get(s.id, [])
        wids = warrant_map.get(s.id, [])
        result.append({
            'sure_type': s.sure_type,
            'sure_type_display': SURE_TYPE_MAP.get(s.sure_type, f'担保{s.sure_type}'),
            'remark': s.remark,
            'customer_ids': cids,
            'customer_names': [cust_names[c] for c in cids],
            'warrant_ids': wids,
            'warrant_names': [warrant_names[w] for w in wids],
        })
    return result


# ============ CRUD ============

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


def list_lending_orders(db: Session, article_id: int) -> list[dict]:
    """查询某项目的全部放款次序（按 seq 升序），每条嵌套 sures 列表。"""
    _get_article_or_404(db, article_id)

    orders = db.scalars(
        select(ArticleLendingOrder)
        .where(ArticleLendingOrder.article_id == article_id)
        .order_by(ArticleLendingOrder.seq.asc())
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


def update_lending_order(
    db: Session, article_id: int, order_id: int, body: LendingOrderUpdate
) -> None:
    """更新放款次序（仅金额 + 备注，seq 不允许改；状态同文章状态同步）。"""
    _get_article_or_404(db, article_id)
    order = _get_order_or_404(db, article_id, order_id)

    # 状态保护：只有非终态才允许修改
    if order.state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "放款已进行/已结清的次序不允许修改")

    if body.order_amount is not None:
        order.order_amount = body.order_amount
    if body.remark is not None:
        order.remark = body.remark

    db.commit()


def delete_lending_order(db: Session, article_id: int, order_id: int) -> None:
    """删除放款次序 + 级联清理其下所有反担保措施及 M2M。"""
    _get_article_or_404(db, article_id)
    order = _get_order_or_404(db, article_id, order_id)

    # 终态保护
    if order.state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "放款已进行/已结清的次序不允许删除")

    # 收集 sure_id
    sure_ids = db.scalars(
        select(ArticleSure.id).where(ArticleSure.lending_order_id == order_id)
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
