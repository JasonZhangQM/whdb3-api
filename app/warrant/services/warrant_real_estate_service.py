"""不动产类 service（房产/土地/在建工程）。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.enums import WarrantType
from app.warrant.models import Warrant, WarrantHouse, WarrantGround, WarrantConstruction

def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


def add_house(db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant(db, warrant_id, ctx)
    if w.warrant_type != WarrantType.HOUSE:
        raise BizError(4001, "该权证不是房产类型")
    row = WarrantHouse(warrant_id=warrant_id, **body.model_dump(), created_by=user_id)
    db.add(row)
    db.flush()
    return row.id


def delete_house(db: Session, warrant_id: int, house_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    row = db.get(WarrantHouse, house_id)
    if row is None or row.warrant_id != warrant_id:
        raise BizError(4041, "房产记录不存在")
    db.delete(row)


def add_ground(db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant(db, warrant_id, ctx)
    if w.warrant_type != WarrantType.GROUND:
        raise BizError(4001, "该权证不是土地类型")
    row = WarrantGround(warrant_id=warrant_id, **body.model_dump(), created_by=user_id)
    db.add(row)
    db.flush()
    return row.id


def delete_ground(db: Session, warrant_id: int, ground_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    row = db.get(WarrantGround, ground_id)
    if row is None or row.warrant_id != warrant_id:
        raise BizError(4041, "土地记录不存在")
    db.delete(row)


def add_construction(db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext) -> int:
    w = _get_warrant(db, warrant_id, ctx)
    if w.warrant_type != WarrantType.CONSTRUCTION:
        raise BizError(4001, "该权证不是在建工程类型")
    row = WarrantConstruction(warrant_id=warrant_id, **body.model_dump(), created_by=user_id)
    db.add(row)
    db.flush()
    return row.id


def delete_construction(db: Session, warrant_id: int, construction_id: int, ctx: AuthContext) -> None:
    _get_warrant(db, warrant_id, ctx)
    row = db.get(WarrantConstruction, construction_id)
    if row is None or row.warrant_id != warrant_id:
        raise BizError(4041, "在建工程记录不存在")
    db.delete(row)
def _ground_dict(g: WarrantGround, region_name: str | None = None) -> dict:
    return {
        "region_id": g.region_id,
        "region_name": region_name,
        "ground_locate": g.ground_locate,
        "ground_app": g.ground_app,
        "ground_area": float(g.ground_area),
    }


# ===== 更新（整体替换式）=====

