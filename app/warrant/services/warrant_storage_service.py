"""权证存储 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.user.models import User
from app.warrant.enums import LABELS, StorageType, WarrantState
from app.warrant.models import Warrant, WarrantStorage
from app.warrant.schemas import (StorageCreate)


def _get_or_404(db: Session, warrant_id: int) -> Warrant:
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


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

def add_storage(db: Session, warrant_id: int, body: StorageCreate, user_id: int, ctx: AuthContext) -> int:
    # 拦截需要审批的出库类型，提示走对应审批流程
    if body.storage_type in _APPROVAL_REQUIRED_TYPES:
        raise BizError(4091, _APPROVAL_REQUIRED_HINT.get(body.storage_type, "该出库类型需审批"))
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
