"""权证模块审批 executor：注册到 APPLY_EXECUTORS，审批通过时原子应用。

- 解保出库通过 → 写 WarrantStorage(storage_type=310) + 联动 warrant_state → RELEASED。
- 权证借出通过 → 写 WarrantStorage(storage_type=110) + 联动 warrant_state → LENT。
"""

from sqlalchemy.orm import Session

from app.approval.services import register_executor
from app.core.exceptions import BizError
from app.warrant.enums import StorageType, WarrantState
from app.warrant.models import Warrant, WarrantStorage


def apply_release_out(db: Session, instance) -> None:
    """解保出库审批通过 → 写出入库记录 + 联动主表状态。"""
    w = db.get(Warrant, instance.biz_id)
    if w is None:
        raise BizError(4041, "权证不存在")

    payload = instance.payload or {}
    db.add(
        WarrantStorage(
            warrant_id=w.id,
            storage_type=StorageType.RELEASE_OUT.value,
            storage_explain=payload.get("storage_explain"),
            conservator_id=instance.submitted_by,
            storage_date=payload.get("storage_date"),
        )
    )
    w.warrant_state = WarrantState.RELEASED.value


def apply_lend_out(db: Session, instance) -> None:
    """权证借出审批通过 → 写出入库记录 + 联动主表状态 → LENT(210)。"""
    w = db.get(Warrant, instance.biz_id)
    if w is None:
        raise BizError(4041, "权证不存在")

    payload = instance.payload or {}
    db.add(
        WarrantStorage(
            warrant_id=w.id,
            storage_type=StorageType.LEND_OUT.value,
            storage_explain=payload.get("storage_explain"),
            conservator_id=instance.submitted_by,
            storage_date=payload.get("storage_date"),
        )
    )
    w.warrant_state = WarrantState.LENT.value


# ============ 注册到审批引擎 ============

register_executor("warrant_release_out", apply_release_out)
register_executor("warrant_lend_out", apply_lend_out)
