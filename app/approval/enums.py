"""审批模块业务枚举（LabeledIntEnum 自带中文 label，一处定义零双维护）。"""

from app.core.enums import LabeledIntEnum, make_labels


class FlowStatus(LabeledIntEnum):
    ENABLED = 10, '启用'
    DISABLED = 20, '停用'


class InstanceStatus(LabeledIntEnum):
    PENDING = 10, '审批中'
    APPROVED = 20, '已通过'
    REJECTED = 30, '已驳回'
    WITHDRAWN = 40, '已撤回'


class TaskStatus(LabeledIntEnum):
    PENDING = 10, '待审批'
    APPROVED = 20, '已同意'
    REJECTED = 30, '已驳回'
    SKIPPED = 40, '已跳过（节点被或签通过/条件跳过）'
    CANCELLED = 50, '因实例终结而取消'


class ApproveAction(LabeledIntEnum):
    APPROVE = 10, '同意'
    REJECT = 20, '驳回'


class ApproverScope(LabeledIntEnum):
    """审批人解析范围：提交人所在部门的指定角色。"""

    DEPT_ROLE = 10, '提交人本部门中拥有指定角色的用户'
    SUBMITTER_LEADER = 20, '提交人部门负责人'


# instance_status_display 是接口专用的冗余 key，从 InstanceStatus 派生
LABELS = make_labels(FlowStatus, InstanceStatus, TaskStatus, ApproveAction, ApproverScope)
LABELS["instance_status_display"] = LABELS["instance_status"]
