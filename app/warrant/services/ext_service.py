"""权证类型扩展信息服务：按类型创建/读取/整体替换扩展表。

11 种类型 OneToOne（房产 1:N 房产包模式），票据/应收另有明细子表。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.enums import LABELS, WarrantType
from app.warrant.models import (
    Warrant,
    WarrantChattel,
    WarrantConstruction,
    WarrantDraft,
    WarrantDraftExtend,
    WarrantGround,
    WarrantHouse,
    WarrantOther,
    WarrantOwnership,
    WarrantPatent,
    WarrantReceivable,
    WarrantReceiveExtend,
    WarrantSoftware,
    WarrantStock,
    WarrantVehicle,
)
from app.warrant.schemas import (
    DraftExtendCreate,
    DraftExtendUpdate,
    OwnershipCreate,
    OwnershipUpdate,
    ReceiveExtendCreate,
    TypeDetailUpdate,
)
from app.warrant.services.warrant_service import _disp, _get_or_404, _get_warrant_with_scope


def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    if ctx is not None:
        return _get_warrant_with_scope(db, warrant_id, ctx)
    return _get_or_404(db, warrant_id)


# ===== 创建（创建权证时由 warrant_service.create 调用）=====

def create_ext(db: Session, warrant_id: int, wtype: WarrantType, body, user_id: int) -> None:
    """按类型创建扩展信息（调用方包事务）。"""
    if wtype == WarrantType.HOUSE:
        for house in body.houses:
            _add_house(db, warrant_id, house, user_id)
    elif wtype == WarrantType.GROUND:
        g = body.ground
        db.add(WarrantGround(warrant_id=warrant_id, **g.model_dump(), created_by=user_id))
    elif wtype == WarrantType.CONSTRUCTION:
        c = body.construction
        db.add(WarrantConstruction(warrant_id=warrant_id, **c.model_dump(), created_by=user_id))
    elif wtype == WarrantType.RECEIVABLE:
        r = body.receivable
        recv = WarrantReceivable(
            warrant_id=warrant_id,
            receivable_detail=r.receivable_detail,
            created_by=user_id,
        )
        db.add(recv)
        db.flush()
        for unit in r.receive_units:
            db.add(
                WarrantReceiveExtend(
                    receivable_id=recv.id, receive_unit=unit, created_by=user_id
                )
            )
    elif wtype == WarrantType.STOCK:
        s = body.stock
        db.add(WarrantStock(warrant_id=warrant_id, **s.model_dump(), created_by=user_id))
    elif wtype == WarrantType.DRAFT:
        d = body.draft
        draft = WarrantDraft(warrant_id=warrant_id, **d.model_dump(), created_by=user_id)
        db.add(draft)
    elif wtype == WarrantType.VEHICLE:
        v = body.vehicle
        db.add(WarrantVehicle(warrant_id=warrant_id, **v.model_dump(), created_by=user_id))
    elif wtype == WarrantType.CHATTEL:
        c = body.chattel
        db.add(WarrantChattel(warrant_id=warrant_id, **c.model_dump(), created_by=user_id))
    elif wtype == WarrantType.OTHER:
        o = body.other
        other = WarrantOther(
            warrant_id=warrant_id,
            other_type=o.other_type,
            cost=o.cost,
            other_detail=o.other_detail,
            created_by=user_id,
        )
        db.add(other)
        db.flush()
        # 商标 / 软著 OneToOne 子表
        if o.patent is not None:
            db.add(
                WarrantPatent(other_id=other.id, **o.patent.model_dump(), created_by=user_id)
            )
        if o.software is not None:
            db.add(
                WarrantSoftware(other_id=other.id, **o.software.model_dump(), created_by=user_id)
            )


def _add_house(db: Session, warrant_id: int, house, user_id: int) -> None:
    """添加一套房产。

    注意：坐落不做全局重复检查——同一坐落的房产换证后会产生多套证，
    产权证编号（warrant_ownerships.ownership_num）才是唯一键。
    """
    db.add(WarrantHouse(warrant_id=warrant_id, **house.model_dump(), created_by=user_id))


# ===== 详情聚合（按类型返回扩展块）=====

def get_type_detail(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    """按权证类型聚合扩展信息（详情页 type-detail 块）。"""
    w = _get_warrant(db, warrant_id, ctx)
    wtype = WarrantType(w.warrant_type)
    # 统一默认值：数组 -> []，对象 -> None，保证前端访问安全
    result: dict = {
        "houses": [],
        "ground": None,
        "construction": None,
        "receivable": None,
        "stock": None,
        "draft": None,
        "draft_extends": [],
        "vehicle": None,
        "chattel": None,
        "other": None,
    }

    if wtype == WarrantType.HOUSE:
        from app.user.models import Region
        houses = db.execute(
            select(WarrantHouse, Region.name.label("region_name"))
            .outerjoin(Region, Region.id == WarrantHouse.region_id)
            .where(WarrantHouse.warrant_id == warrant_id)
            .order_by(WarrantHouse.id)
        ).all()
        result["houses"] = [
            {
                "id": h.id,
                "region_id": h.region_id,
                "region_name": region_name,
                "house_locate": h.house_locate,
                "house_app": h.house_app,
                "house_area": float(h.house_area),
                "house_name": h.house_name,
                "house_build_year": h.house_build_year,
                "house_usage": h.house_usage,
                "house_usage_display": _disp("house_usage", h.house_usage),
            }
            for h, region_name in houses
        ]
    elif wtype == WarrantType.GROUND:
        from app.user.models import Region
        row = db.execute(
            select(WarrantGround, Region.name.label("region_name"))
            .outerjoin(Region, Region.id == WarrantGround.region_id)
            .where(WarrantGround.warrant_id == warrant_id)
        ).first()
        if row:
            g, region_name = row
            result["ground"] = _ground_dict(g, region_name)
        else:
            result["ground"] = None
    elif wtype == WarrantType.CONSTRUCTION:
        from app.user.models import Region
        row = db.execute(
            select(WarrantConstruction, Region.name.label("region_name"))
            .outerjoin(Region, Region.id == WarrantConstruction.region_id)
            .where(WarrantConstruction.warrant_id == warrant_id)
        ).first()
        if row:
            c, region_name = row
            result["construction"] = {
                "region_id": c.region_id,
                "region_name": region_name,
                "construct_locate": c.construct_locate,
                "construct_app": c.construct_app,
                "construct_area": float(c.construct_area),
            }
        else:
            result["construction"] = None
    elif wtype == WarrantType.RECEIVABLE:
        r = db.scalar(
            select(WarrantReceivable).where(WarrantReceivable.warrant_id == warrant_id)
        )
        if r:
            units = db.scalars(
                select(WarrantReceiveExtend)
                .where(WarrantReceiveExtend.receivable_id == r.id)
                .order_by(WarrantReceiveExtend.id)
            ).all()
            result["receivable"] = {
                "id": r.id,
                "receivable_detail": r.receivable_detail,
                "receive_units": [u.receive_unit for u in units],
            }
        else:
            result["receivable"] = None
    elif wtype == WarrantType.STOCK:
        s = db.scalar(select(WarrantStock).where(WarrantStock.warrant_id == warrant_id))
        result["stock"] = {
            "stock_type": s.stock_type,
            "stock_type_display": _disp("stock_type", s.stock_type),
            "target": s.target,
            "ratio": float(s.ratio),
            "registered_capital": float(s.registered_capital),
            "paid_capital": float(s.paid_capital),
            "remark": s.remark,
        } if s else None
    elif wtype == WarrantType.DRAFT:
        d = db.scalar(select(WarrantDraft).where(WarrantDraft.warrant_id == warrant_id))
        result["draft"] = {
            "id": d.id,
            "draft_type": d.draft_type,
            "draft_type_display": _disp("draft_main_type", d.draft_type),
            "denomination": float(d.denomination),
            "draft_detail": d.draft_detail,
        } if d else None
        result["draft_extends"] = list_draft_extends(db, warrant_id, ctx)["items"]
    elif wtype == WarrantType.VEHICLE:
        v = db.scalar(select(WarrantVehicle).where(WarrantVehicle.warrant_id == warrant_id))
        result["vehicle"] = {
            "frame_num": v.frame_num,
            "plate_num": v.plate_num,
            "vehicle_brand": v.vehicle_brand,
            "remark": v.remark,
        } if v else None
    elif wtype == WarrantType.CHATTEL:
        c = db.scalar(select(WarrantChattel).where(WarrantChattel.warrant_id == warrant_id))
        result["chattel"] = {
            "chattel_type": c.chattel_type,
            "chattel_type_display": _disp("chattel_type", c.chattel_type),
            "chattel_detail": c.chattel_detail,
        } if c else None
    elif wtype == WarrantType.OTHER:
        o = db.scalar(select(WarrantOther).where(WarrantOther.warrant_id == warrant_id))
        if o:
            patent = db.scalar(
                select(WarrantPatent).where(WarrantPatent.other_id == o.id)
            )
            software = db.scalar(
                select(WarrantSoftware).where(WarrantSoftware.other_id == o.id)
            )
            result["other"] = {
                "other_type": o.other_type,
                "other_type_display": _disp("other_type", o.other_type),
                "cost": float(o.cost),
                "other_detail": o.other_detail,
                "patent": {
                    "patent_name": patent.patent_name,
                    "reg_num": patent.reg_num,
                    "patent_ty": patent.patent_ty,
                } if patent else None,
                "software": {
                    "software_name": software.software_name,
                    "reg_num": software.reg_num,
                } if software else None,
            }
        else:
            result["other"] = None
    return result


def _ground_dict(g: WarrantGround, region_name: str | None = None) -> dict:
    return {
        "region_id": g.region_id,
        "region_name": region_name,
        "ground_locate": g.ground_locate,
        "ground_app": g.ground_app,
        "ground_area": float(g.ground_area),
    }


# ===== 更新（整体替换式）=====

def update_type_detail(db: Session, warrant_id: int, body: TypeDetailUpdate, user_id: int, ctx: AuthContext) -> None:
    """按类型整体替换扩展信息：先清旧再写新（调用方包事务）。"""
    from app.warrant.services.warrant_service import TYPE_EXT_FIELD

    w = _get_warrant(db, warrant_id, ctx)
    wtype = WarrantType(w.warrant_type)
    ext_field = TYPE_EXT_FIELD[wtype]
    ext = getattr(body, ext_field)
    if ext is None:
        raise BizError(4001, f"必须提供该类型的扩展信息字段: {ext_field}")

    _delete_ext(db, warrant_id, wtype)
    create_ext(db, warrant_id, wtype, body, user_id)


# _type_field 已合并到 warrant_service.TYPE_EXT_FIELD，ext_service 不再单独维护。


def _delete_ext(db: Session, warrant_id: int, wtype: WarrantType) -> None:
    """物理删除旧扩展（含明细子表，权证无软删设计）。"""
    if wtype == WarrantType.HOUSE:
        db.query(WarrantHouse).filter(WarrantHouse.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.GROUND:
        db.query(WarrantGround).filter(WarrantGround.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.CONSTRUCTION:
        db.query(WarrantConstruction).filter(
            WarrantConstruction.warrant_id == warrant_id
        ).delete(synchronize_session=False)
    elif wtype == WarrantType.RECEIVABLE:
        recv_ids = list(
            db.scalars(
                select(WarrantReceivable.id).where(WarrantReceivable.warrant_id == warrant_id)
            )
        )
        if recv_ids:
            db.query(WarrantReceiveExtend).filter(
                WarrantReceiveExtend.receivable_id.in_(recv_ids)
            ).delete(synchronize_session=False)
        db.query(WarrantReceivable).filter(
            WarrantReceivable.warrant_id == warrant_id
        ).delete(synchronize_session=False)
    elif wtype == WarrantType.STOCK:
        db.query(WarrantStock).filter(WarrantStock.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.DRAFT:
        draft_id = db.scalar(
            select(WarrantDraft.id).where(WarrantDraft.warrant_id == warrant_id)
        )
        if draft_id:
            db.query(WarrantDraftExtend).filter(
                WarrantDraftExtend.draft_id == draft_id
            ).delete(synchronize_session=False)
        db.query(WarrantDraft).filter(WarrantDraft.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.VEHICLE:
        db.query(WarrantVehicle).filter(WarrantVehicle.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.CHATTEL:
        db.query(WarrantChattel).filter(WarrantChattel.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.OTHER:
        other_id = db.scalar(
            select(WarrantOther.id).where(WarrantOther.warrant_id == warrant_id)
        )
        if other_id:
            db.query(WarrantPatent).filter(WarrantPatent.other_id == other_id).delete(
                synchronize_session=False
            )
            db.query(WarrantSoftware).filter(WarrantSoftware.other_id == other_id).delete(
                synchronize_session=False
            )
        db.query(WarrantOther).filter(WarrantOther.warrant_id == warrant_id).delete(
            synchronize_session=False
        )


# ===== 票据明细 =====

def list_draft_extends(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    """票据明细列表（关联核心企业/承兑人名称）。"""
    _get_warrant(db, warrant_id, ctx)
    draft_id = db.scalar(
        select(WarrantDraft.id).where(WarrantDraft.warrant_id == warrant_id)
    )
    if draft_id is None:
        return {"items": []}
    rows = db.execute(
        select(WarrantDraftExtend, Customer.name)
        .join(Customer, Customer.id == WarrantDraftExtend.acceptor_id)
        .where(WarrantDraftExtend.draft_id == draft_id)
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
            "draft_type_display": _disp("draft_detail_type", r.draft_type),
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
    """添加票据明细（校验：承兑人存在、核心企业 is_core、票据号唯一）。"""
    w = _get_warrant(db, warrant_id, ctx)
    if WarrantType(w.warrant_type) != WarrantType.DRAFT:
        raise BizError(4001, "仅票据类型权证可添加票据明细")
    draft_id = db.scalar(
        select(WarrantDraft.id).where(WarrantDraft.warrant_id == warrant_id)
    )
    if draft_id is None:
        raise BizError(4041, "票据扩展信息不存在")

    acceptor = db.get(Customer, body.acceptor_id)
    if acceptor is None:
        raise BizError(4041, "承兑人客户不存在")
    core = db.get(Customer, body.core_id)
    if core is None or not core.is_core:
        raise BizError(4001, "核心企业不存在或非核心企业")
    if body.due_date < body.issue_date:
        raise BizError(4001, "到期日不能早于出票日")
    dup = db.scalar(
        select(WarrantDraftExtend.id).where(WarrantDraftExtend.draft_num == body.draft_num)
    )
    if dup is not None:
        raise BizError(4091, "票据编号已存在")

    e = WarrantDraftExtend(draft_id=draft_id, **body.model_dump(), created_by=user_id)
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
    from app.warrant.models import WarrantDraftExtend as DE

    db.query(DE).filter(DE.id == extend_id).delete(synchronize_session=False)


def _get_draft_extend(db: Session, warrant_id: int, extend_id: int) -> WarrantDraftExtend:
    e = db.get(WarrantDraftExtend, extend_id)
    if e is None:
        raise BizError(4041, "票据明细不存在")
    draft_id = db.scalar(
        select(WarrantDraft.id).where(WarrantDraft.warrant_id == warrant_id)
    )
    if draft_id is None or e.draft_id != draft_id:
        raise BizError(4041, "票据明细不存在")
    return e


# ===== 应收明细 =====

def list_receive_extends(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    _get_warrant(db, warrant_id, ctx)
    recv_id = db.scalar(
        select(WarrantReceivable.id).where(WarrantReceivable.warrant_id == warrant_id)
    )
    if recv_id is None:
        return {"items": []}
    rows = db.scalars(
        select(WarrantReceiveExtend)
        .where(WarrantReceiveExtend.receivable_id == recv_id)
        .order_by(WarrantReceiveExtend.id)
    ).all()
    return {
        "items": [{"id": r.id, "receive_unit": r.receive_unit} for r in rows]
    }


def add_receive_extend(db: Session, warrant_id: int, body: ReceiveExtendCreate, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant(db, warrant_id, ctx)
    if WarrantType(w.warrant_type) != WarrantType.RECEIVABLE:
        raise BizError(4001, "仅应收账款类型权证可添加应收单位")
    recv_id = db.scalar(
        select(WarrantReceivable.id).where(WarrantReceivable.warrant_id == warrant_id)
    )
    if recv_id is None:
        raise BizError(4041, "应收扩展信息不存在")
    dup = db.scalar(
        select(WarrantReceiveExtend.id).where(
            WarrantReceiveExtend.receivable_id == recv_id,
            WarrantReceiveExtend.receive_unit == body.receive_unit,
        )
    )
    if dup is not None:
        raise BizError(4091, "该应收单位已存在")
    e = WarrantReceiveExtend(
        receivable_id=recv_id, receive_unit=body.receive_unit, created_by=user_id
    )
    db.add(e)
    db.flush()
    return e.id


def delete_receive_extend(db: Session, warrant_id: int, extend_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    e = db.get(WarrantReceiveExtend, extend_id)
    if e is None:
        raise BizError(4041, "应收单位不存在")
    recv_id = db.scalar(
        select(WarrantReceivable.id).where(WarrantReceivable.warrant_id == warrant_id)
    )
    if recv_id is None or e.receivable_id != recv_id:
        raise BizError(4041, "应收单位不存在")
    db.delete(e)


# ===== 所有权人 =====

def list_owners(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    _get_warrant(db, warrant_id, ctx)
    rows = db.execute(
        select(WarrantOwnership, Customer.name)
        .join(Customer, Customer.id == WarrantOwnership.owner_id)
        .where(WarrantOwnership.warrant_id == warrant_id)
        .order_by(WarrantOwnership.id)
    ).all()
    return {
        "items": [
            {
                "id": o.id,
                "ownership_num": o.ownership_num,
                "owner_id": o.owner_id,
                "owner_name": name,
                "share_ratio": float(o.share_ratio) if o.share_ratio is not None else None,
            }
            for o, name in rows
        ]
    }


def add_owner(db: Session, warrant_id: int, body: OwnershipCreate, user_id: int, ctx: AuthContext) -> int:
    from app.warrant.services import warrant_service

    _get_warrant(db, warrant_id, ctx)
    warrant_service._add_owners(db, warrant_id, [body], user_id)
    o = db.scalar(
        select(WarrantOwnership)
        .where(
            WarrantOwnership.warrant_id == warrant_id,
            WarrantOwnership.owner_id == body.owner_id,
        )
    )
    return o.id


def update_owner(db: Session, warrant_id: int, owner_row_id: int, body: OwnershipUpdate, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    o = _get_owner(db, warrant_id, owner_row_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(o, k, v)


def delete_owner(db: Session, warrant_id: int, owner_row_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    o = _get_owner(db, warrant_id, owner_row_id)
    db.delete(o)


def _get_owner(db: Session, warrant_id: int, owner_row_id: int) -> WarrantOwnership:
    o = db.get(WarrantOwnership, owner_row_id)
    if o is None or o.warrant_id != warrant_id:
        raise BizError(4041, "产权证记录不存在")
    return o
