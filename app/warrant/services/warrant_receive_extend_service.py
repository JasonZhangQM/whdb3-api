"""已接收展期 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.enums import WarrantType
from app.warrant.models import Warrant, WarrantReceiveExtend
from app.warrant.schemas import ReceiveExtendCreate, ReceiveExtendUpdate

def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


def list_receive_extends(db: Session, warrant_id: int, ctx: AuthContext) -> dict:
    _get_warrant(db, warrant_id, ctx)
    rows = db.scalars(
        select(WarrantReceiveExtend)
        .where(WarrantReceiveExtend.warrant_id == warrant_id)
        .order_by(WarrantReceiveExtend.id)
    ).all()
    return {
        "items": [{"id": r.id, "receive_unit": r.receive_unit} for r in rows]
    }


def add_receive_extend(db: Session, warrant_id: int, body: ReceiveExtendCreate, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant(db, warrant_id, ctx)
    if WarrantType(w.warrant_type) != WarrantType.RECEIVABLE:
        raise BizError(4001, "仅应收账款类型权证可添加应收单位")
    dup = db.scalar(
        select(WarrantReceiveExtend.id).where(
            WarrantReceiveExtend.warrant_id == warrant_id,
            WarrantReceiveExtend.receive_unit == body.receive_unit,
        )
    )
    if dup is not None:
        raise BizError(4091, "该应收单位已存在")
    e = WarrantReceiveExtend(
        warrant_id=warrant_id, receive_unit=body.receive_unit, created_by=user_id
    )
    db.add(e)
    db.flush()
    return e.id


def delete_receive_extend(db: Session, warrant_id: int, extend_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    e = db.get(WarrantReceiveExtend, extend_id)
    if e is None or e.warrant_id != warrant_id:
        raise BizError(4041, "应收单位不存在")
    db.delete(e)


def update_receive_extend(
    db: Session, warrant_id: int, extend_id: int, body: ReceiveExtendUpdate, ctx: AuthContext
) -> None:
    """修改应收单位（校验同权证下名称不重复）。"""
    _get_warrant(db, warrant_id, ctx)
    e = db.get(WarrantReceiveExtend, extend_id)
    if e is None or e.warrant_id != warrant_id:
        raise BizError(4041, "应收单位不存在")
    dup = db.scalar(
        select(WarrantReceiveExtend.id).where(
            WarrantReceiveExtend.warrant_id == warrant_id,
            WarrantReceiveExtend.receive_unit == body.receive_unit,
            WarrantReceiveExtend.id != extend_id,
        )
    )
    if dup is not None:
        raise BizError(4091, "同权证下已存在同名应收单位")
    e.receive_unit = body.receive_unit


# ===== 所有权人 =====

