"""权证主服务：列表/详情/创建（按类型联动）/修改/删除/批量/统计。

与客户模块不同：权证创建不走审批流，由项目经理/风控专员直接创建（设计 §3.3）。
数据级权限按 created_by 过滤（设计 §4）。
"""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, apply_data_scope_filter
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.enums import LABELS, StorageType, WarrantState, WarrantType
from app.warrant.models import (
    Warrant,
    WarrantDraft,
    WarrantDraftExtend,
    WarrantEvaluate,
    WarrantEvaluateCompany,
    WarrantEvaluateRecheck,
    WarrantGround,
    WarrantHouse,
    WarrantOwnership,
    WarrantStorage,
)
from app.warrant.schemas import (
    StorageCreate,
    WarrantCreate,
    WarrantUpdate,
)

# storage_type → warrant_state 联动映射（设计 §3.5）
STORAGE_STATE_MAP = {
    StorageType.STORE_IN: WarrantState.STORED,
    StorageType.RENEW_OUT: WarrantState.RENEW_OUT,
    StorageType.GUARD: WarrantState.GUARDED,
    StorageType.NO_NEED: WarrantState.NO_NEED,
    StorageType.LEND_OUT: WarrantState.LENT,
    StorageType.RETURN: WarrantState.STORED,
    StorageType.RELEASE_OUT: WarrantState.RELEASED,
    StorageType.TRANSFER: WarrantState.TRANSFERRED,
}

# 类型 → 创建/更新时扩展信息属性名（warrant_type 与 schema 字段对应）
TYPE_EXT_FIELD = {
    WarrantType.HOUSE: "houses",
    WarrantType.GROUND: "grounds",
    WarrantType.CONSTRUCTION: "constructions",
    WarrantType.RECEIVABLE: "receivable",
    WarrantType.STOCK: "stock",
    WarrantType.DRAFT: "draft",
    WarrantType.VEHICLE: "vehicle",
    WarrantType.CHATTEL: "chattel",
    WarrantType.OTHER: "other",
}


def _disp(group: str, value: int | None) -> str | None:
    if value is None:
        return None
    return LABELS[group].get(value, str(value))


def _get_or_404(db: Session, warrant_id: int) -> Warrant:
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


def _get_warrant_with_scope(
    db: Session, warrant_id: int, ctx: AuthContext
) -> Warrant:
    """获取权证 + 数据级权限校验（无权限返回 404 避免枚举 id）。"""
    if ctx.is_super_admin or ctx.data_scope == 40:  # ALL
        return _get_or_404(db, warrant_id)

    stmt = select(Warrant).where(Warrant.id == warrant_id)
    stmt = apply_data_scope_filter(db, stmt, ctx, owner_field="created_by")
    w = db.scalar(stmt)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


# ===== 列表 =====

