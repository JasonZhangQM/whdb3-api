"""展期草稿 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.enums import WarrantType
from app.warrant.models import Warrant, WarrantDraftExtend
from app.warrant.schemas import DraftExtendCreate, DraftExtendUpdate

def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    # 延迟导入避免与 warrant_service 的循环依赖
    from app.warrant.services.warrant_service import _get_warrant_with_scope
    if ctx is not None:
        return _get_warrant_with_scope(db, warrant_id, ctx)
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


def list_draft_extends(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    """票据明细列表（关联核心企业/承兑人名称）。"""
    # 延迟导入避免与 warrant_service 的循环依赖
    from app.warrant.services.warrant_service import _disp
    _get_warrant(db, warrant_id, ctx)
    rows = db.execute(
        select(WarrantDraftExtend, Customer.name)
        .join(Customer, Customer.id == WarrantDraftExtend.acceptor_id)
        .where(WarrantDraftExtend.warrant_id == warrant_id)
        .order_by(WarrantDraftExtend.id)
    ).all()
    # 核心企业名二次批量取（避免 join 两别名复杂化）
    core_ids = {r.core_id for r, _ in rows}
    core_names = {}
    if core_ids:
        core_names = dict(
            db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(core_ids))
            ).all()
        )
    items = [
        {
            "id": r.id,
            "draft_type": r.draft_type,
            "draft_type_display": _disp("draft_type", r.draft_type),
            "draft_num": r.draft_num,
            "acceptor_id": r.acceptor_id,
            "acceptor_name": aname,
            "core_id": r.core_id,
            "core_name": core_names.get(r.core_id, ""),
            "draft_amount": float(r.draft_amount),
            "issue_date": r.issue_date,
            "due_date": r.due_date,
            "draft_state": r.draft_state,
            "draft_state_display": _disp("draft_state", r.draft_state),
        }
        for r, aname in rows
    ]
    return {"items": items}


def add_draft_extend(db: Session, warrant_id: int, body: DraftExtendCreate, user_id: int, ctx: AuthContext) -> int:
    """添加票据明细（校验：承兑人/核心企业存在、票据号唯一）。"""
    w = _get_warrant(db, warrant_id, ctx)
    if WarrantType(w.warrant_type) != WarrantType.DRAFT:
        raise BizError(4001, "仅票据类型权证可添加票据明细")

    acceptor = db.get(Customer, body.acceptor_id)
    if acceptor is None:
        raise BizError(4041, "承兑人客户不存在")
    core = db.get(Customer, body.core_id)
    if core is None:
        raise BizError(4041, "核心企业客户不存在")
    if body.due_date < body.issue_date:
        raise BizError(4001, "到期日不能早于出票日")
    dup = db.scalar(
        select(WarrantDraftExtend.id).where(WarrantDraftExtend.draft_num == body.draft_num)
    )
    if dup is not None:
        raise BizError(4091, "票据编号已存在")

    e = WarrantDraftExtend(warrant_id=warrant_id, **body.model_dump(), created_by=user_id)
    db.add(e)
    db.flush()
    return e.id


def update_draft_extend(
    db: Session, warrant_id: int, extend_id: int, body: DraftExtendUpdate, user_id: int, ctx: AuthContext
) -> None:
    _get_warrant(db, warrant_id, ctx)
    e = _get_draft_extend(db, warrant_id, extend_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(e, k, v)
    e.updated_by = user_id


def delete_draft_extend(db: Session, warrant_id: int, extend_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    db.query(WarrantDraftExtend).filter(WarrantDraftExtend.id == extend_id).delete(
        synchronize_session=False
    )


def _get_draft_extend(db: Session, warrant_id: int, extend_id: int) -> WarrantDraftExtend:
    e = db.get(WarrantDraftExtend, extend_id)
    if e is None or e.warrant_id != warrant_id:
        raise BizError(4041, "票据明细不存在")
    return e

