"""产权人 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.models import Warrant, WarrantOwnership
from app.warrant.schemas import OwnershipCreate, OwnershipUpdate

def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


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
    # autoflush=False：需显式 flush 让挂起记录对后续查询可见
    db.flush()
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


# ===== 房产/土地/在建工程 独立 CRUD =====

