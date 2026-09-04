"""权证模块审批 executor：注册到 APPLY_EXECUTORS，审批通过时原子应用。

解保出库通过 → 写 WarrantStorage(storage_type=310) + 联动 warrant_state → RELEASED。
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
    storage_date = payload.get("storage_date")  # str "YYYY-MM-DD"

    # 执行出库：写 WarrantStorage + 联动 warrant_state
    db.add(
        WarrantStorage(
            warrant_id=w.id,
            storage_type=StorageType.RELEASE_OUT.value,
            storage_explain=payload.get("storage_explain"),
            conservator_id=instance.submitted_by,  # 发起人为当前 conservator
            storage_date=storage_date,
        )
    )
    w.warrant_state = WarrantState.RELEASED.value


# ============ 注册到审批引擎 ============

register_executor("warrant_release_out", apply_release_out)
