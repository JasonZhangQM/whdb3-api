"""审批模块业务枚举。"""

from enum import IntEnum


class FlowStatus(IntEnum):
    ENABLED = 10
    DISABLED = 20


class InstanceStatus(IntEnum):
    PENDING = 10   # 审批中
    APPROVED = 20  # 已通过
    REJECTED = 30  # 已驳回
    WITHDRAWN = 40  # 已撤回


class TaskStatus(IntEnum):
    PENDING = 10   # 待审批
    APPROVED = 20  # 已同意
    REJECTED = 30  # 已驳回
    SKIPPED = 40   # 已跳过（节点被或签通过/条件跳过）
    CANCELLED = 50  # 因实例终结而取消


class ApproveAction(IntEnum):
    APPROVE = 10
    REJECT = 20


class ApproverScope(IntEnum):
    """审批人解析范围：提交人所在部门的指定角色。"""

    DEPT_ROLE = 10   # 提交人本部门中拥有指定角色的用户
    SUBMITTER_LEADER = 20  # 提交人部门负责人


LABELS: dict[str, dict[int, str]] = {
    "flow_status": {10: "启用", 20: "停用"},
    "instance_status": {10: "审批中", 20: "已通过", 30: "已驳回", 40: "已撤回"},
    "task_status": {10: "待审批", 20: "已同意", 30: "已驳回", 40: "已跳过", 50: "已取消"},
    "approve_action": {10: "同意", 20: "驳回"},
    "instance_status_display": {
        10: "审批中", 20: "已通过", 30: "已驳回", 40: "已撤回",
    },
}