def list_warrants(
    db: Session,
    ctx: AuthContext,
    page: int,
    page_size: int,
    warrant_type: int | None = None,
    warrant_state: int | None = None,
    auction_state: int | None = None,
    owner_id: int | None = None,
    evaluate_method: int | None = None,
    q: str | None = None,
) -> tuple[list[dict], int]:
    stmt = select(Warrant).order_by(Warrant.id.desc())
    # 数据级权限：按创建者过滤（设计 §4：本人在 created_by / 部门 / 全部）
    stmt = apply_data_scope_filter(db, stmt, ctx, owner_field="created_by")

    if warrant_type is not None:
        stmt = stmt.where(Warrant.warrant_type == warrant_type)
    if warrant_state is not None:
        stmt = stmt.where(Warrant.warrant_state == warrant_state)
    if auction_state is not None:
        stmt = stmt.where(Warrant.auction_state == auction_state)
    if evaluate_method is not None:
        stmt = stmt.where(Warrant.evaluate_method == evaluate_method)
    if q:
        stmt = stmt.where(Warrant.warrant_num.like(f"%{q}%"))
    if owner_id is not None:
        stmt = stmt.join(WarrantOwnership, WarrantOwnership.warrant_id == Warrant.id).where(
            WarrantOwnership.owner_id == owner_id
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    # 批量取所有权人名称与最近出入库（避免 N+1）
    wids = [w.id for w in rows]
    owner_map = _owner_names_map(db, wids)
    user_names = _user_names(db, {w.created_by for w in rows})
    latest_storage = _latest_storages(db, wids)

    items = []
    for w in rows:
        items.append(
            {
                "id": w.id,
                "warrant_num": w.warrant_num,
                "warrant_type": w.warrant_type,
                "warrant_type_display": _disp("warrant_type", w.warrant_type),
                "warrant_state": w.warrant_state,
                "warrant_state_display": _disp("warrant_state", w.warrant_state),
                "auction_state": w.auction_state,
                "auction_state_display": _disp("auction_state", w.auction_state),
                "evaluate_value": float(w.evaluate_value) if w.evaluate_value else None,
                "evaluate_method": w.evaluate_method,
                "evaluate_method_display": _disp("evaluate_method", w.evaluate_method),
                "owner_names": owner_map.get(w.id, []),
                "storage_latest": latest_storage.get(w.id),
                "created_by_name": user_names.get(w.created_by, ""),
                "created_at": w.created_at,
            }
        )
    return items, total


def _owner_names_map(db: Session, warrant_ids: list[int]) -> dict[int, list[str]]:
    if not warrant_ids:
        return {}
    rows = db.execute(
        select(WarrantOwnership.warrant_id, Customer.name)
        .join(Customer, Customer.id == WarrantOwnership.owner_id)
        .where(WarrantOwnership.warrant_id.in_(warrant_ids))
    ).all()
    result: dict[int, list[str]] = {}
    for wid, name in rows:
        result.setdefault(wid, []).append(name)
    return result


def _user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    from app.user.models import User

    return dict(
        db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
    )


def _latest_storages(db: Session, warrant_ids: list[int]) -> dict[int, dict]:
    """批量取每个权证最近一条出入库——ROW_NUMBER() 窗口函数，数据库层完成分组，
    避免 Python 拉全量记录再按 warrant_id 分组。
    """
    from sqlalchemy import func

    if not warrant_ids:
        return {}

    # 用 CTE / 子查询先给每条出入库编排名，再取 rn=1——一条 SQL 搞定
    storage = WarrantStorage
    rn = func.row_number().over(
        partition_by=storage.warrant_id,
        order_by=(storage.storage_date.desc(), storage.id.desc()),
    ).label("rn")
    subq = (
        select(storage.id, storage.warrant_id, storage.storage_type,
               storage.storage_explain, storage.transfer_id,
               storage.conservator_id, storage.storage_date, rn)
        .where(storage.warrant_id.in_(warrant_ids))
        .subquery()
    )
    rows = db.execute(select(subq).where(subq.c.rn == 1)).all()
    return {
        r.warrant_id: {
            "id": r.id,
            "storage_type": r.storage_type,
            "storage_type_display": _disp("storage_type", r.storage_type),
            "storage_explain": r.storage_explain,
            "transfer_id": r.transfer_id,
            "conservator_id": r.conservator_id,
            "conservator_name": None,
            "storage_date": r.storage_date,
        }
        for r in rows
    }


def _storage_brief(s: WarrantStorage, transfer_name, conservator_name) -> dict:
    return {
        "id": s.id,
        "storage_type": s.storage_type,
        "storage_type_display": _disp("storage_type", s.storage_type),
        "storage_explain": s.storage_explain,
        "transfer_id": s.transfer_id,
        "transfer_name": transfer_name,
        "conservator_id": s.conservator_id,
        "conservator_name": conservator_name,
        "storage_date": s.storage_date,
    }


# ===== 出入库 / 评估（独立轻量查询 + 被 get_detail 复用）=====

def list_storages(db: Session, warrant_id: int, ctx: AuthContext) -> list[dict]:
    """出入库历史列表（独立接口 + get_detail 内部复用，不查扩展表）。"""
    _get_warrant_with_scope(db, warrant_id, ctx)  # 鉴权 + 存在性校验
    storages = db.scalars(
        select(WarrantStorage)
        .where(WarrantStorage.warrant_id == warrant_id)
        .order_by(WarrantStorage.storage_date.desc(), WarrantStorage.id.desc())
    ).all()
    uids = {s.conservator_id for s in storages if s.conservator_id}
    uids |= {s.transfer_id for s in storages if s.transfer_id}
    user_names = _user_names(db, uids)
    return [
        _storage_brief(s, user_names.get(s.transfer_id), user_names.get(s.conservator_id))
        for s in storages
    ]


def list_evaluates(db: Session, warrant_id: int, ctx: AuthContext) -> list[dict]:
    """评估历史列表（含复核）。独立接口 + get_detail 内部复用。"""
    _get_warrant_with_scope(db, warrant_id, ctx)
    evaluates = db.scalars(
        select(WarrantEvaluate)
        .where(WarrantEvaluate.warrant_id == warrant_id)
        .order_by(WarrantEvaluate.evaluate_date.desc(), WarrantEvaluate.id.desc())
    ).all()
    user_names = _user_names(db, {e.created_by for e in evaluates if e.created_by})
    eval_ids = [e.id for e in evaluates]
    recheck_map = dict()
    if eval_ids:
        rr = db.scalars(
            select(WarrantEvaluateRecheck).where(WarrantEvaluateRecheck.evaluate_id.in_(eval_ids))
        ).all()
        recheck_map = {r.evaluate_id: r for r in rr}
    return [
        {
            "id": e.id,
            "evaluate_method": e.evaluate_method,
            "evaluate_method_display": _disp("evaluate_method", e.evaluate_method),
            "evaluate_value": float(e.evaluate_value),
            "evaluate_date": e.evaluate_date,
            "evaluate_explain": e.evaluate_explain,
            "evaluate_company": e.evaluate_company,
            "created_by_name": user_names.get(e.created_by, ""),
            "recheck": (
                {
                    "id": rc.id,
                    "check_value": float(rc.check_value),
                    "recheck_value": float(rc.recheck_value),
                    "recheck_channel": rc.recheck_channel,
                    "remark": rc.remark,
                }
                if (rc := recheck_map.get(e.id)) else None
            ),
        }
        for e in evaluates
    ]


# ===== 详情（一次性聚合）=====

def get_detail(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    from app.warrant.services import ext_service

    w = _get_warrant_with_scope(db, warrant_id, ctx)
    user_ids = {w.created_by}
    # 所有权人
    owners_rows = db.execute(
        select(WarrantOwnership, Customer.name)
        .join(Customer, Customer.id == WarrantOwnership.owner_id)
        .where(WarrantOwnership.warrant_id == warrant_id)
        .order_by(WarrantOwnership.id)
    ).all()
    owners = [
        {
            "id": o.id,
            "ownership_num": o.ownership_num,
            "owner_id": o.owner_id,
            "owner_name": oname,
            "share_ratio": float(o.share_ratio) if o.share_ratio is not None else None,
        }
        for o, oname in owners_rows
    ]
    # 出入库 / 评估 —— 复用独立轻量函数（避免在 get_detail 里散落重复查询）
    storage_items = list_storages(db, warrant_id, ctx)
    evaluate_items = list_evaluates(db, warrant_id, ctx)
    user_names = _user_names(db, user_ids)  # 主表创建人

    detail = {
        "id": w.id,
        "warrant_num": w.warrant_num,
        "warrant_type": w.warrant_type,
        "warrant_type_display": _disp("warrant_type", w.warrant_type),
        "warrant_state": w.warrant_state,
        "warrant_state_display": _disp("warrant_state", w.warrant_state),
        "auction_state": w.auction_state,
        "auction_state_display": _disp("auction_state", w.auction_state),
        "evaluate_method": w.evaluate_method,
        "evaluate_method_display": _disp("evaluate_method", w.evaluate_method),
        "evaluate_value": float(w.evaluate_value) if w.evaluate_value else None,
        "evaluate_date": w.evaluate_date,
        "evaluate_explain": w.evaluate_explain,
        "evaluate_company": w.evaluate_company,
        "meeting_date": w.meeting_date,
        "storage_explain": w.storage_explain,
        "inquiry_date": w.inquiry_date,
        "inquiry_detail": w.inquiry_detail,
        "auction_date": w.auction_date,
        "listing_price": float(w.listing_price) if w.listing_price else None,
        "auction_remark": w.auction_remark,
        "transaction_date": w.transaction_date,
        "auction_amount": float(w.auction_amount) if w.auction_amount else None,
        "owner_names": [o["owner_name"] for o in owners],
        "created_by_name": user_names.get(w.created_by, ""),
        "created_at": w.created_at,
        "owners": owners,
        "storages": storage_items,
        "evaluates": evaluate_items,
    }
    # 按类型聚合扩展信息
    detail.update(ext_service.get_type_detail(db, warrant_id, ctx))
    return detail


# ===== 创建 / 修改 / 删除 =====

def create(db: Session, body: WarrantCreate, user_id: int) -> int:
    """创建权证：主表 + 按类型扩展 + 所有权人（单事务）。"""
    from app.warrant.services import ext_service

    dup = db.scalar(select(Warrant.id).where(Warrant.warrant_num == body.warrant_num))
    if dup is not None:
        raise BizError(4091, "权证编号已存在")

    wtype = WarrantType(body.warrant_type)
    if wtype == WarrantType.HYPOTHEC:
        raise BizError(4001, "他权类型随合同模块（M3）开放")

    # 扩展信息必填校验（type=1 必须有 houses[≥1]，其余 OneToOne 必须有对应对象）
    ext_field = TYPE_EXT_FIELD[wtype]
    ext_value = getattr(body, ext_field)
    if not ext_value:
        raise BizError(4001, f"该类型必须提供扩展信息: {ext_field}")
    if wtype == WarrantType.HOUSE and not body.houses:
        raise BizError(4001, "房产类型至少提供一套房产")
    if wtype == WarrantType.GROUND and not body.grounds:
        raise BizError(4001, "土地类型至少提供一宗土地")
    if wtype == WarrantType.CONSTRUCTION and not body.constructions:
        raise BizError(4001, "在建工程类型至少提供一项在建工程")

    w = Warrant(warrant_num=body.warrant_num, warrant_type=body.warrant_type, created_by=user_id)
    db.add(w)
    db.flush()

    ext_service.create_ext(db, w.id, wtype, body, user_id)
    _add_owners(db, w.id, body.owners, user_id)
    return w.id


def _add_owners(db: Session, warrant_id: int, owners, user_id: int) -> None:
    for o in owners:
        if db.get(Customer, o.owner_id) is None:
            raise BizError(4041, f"所有权人客户 {o.owner_id} 不存在")
        dup = db.scalar(
            select(WarrantOwnership.id).where(
                WarrantOwnership.warrant_id == warrant_id,
                WarrantOwnership.owner_id == o.owner_id,
            )
        )
        if dup is not None:
            raise BizError(4091, "同一权证同一所有权人不重复添加")
        db.add(
            WarrantOwnership(
                warrant_id=warrant_id, ownership_num=o.ownership_num,
                owner_id=o.owner_id, share_ratio=o.share_ratio, created_by=user_id,
            )
        )


def update(db: Session, warrant_id: int, body: WarrantUpdate, ctx: AuthContext) -> None:
    w = _get_warrant_with_scope(db, warrant_id, ctx)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(w, k, v)


def delete(db: Session, warrant_id: int, ctx: AuthContext) -> None:
    """删除拦截：已入库 / 已绑定项目（M3）。

    TODO(M3)：项目绑定表 article_warrant_bindings 落地后，在此处补：
        若该权证已绑定任何项目（article_warrant_bindings），拒绝删除并提示先解绑。
    """
    w = _get_warrant_with_scope(db, warrant_id, ctx)
    if w.warrant_state not in (WarrantState.NOT_STORED, WarrantState.CANCELLED):
        raise BizError(4091, "权证已入库或已流转，不可删除，请走注销流程")
    # DB FK ondelete=CASCADE 自动清理全部子表（ownership/house/ground/.../evaluate/storage）
    db.delete(w)


# ===== 出入库（联动主表状态）=====

def add_storage(db: Session, warrant_id: int, body: StorageCreate, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant_with_scope(db, warrant_id, ctx)
    s = WarrantStorage(
        warrant_id=warrant_id,
        storage_type=body.storage_type,
        storage_explain=body.storage_explain,
        transfer_id=body.transfer_id,
        conservator_id=user_id,
        storage_date=body.storage_date,
    )
    db.add(s)
    db.flush()
    _apply_state(db, w, body.storage_type)
    return s.id


def _apply_state(db: Session, w: Warrant, storage_type: int) -> None:
    """出入库联动主表状态（设计 §3.5）。"""
    new_state = STORAGE_STATE_MAP.get(StorageType(storage_type))
    if new_state is not None:
        w.warrant_state = new_state


# ===== 评估（联动主表最新评估）=====

def add_evaluate(db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant_with_scope(db, warrant_id, ctx)
    e = WarrantEvaluate(
        warrant_id=warrant_id, **body.model_dump(), created_by=user_id
    )
    db.add(e)
    db.flush()
    # 联动主表最新评估字段
    w.evaluate_method = body.evaluate_method
    w.evaluate_value = body.evaluate_value
    w.evaluate_date = body.evaluate_date
    w.evaluate_explain = body.evaluate_explain
    w.evaluate_company = body.evaluate_company
    return e.id


def add_recheck(db: Session, warrant_id: int, evaluate_id: int, body, user_id: int, ctx: AuthContext) -> int:
    _get_warrant_with_scope(db, warrant_id, ctx)
    e = db.get(WarrantEvaluate, evaluate_id)
    if e is None or e.warrant_id != warrant_id:
        raise BizError(4041, "评估记录不存在")
    existing = db.scalar(
        select(WarrantEvaluateRecheck.id).where(
            WarrantEvaluateRecheck.evaluate_id == evaluate_id
        )
    )
    if existing is not None:
        raise BizError(4091, "该评估已有复核记录")
    r = WarrantEvaluateRecheck(
        evaluate_id=evaluate_id, **body.model_dump(), created_by=user_id
    )
    db.add(r)
    db.flush()
    return r.id


# ===== 批量操作 =====

def batch_storage(db: Session, warrant_ids: list[int], body, user_id: int, ctx: AuthContext) -> int:
    """批量出入库：全部成功或全部回滚（调用方事务）。"""
    count = 0
    for wid in warrant_ids:
        w = _get_warrant_with_scope(db, wid, ctx)
        db.add(
            WarrantStorage(
                warrant_id=wid,
                storage_type=body.storage_type,
                storage_explain=body.storage_explain,
                transfer_id=body.transfer_id,
                conservator_id=user_id,
                storage_date=body.storage_date,
            )
        )
        _apply_state(db, w, body.storage_type)
        count += 1
    return count


def batch_transfer(db: Session, warrant_ids: list[int], to_conservator_id: int, reason: str, user_id: int, ctx: AuthContext) -> int:
    """批量移交（权证管理岗变更 + 移交记录 + 状态联动）。"""
    from app.user.models import User

    if db.get(User, to_conservator_id) is None:
        raise BizError(4041, "接收权证管理岗用户不存在")
    from datetime import date

    today = date.today()
    for wid in warrant_ids:
        w = _get_warrant_with_scope(db, wid, ctx)
        db.add(
            WarrantStorage(
                warrant_id=wid,
                storage_type=StorageType.TRANSFER,
                storage_explain=f"批量移交：{reason}",
                transfer_id=to_conservator_id,
                conservator_id=user_id,
                storage_date=today,
            )
        )
        w.warrant_state = WarrantState.TRANSFERRED
    return len(warrant_ids)


def batch_cancel(db: Session, warrant_ids: list[int], reason: str, user_id: int, ctx: AuthContext) -> int:
    """批量注销：状态置已注销 + 写注销出入库记录。"""
    from datetime import date

    today = date.today()
    for wid in warrant_ids:
        w = _get_warrant_with_scope(db, wid, ctx)
        if w.warrant_state == WarrantState.CANCELLED:
            raise BizError(4091, f"权证 {w.warrant_num} 已注销")
        w.warrant_state = WarrantState.CANCELLED
        w.storage_explain = f"批量注销：{reason}"
        db.add(
            WarrantStorage(
                warrant_id=wid,
                storage_type=StorageType.CANCELLED,
                storage_explain=f"批量注销：{reason}",
                conservator_id=user_id,
                storage_date=today,
            )
        )
    return len(warrant_ids)


# ===== 统计 =====

def stats_overview(db: Session) -> dict:
    total = db.scalar(select(func.count(Warrant.id))) or 0
    by_type_rows = db.execute(
        select(Warrant.warrant_type, func.count()).group_by(Warrant.warrant_type)
    ).all()
    by_state_rows = db.execute(
        select(Warrant.warrant_state, func.count()).group_by(Warrant.warrant_state)
    ).all()
    value_sum = db.scalar(
        select(func.coalesce(func.sum(Warrant.evaluate_value), 0))
    )
    auction_count = db.scalar(
        select(func.count(Warrant.id)).where(Warrant.auction_state.not_in([10, 990]))
    ) or 0
    return {
        "total_count": total,
        "by_type": {_disp("warrant_type", t): n for t, n in by_type_rows},
        "by_state": {_disp("warrant_state", s): n for s, n in by_state_rows},
        "total_evaluate_value": float(value_sum or 0),
        "auction_count": auction_count,
    }


def stats_by_customer(db: Session, customer_id: int) -> dict:
    """指定客户名下权证汇总（客户详情聚合用）。"""
    if db.get(Customer, customer_id) is None:
        raise BizError(4041, "客户不存在")
    stmt = select(Warrant.id).join(
        WarrantOwnership, WarrantOwnership.warrant_id == Warrant.id
    ).where(WarrantOwnership.owner_id == customer_id)
    wids = list(db.scalars(stmt))
    result: dict = {"total_count": len(wids), "by_type": {}, "total_evaluate_value": 0.0}
    if not wids:
        return result
    by_type = db.execute(
        select(Warrant.warrant_type, func.count())
        .where(Warrant.id.in_(wids))
        .group_by(Warrant.warrant_type)
    ).all()
    value_sum = db.scalar(
        select(func.coalesce(func.sum(Warrant.evaluate_value), 0)).where(
            Warrant.id.in_(wids)
        )
    )
    result["by_type"] = {_disp("warrant_type", t): n for t, n in by_type}
    result["total_evaluate_value"] = float(value_sum or 0)
    return result


# ===== 评估公司字典 =====

def list_evaluate_companies(db: Session) -> list[dict]:
    rows = db.scalars(select(WarrantEvaluateCompany).order_by(WarrantEvaluateCompany.id)).all()
    return [{"id": r.id, "name": r.name} for r in rows]


def create_evaluate_company(db: Session, name: str, user_id: int) -> int:
    dup = db.scalar(
        select(WarrantEvaluateCompany.id).where(WarrantEvaluateCompany.name == name)
    )
    if dup is not None:
        raise BizError(4091, "评估公司已存在")
    c = WarrantEvaluateCompany(name=name, created_by=user_id)
    db.add(c)
    db.flush()
    return c.id


def delete_evaluate_company(db: Session, company_id: int) -> None:
    """删除拦截：已被评估记录引用。"""
    c = db.get(WarrantEvaluateCompany, company_id)
    if c is None:
        raise BizError(4041, "评估公司不存在")
    used = db.scalar(
        select(WarrantEvaluate.id).where(WarrantEvaluate.evaluate_company == c.name).limit(1)
    )
    if used is not None:
        raise BizError(4091, "评估公司已被评估记录引用，不可删除")
    db.delete(c)
