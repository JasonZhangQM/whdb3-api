"""审批模块 Schemas。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InstanceListItem(BaseModel):
    """我的申请 / 待我审批列表项。"""

    id: int
    flow_code: str
    flow_name: str
    biz_type: str
    biz_id: int | None
    summary: str
    status: int
    status_display: str
    current_step: int
    current_node_name: str | None
    submitted_by_name: str
    submitted_at: datetime
    finished_at: datetime | None


class InstanceDetail(InstanceListItem):
    """审批实例详情（含 payload 与任务轨迹）。"""

    payload: dict[str, Any]
    tasks: list["TaskItem"]


class TaskItem(BaseModel):
    id: int
    step: int
    node_name: str
    approver_name: str
    status: int
    status_display: str
    opinion: str | None
    acted_at: datetime | None


class ApproveReq(BaseModel):
    """审批动作（同意/驳回）。"""

    action: Literal[10, 20]  # 10同意 20驳回
    opinion: str | None = Field(None, max_length=500)


class WithdrawReq(BaseModel):
    reason: str | None = Field(None, max_length=500)


class SubmitResult(BaseModel):
    instance_id: int
    message: str
