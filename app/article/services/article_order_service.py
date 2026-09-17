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
from app.customer.enums import Genre as CustomerGenre
from app.customer.models import Customer, CustomerContact
from app.warrant.models import (
    Warrant,
    WarrantOwnership,
    WarrantHouse,
    WarrantGround,
    WarrantConstruction,
    WarrantReceiveExtend,
    WarrantStock,
    WarrantDraftExtend,
    WarrantVehicle,
    WarrantChattel,
    WarrantOther,
    WarrantHouseApp,
)

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
    """查某放款次序下的所有反担保措施，按 (ware_category, method_category) 排序。

    返回结构保证前端可以"每个保证人一行 / 每个权证一行"展开展示：
    - 保证类 (ware_category=1): guarantors = [{id, name, genre, genre_display, address, contact_name, contact_phone}]
    - 抵质押类 (ware_category!=1): collaterals = [{id, warrant_num, address, area, owners, description}]
    """
    sures = db.scalars(
        select(ArticleSure).where(ArticleSure.order_id == order_id)
    ).all()
    if not sures:
        return []

    sure_ids = [s.id for s in sures]
    guarantor_ware = WareCategory.GUARANTOR.value  # 1

    # ---- 1. 批量查 M2M 关系 ----
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

    cust_map: dict[int, list[int]] = {}
    for sid, cid in cust_rows:
        cust_map.setdefault(sid, []).append(cid)
    warrant_map: dict[int, list[int]] = {}
    for sid, wid in warrant_rows:
        warrant_map.setdefault(sid, []).append(wid)

    # ---- 2. 收集 customer_ids + owner_ids ----
    all_cids = {cid for cids in cust_map.values() for cid in cids}

    # ---- 3. 批量查 Warrant + WarrantOwnership + 各扩展表 ----
    all_wids = {wid for wids in warrant_map.values() for wid in wids}
    warrant_dict: dict[int, Warrant] = {}
    if all_wids:
        for w in db.scalars(select(Warrant).where(Warrant.id.in_(all_wids))).all():
            warrant_dict[w.id] = w

    # WarrantOwnership: warrant_id → [(owner_id, ownership_num), ...]
    ownership_map: dict[int, list[tuple[int, str]]] = {}
    if all_wids:
        own_rows = db.execute(
            select(WarrantOwnership.warrant_id, WarrantOwnership.owner_id, WarrantOwnership.ownership_num).where(
                WarrantOwnership.warrant_id.in_(all_wids)
            )
        ).all()
        for wid, oid, onum in own_rows:
            ownership_map.setdefault(wid, []).append((oid, onum))
            all_cids.add(oid)  # owner_ids 合并进 all_cids

    # ---- 3.5 批量查 Customer + CustomerContact（合并了保证人和所有权人）----
    cust_dict: dict[int, Customer] = {}
    if all_cids:
        for c in db.scalars(select(Customer).where(Customer.id.in_(all_cids))).all():
            cust_dict[c.id] = c

    contact_dict: dict[int, CustomerContact] = {}
    if all_cids:
        all_contacts = db.scalars(
            select(CustomerContact).where(CustomerContact.customer_id.in_(all_cids))
        ).all()
        from collections import defaultdict
        contact_groups: dict[int, list[CustomerContact]] = defaultdict(list)
        for ct in all_contacts:
            contact_groups[ct.customer_id].append(ct)
        for cid, contacts in contact_groups.items():
            primary = next((c for c in contacts if c.is_primary), None)
            contact_dict[cid] = primary or contacts[0]

    # 各 Warrant 扩展表批量查（按 warrant_type 分流）
    warrant_ext_info: dict[int, dict] = {}  # warrant_id → {address, area, detail}
    if all_wids:
        # 分 type 收集 warrant_ids
        type_groups: dict[int, list[int]] = {}
        for wid, w in warrant_dict.items():
            type_groups.setdefault(w.warrant_type, []).append(wid)

        # Helper: 批量查扩展表 + 统一输出 {address, area, detail, house_usage}
        def _fill_ext(
            wtype: int, ext_table,
            addr_field: str | None, area_field: str | None, detail_field: str | None,
            extra_fields: dict[str, str] | None = None,  # {'输出key': '表字段名', ...}
        ):
            wids = type_groups.get(wtype)
            if not wids:
                return
            rows = db.scalars(select(ext_table).where(ext_table.warrant_id.in_(wids))).all()
            for r in rows:
                info = {}
                if addr_field:
                    info['address'] = getattr(r, addr_field, None)
                if area_field:
                    v = getattr(r, area_field, None)
                    info['area'] = float(v) if v is not None else None
                if detail_field:
                    info['detail'] = getattr(r, detail_field, None)
                if extra_fields:
                    for out_key, attr in extra_fields.items():
                        info[out_key] = getattr(r, attr, None)
                warrant_ext_info[r.warrant_id] = info

        _fill_ext(1, WarrantHouse, 'house_locate', 'house_area', 'house_name',
                  extra_fields={'house_usage': 'house_usage', 'house_app': 'house_app'})
        _fill_ext(5, WarrantGround, 'ground_locate', 'ground_area', 'ground_app')
        _fill_ext(6, WarrantConstruction, 'construct_locate', 'construct_area', 'construct_app')
        _fill_ext(11, WarrantReceiveExtend, None, None, 'receive_unit')
        _fill_ext(21, WarrantStock, None, None, 'target')
        _fill_ext(41, WarrantVehicle, None, None, 'plate_num')
        _fill_ext(51, WarrantChattel, None, None, 'chattel_detail')
        _fill_ext(55, WarrantOther, None, None, 'other_detail')
        # 31 票据 / 99 他权 等暂无扩展表，留空即可

    # 批量查房产用途字典（WarrantHouseApp 是字典表，id→name）
    house_app_map: dict[int, str] = {}
    if all_wids:
        house_rows = db.scalars(
            select(WarrantHouseApp).where(WarrantHouseApp.status == 10)
        ).all()
        for h in house_rows:
            house_app_map[h.id] = h.name

    # ---- 4. 组装 ----
    result = []
    for s in sorted(sures, key=lambda x: (x.ware_category, x.method_category)):
        entry = {
            'sure_id': s.id,
            'ware_category': s.ware_category,
            'ware_category_display': WARE_MAP.get(s.ware_category, f'担保物{s.ware_category}'),
            'method_category': s.method_category,
            'method_category_display': METHOD_MAP.get(s.method_category, f'担保方式{s.method_category}'),
            'remark': s.remark,
        }

        if s.ware_category == guarantor_ware:
            # 保证类 → 每个保证人一行展开
            guarantors = []
            for cid in cust_map.get(s.id, []):
                c = cust_dict.get(cid)
                if not c:
                    continue
                contact = contact_dict.get(cid)
                genre_label = CustomerGenre.COMPANY.label if c.genre == CustomerGenre.COMPANY.value \
                    else CustomerGenre.PERSONAL.label if c.genre == CustomerGenre.PERSONAL.value \
                    else ''
                guarantors.append({
                    'sure_id': s.id,
                    'id': cid,
                    'name': c.name or c.license_num or '',
                    'genre': c.genre,
                    'genre_display': genre_label,
                    'address': (contact.addr if contact else None) or c.license_addr or '',
                    'contact_name': contact.name if contact else '',
                    'contact_phone': contact.phone if contact else '',
                })
            entry['guarantors'] = guarantors
            entry['collaterals'] = []
        else:
            # 抵质押类 → 每个权证一行展开
            house_usage_labels = {10: '自用', 20: '出租', 30: '空置'}
            collaterals = []
            for wid in warrant_map.get(s.id, []):
                w = warrant_dict.get(wid)
                if not w:
                    continue
                ext = warrant_ext_info.get(wid, {})
                # 所有权人 + 产权证号（都 join 所有）
                own_tuples = ownership_map.get(wid, [])  # [(owner_id, ownership_num), ...]
                owner_names = []
                ownership_nums = []
                for oid, onum in own_tuples:
                    oc = cust_dict.get(oid)
                    if oc:
                        owner_names.append(oc.name)
                    if onum:
                        ownership_nums.append(onum)
                house_usage = ext.get('house_usage')
                house_app = ext.get('house_app')
                collaterals.append({
                    'sure_id': s.id,
                    'id': wid,
                    'warrant_type': w.warrant_type,
                    'method_category': s.method_category,
                    'method_category_display': METHOD_MAP.get(s.method_category, f'担保方式{s.method_category}'),
                    'address': ext.get('address') or '',
                    'area': ext.get('area'),
                    'owners': '、'.join(owner_names),
                    'ownership_num': '、'.join(ownership_nums),
                    'description': ext.get('detail') or '',
                    'house_app': house_app,
                    'house_app_display': house_app_map.get(house_app, '') if house_app is not None else '',
                    'house_usage': house_usage,
                    'house_usage_display': house_usage_labels.get(house_usage, '') if house_usage is not None else '',
                })
            entry['collaterals'] = collaterals
            entry['guarantors'] = []

        result.append(entry)
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
