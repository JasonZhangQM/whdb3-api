"""权证按类型分发的详情 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.enums import WarrantType
from app.warrant.models import (
    Warrant, WarrantHouse, WarrantGround, WarrantConstruction,
    WarrantReceiveExtend, WarrantDraftExtend, WarrantStock,
    WarrantVehicle, WarrantChattel, WarrantOther, WarrantPatent,
    WarrantSoftware,
)
from app.warrant.schemas import TypeDetailUpdate

def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    # 延迟导入避免与 warrant_service 的循环依赖
    from app.warrant.services.warrant_service import _get_warrant_with_scope, _get_or_404
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
        for g in body.grounds:
            db.add(WarrantGround(warrant_id=warrant_id, **g.model_dump(), created_by=user_id))
    elif wtype == WarrantType.CONSTRUCTION:
        for c in body.constructions:
            db.add(WarrantConstruction(warrant_id=warrant_id, **c.model_dump(), created_by=user_id))
    elif wtype == WarrantType.RECEIVABLE:
        # 应收明细直连 warrants（无中间表），创建时单位可为空
        for unit in body.receive_units:
            db.add(
                WarrantReceiveExtend(
                    warrant_id=warrant_id, receive_unit=unit, created_by=user_id
                )
            )
    elif wtype == WarrantType.DRAFT:
        for d in body.draft_extends:
            db.add(
                WarrantDraftExtend(
                    warrant_id=warrant_id, **d.model_dump(), created_by=user_id
                )
            )
    elif wtype == WarrantType.STOCK:
        s = body.stock
        db.add(WarrantStock(warrant_id=warrant_id, **s.model_dump(), created_by=user_id))
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
    from app.warrant.services.warrant_service import _disp
    from app.warrant.services.warrant_real_estate_service import _ground_dict
    """按权证类型聚合扩展信息（详情页 type-detail 块）。"""
    w = _get_warrant(db, warrant_id, ctx)
    wtype = WarrantType(w.warrant_type)
    # 统一默认值：数组 -> []，对象 -> None，保证前端访问安全
    result: dict = {
        "houses": [],
        "ground": None,
        "construction": None,
        "receive_units": [],
        "stock": None,
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
        rows = db.execute(
            select(WarrantGround, Region.name.label("region_name"))
            .outerjoin(Region, Region.id == WarrantGround.region_id)
            .where(WarrantGround.warrant_id == warrant_id)
            .order_by(WarrantGround.id)
        ).all()
        result["grounds"] = [_ground_dict(g, region_name) for g, region_name in rows]
    elif wtype == WarrantType.CONSTRUCTION:
        from app.user.models import Region
        rows = db.execute(
            select(WarrantConstruction, Region.name.label("region_name"))
            .outerjoin(Region, Region.id == WarrantConstruction.region_id)
            .where(WarrantConstruction.warrant_id == warrant_id)
            .order_by(WarrantConstruction.id)
        ).all()
        result["constructions"] = [
            {
                "id": c.id,
                "region_id": c.region_id,
                "region_name": region_name,
                "construct_locate": c.construct_locate,
                "construct_app": c.construct_app,
                "construct_area": float(c.construct_area),
            }
            for c, region_name in rows
        ]
    elif wtype == WarrantType.RECEIVABLE:
        units = db.scalars(
            select(WarrantReceiveExtend)
            .where(WarrantReceiveExtend.warrant_id == warrant_id)
            .order_by(WarrantReceiveExtend.id)
        ).all()
        # 带 id 供详情页删除操作使用
        result["receive_units"] = [
            {"id": u.id, "receive_unit": u.receive_unit} for u in units
        ]
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
        # 延迟导入避免与票据明细 service 的循环依赖
        from app.warrant.services.warrant_draft_extend_service import list_draft_extends
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


def update_type_detail(db: Session, warrant_id: int, body: TypeDetailUpdate, user_id: int, ctx: AuthContext) -> None:
    """按类型整体替换扩展信息：先清旧再写新（调用方包事务）。"""
    from app.warrant.services.warrant_service import TYPE_EXT_FIELD

    w = _get_warrant(db, warrant_id, ctx)
    wtype = WarrantType(w.warrant_type)
    ext_field = TYPE_EXT_FIELD.get(wtype)
    if ext_field is None:
        # 票据/应收明细已直连 warrants，扩展信息走独立明细接口，整体替换无意义
        return
    ext = getattr(body, ext_field)
    if ext is None:
        raise BizError(4001, f"必须提供该类型的扩展信息字段: {ext_field}")

    _delete_ext(db, warrant_id, wtype)
    create_ext(db, warrant_id, wtype, body, user_id)


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
        db.query(WarrantReceiveExtend).filter(
            WarrantReceiveExtend.warrant_id == warrant_id
        ).delete(synchronize_session=False)
    elif wtype == WarrantType.STOCK:
        db.query(WarrantStock).filter(WarrantStock.warrant_id == warrant_id).delete(
            synchronize_session=False
        )
    elif wtype == WarrantType.DRAFT:
        db.query(WarrantDraftExtend).filter(
            WarrantDraftExtend.warrant_id == warrant_id
        ).delete(synchronize_session=False)
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

