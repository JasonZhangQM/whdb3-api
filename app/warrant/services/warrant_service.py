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
# 票据(31)/应收(11)明细已直连 warrants，创建时无必填扩展对象，不在此映射
TYPE_EXT_FIELD = {
    WarrantType.HOUSE: "houses",
    WarrantType.GROUND: "grounds",
    WarrantType.CONSTRUCTION: "constructions",
    WarrantType.STOCK: "stock",
    WarrantType.VEHICLE: "vehicle",
    WarrantType.CHATTEL: "chattel",
    WarrantType.OTHER: "other",
}


# ---------- 子模块 re-export（按 AGENTS.md §2.2 拆分到独立 service）----------
from .warrant_evaluate_service import (
    list_evaluates, add_evaluate, add_recheck,
    list_evaluate_companies, create_evaluate_company, delete_evaluate_company,
)  # noqa: F402,E402
from .warrant_storage_service import (
    list_storages, add_storage,
)  # noqa: F402,E402

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


def warrant_dict(
    db: Session,
    q: str | None = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[dict], int]:
    """权证下拉字典（表单选择用）。无 data_scope——业务模块（如项目担保措施）
    选抵质押权证时需要看到全量权证，不应被 created_by 归属过滤。
    """
    stmt = select(Warrant.id, Warrant.warrant_num, Warrant.warrant_type)
    if q:
        stmt = stmt.where(Warrant.warrant_num.like(f"%{q.strip()}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(Warrant.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {"id": wid, "warrant_num": wnum, "warrant_type": wtype}
        for wid, wnum, wtype in rows
    ]
    return items, total


def list_warrants(
    db: Session,
    ctx: AuthContext,
    page: int,
    page_size: int,
    warrant_type: int | None = None,
    warrant_state: int | None = None,
    owner_id: int | None = None,
    q: str | None = None,
) -> tuple[list[dict], int]:
    stmt = select(Warrant).order_by(Warrant.id.desc())
    # 数据级权限：按创建者过滤（设计 §4：本人在 created_by / 部门 / 全部）
    stmt = apply_data_scope_filter(db, stmt, ctx, owner_field="created_by")

    if warrant_type is not None:
        stmt = stmt.where(Warrant.warrant_type == warrant_type)
    if warrant_state is not None:
        stmt = stmt.where(Warrant.warrant_state == warrant_state)
    if q:
        stmt = stmt.where(Warrant.warrant_num.like(f"%{q}%"))
    if owner_id is not None:
        stmt = stmt.join(WarrantOwnership, WarrantOwnership.warrant_id == Warrant.id).where(
            WarrantOwnership.owner_id == owner_id
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    # 批量取所有权人名称（避免 N+1）
    wids = [w.id for w in rows]
    owner_map = _owner_names_map(db, wids)
    user_names = _user_names(db, {w.created_by for w in rows})

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
                "owner_names": owner_map.get(w.id, []),
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



def get_detail(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    from app.warrant.services import warrant_type_detail_service

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
        "remark": w.remark,
        "warrant_state": w.warrant_state,
        "warrant_state_display": _disp("warrant_state", w.warrant_state),
        "owner_names": [o["owner_name"] for o in owners],
        "created_by_name": user_names.get(w.created_by, ""),
        "created_at": w.created_at,
        "owners": owners,
        "storages": storage_items,
        "evaluates": evaluate_items,
    }
    # 按类型聚合扩展信息
    detail.update(warrant_type_detail_service.get_type_detail(db, warrant_id, ctx))
    return detail


# ===== 创建 / 修改 / 删除 =====


def create(db: Session, body: WarrantCreate, user_id: int) -> int:
    """创建权证：主表 + 按类型扩展 + 所有权人（单事务）。"""
    from app.warrant.services import warrant_type_detail_service

    dup = db.scalar(select(Warrant.id).where(Warrant.warrant_num == body.warrant_num))
    if dup is not None:
        raise BizError(4091, "权证编号已存在")

    wtype = WarrantType(body.warrant_type)
    if wtype == WarrantType.HYPOTHEC:
        raise BizError(4001, "他权类型随合同模块（M3）开放")

    # 扩展信息必填校验（type=1 必须有 houses[≥1]，其余 OneToOne 必须有对应对象）
    # 票据/应收无必填扩展对象（明细可为空，走独立明细接口），跳过
    ext_field = TYPE_EXT_FIELD.get(wtype)
    if ext_field and not getattr(body, ext_field):
        raise BizError(4001, f"该类型必须提供扩展信息: {ext_field}")
    if wtype == WarrantType.HOUSE and not body.houses:
        raise BizError(4001, "房产类型至少提供一套房产")
    if wtype == WarrantType.GROUND and not body.grounds:
        raise BizError(4001, "土地类型至少提供一宗土地")
    if wtype == WarrantType.CONSTRUCTION and not body.constructions:
        raise BizError(4001, "在建工程类型至少提供一项在建工程")

    w = Warrant(warrant_num=body.warrant_num, warrant_type=body.warrant_type, remark=body.remark, created_by=user_id)
    db.add(w)
    db.flush()

    warrant_type_detail_service.create_ext(db, w.id, wtype, body, user_id)
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

# 需要审批的出库类型集合——直接调 add_storage / batch_storage 会被拦截
_APPROVAL_REQUIRED_TYPES = frozenset([
    StorageType.RENEW_OUT.value,   # 续抵出库
    StorageType.LEND_OUT.value,    # 借出
    StorageType.RELEASE_OUT.value, # 解保出库（主场景）
])
_APPROVAL_REQUIRED_HINT = {
    StorageType.RELEASE_OUT.value: "请走解保审批流程",
    StorageType.LEND_OUT.value: "请走权证借出审批流程",
    StorageType.RENEW_OUT.value: "续抵出库需审批，请联系管理员",
}



def batch_storage(db: Session, warrant_ids: list[int], body, user_id: int, ctx: AuthContext) -> int:
    """批量出入库：全部成功或全部回滚（调用方事务）。"""
    if body.storage_type in _APPROVAL_REQUIRED_TYPES:
        raise BizError(4091, _APPROVAL_REQUIRED_HINT.get(body.storage_type, "该出库类型需审批"))
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


# ===== 审批对接 =====


def submit_release_out_request(
    db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext
) -> int:
    """发起解保出库审批。

    前置校验：
    1. 权证存在 + 数据级权限
    2. warrant_state ∈ {STORED=20, GUARDED=30}（已入库/已加保才允许解保）
    3. 审批引擎内置互斥（同一 warrant 同时只允许 1 个 pending 实例）
    """
    from app.approval.services.engine_service import submit as approval_submit

    w = _get_warrant_with_scope(db, warrant_id, ctx)
    if w.warrant_state not in (WarrantState.STORED.value, WarrantState.GUARDED.value):
        raise BizError(
            4031,
            f"当前权证状态为「{_disp('warrant_state', w.warrant_state)}」，仅已入库/已加保可发起解保审批",
        )

    payload = {
        "storage_type": StorageType.RELEASE_OUT.value,
        "storage_explain": body.storage_explain,
        "storage_date": str(body.storage_date),
    }
    instance_id = approval_submit(
        db,
        flow_code="warrant_release_out",
        biz_type="warrant",
        biz_id=warrant_id,
        payload=payload,
        summary=f"权证 {w.warrant_num} 发起解保出库",
        submitted_by=user_id,
    )
    db.commit()
    return instance_id



def get_release_out_pending(db: Session, warrant_id: int) -> dict | None:
    """查询权证当前是否有 pending 的解保出库审批实例。

    返回简易信息供前端展示待审状态；无 pending 实例返回 None。
    """
    from app.approval.models import ApprovalInstance
    from app.approval.enums import InstanceStatus

    stmt = select(ApprovalInstance).where(
        ApprovalInstance.flow_code == "warrant_release_out",
        ApprovalInstance.biz_type == "warrant",
        ApprovalInstance.biz_id == warrant_id,
        ApprovalInstance.status == InstanceStatus.PENDING,
    )
    inst = db.scalar(stmt)
    if inst is None:
        return None
    return {
        "instance_id": inst.id,
        "flow_code": inst.flow_code,
        "status": inst.status,
        "current_step": inst.current_step,
        "submitted_at": inst.submitted_at,
    }



def submit_lend_out_request(
    db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext
) -> int:
    """发起权证借出审批。

    前置校验：
    1. 权证存在 + 数据级权限
    2. warrant_state ∈ {STORED=20, GUARDED=30}（已入库/已加保才允许借出）
    3. 审批引擎内置互斥
    """
    from app.approval.services.engine_service import submit as approval_submit

    w = _get_warrant_with_scope(db, warrant_id, ctx)
    if w.warrant_state not in (WarrantState.STORED.value, WarrantState.GUARDED.value):
        raise BizError(
            4031,
            f"当前权证状态为「{_disp('warrant_state', w.warrant_state)}」，仅已入库/已加保可发起借出审批",
        )

    payload = {
        "storage_type": StorageType.LEND_OUT.value,
        "storage_explain": body.storage_explain,
        "storage_date": str(body.storage_date),
    }
    instance_id = approval_submit(
        db,
        flow_code="warrant_lend_out",
        biz_type="warrant",
        biz_id=warrant_id,
        payload=payload,
        summary=f"权证 {w.warrant_num} 发起借出审批",
        submitted_by=user_id,
    )
    db.commit()
    return instance_id



def get_lend_out_pending(db: Session, warrant_id: int) -> dict | None:
    """查询权证当前是否有 pending 的借出审批实例。"""
    from app.approval.models import ApprovalInstance
    from app.approval.enums import InstanceStatus

    stmt = select(ApprovalInstance).where(
        ApprovalInstance.flow_code == "warrant_lend_out",
        ApprovalInstance.biz_type == "warrant",
        ApprovalInstance.biz_id == warrant_id,
        ApprovalInstance.status == InstanceStatus.PENDING,
    )
    inst = db.scalar(stmt)
    if inst is None:
        return None
    return {
        "instance_id": inst.id,
        "flow_code": inst.flow_code,
        "status": inst.status,
        "current_step": inst.current_step,
        "submitted_at": inst.submitted_at,
    }


# ===== 统计 =====


def stats_overview(db: Session) -> dict:
    total = db.scalar(select(func.count(Warrant.id))) or 0
    by_type_rows = db.execute(
        select(Warrant.warrant_type, func.count()).group_by(Warrant.warrant_type)
    ).all()
    by_state_rows = db.execute(
        select(Warrant.warrant_state, func.count()).group_by(Warrant.warrant_state)
    ).all()
    # 评估总值从 WarrantEvaluate 子表按 warrant_id 取最新一条的 evaluate_value
    # 简单方案：sum 所有 evaluate_value（后续如需"最新值"可改为窗口函数取 rn=1）
    value_sum = db.scalar(
        select(func.coalesce(func.sum(WarrantEvaluate.evaluate_value), 0))
    )
    return {
        "total_count": total,
        "by_type": {_disp("warrant_type", t): n for t, n in by_type_rows},
        "by_state": {_disp("warrant_state", s): n for s, n in by_state_rows},
        "total_evaluate_value": float(value_sum or 0),
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
        select(func.coalesce(func.sum(WarrantEvaluate.evaluate_value), 0)).where(
            WarrantEvaluate.warrant_id.in_(wids)
        )
    )
    result["by_type"] = {_disp("warrant_type", t): n for t, n in by_type}
    result["total_evaluate_value"] = float(value_sum or 0)
    return result


# ===== 评估公司字典 =====

