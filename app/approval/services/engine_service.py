"""审批引擎写链路：提交 / 审批 / 撤回 / executor 注册表。

设计要点：
- executor 注册表实现依赖反转：APPLY_EXECUTORS[flow_code] 由业务模块注册，
  approval 永不 import 业务模块（R4）。
- 审批同意在单事务内"实例置通过 + executor 应用"原子完成。
- 互斥规则：同一 (biz_type, biz_id) 同时只允许一个 pending 实例。
- 或签节点：任一审批人同意即推进；驳回即整单驳回。
"""

import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approval.enums import ApproveAction, InstanceStatus, TaskStatus
from app.approval.models import (
    ApprovalFlowDef,
    ApprovalFlowNode,
    ApprovalInstance,
    ApprovalTask,
)
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

# executor 注册表：flow_code -> 审批通过后的生效函数 (db, instance) -> None
# 业务模块在 services/executors.py 中调用 register_executor 注册（R4 依赖反转）
ApplyExecutor = Callable[[Session, ApprovalInstance], None]
APPLY_EXECUTORS: dict[str, ApplyExecutor] = {}


def register_executor(flow_code: str, func: ApplyExecutor) -> None:
    """业务模块注册 flow_code 的生效函数（幂等覆盖，供应用重载）。"""
    APPLY_EXECUTORS[flow_code] = func


def _get_flow(db: Session, flow_code: str) -> tuple[ApprovalFlowDef, list[ApprovalFlowNode]]:
    """取启用中的流程定义及其节点（按 step 排序）。"""
    flow = db.scalar(
        select(ApprovalFlowDef).where(
            ApprovalFlowDef.code == flow_code,
            ApprovalFlowDef.status == 10,
        )
    )
    if flow is None:
        raise BizError(4041, f"审批流程未定义或未启用: {flow_code}")
    nodes = list(
        db.scalars(
            select(ApprovalFlowNode)
            .where(ApprovalFlowNode.flow_def_id == flow.id)
            .order_by(ApprovalFlowNode.step)
        )
    )
    if not nodes:
        raise BizError(5001, f"审批流程无节点: {flow_code}")
    return flow, nodes


def _resolve_approvers(db: Session, node: ApprovalFlowNode, submitted_by: int) -> list[int]:
    """解析节点审批人，按 approver_scope 分派：

    scope=10 DEPT_ROLE：提交人本部门中拥有指定角色的用户（排除提交人自己）。
    scope=20 SUBMITTER_LEADER：提交人所在部门的负责人（Department.leader_user_id）。
    """
    from app.approval.enums import ApproverScope
    from app.user.models import Department, Role, User, UserRole

    submitter = db.get(User, submitted_by)
    if submitter is None or submitter.dept_id is None:
        raise BizError(4001, "提交人无部门归属，无法解析审批人")

    if node.approver_scope == ApproverScope.SUBMITTER_LEADER:
        # scope=20：取提交人部门负责人
        dept = db.get(Department, submitter.dept_id)
        if dept is None or dept.leader_user_id is None:
            raise BizError(
                4091,
                f"节点「{node.name}」审批人解析失败：部门「{dept.name if dept else submitter.dept_id}」未设置负责人",
            )
        if dept.leader_user_id == submitted_by:
            raise BizError(
                4091,
                f"节点「{node.name}」审批人无效：提交人即部门负责人，自审不可跳过（skip_condition 未实现）",
            )
        leader = db.get(User, dept.leader_user_id)
        if leader is None or leader.status != 10:
            raise BizError(
                4091,
                f"节点「{node.name}」部门负责人已离职或停用，请联系管理员",
            )
        return [leader.id]

    if node.approver_scope == ApproverScope.GLOBAL_ROLE:
        # scope=30：全局找指定角色的用户（不限部门，排除提交人）
        stmt = (
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.status == 10,
                Role.code == node.approver_role_code,
                User.id != submitted_by,
            )
            .distinct()
        )
        approvers = list(db.scalars(stmt))
        if not approvers:
            raise BizError(
                4091,
                f"节点「{node.name}」无可用审批人（需全局角色 {node.approver_role_code}）",
            )
        return approvers

    # scope=10 默认：本部门角色匹配
    stmt = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.dept_id == submitter.dept_id,
            User.status == 10,
            Role.code == node.approver_role_code,
            User.id != submitted_by,  # 提交人自审无意义，排除
        )
        .distinct()
    )
    approvers = list(db.scalars(stmt))
    if not approvers:
        raise BizError(
            4091,
            f"节点「{node.name}」无可用的审批人"
            f"（需本部门角色 {node.approver_role_code}），请联系管理员",
        )
    return approvers


def _check_pending_mutex(db: Session, biz_type: str, biz_id: int | None) -> None:
    """互斥：同一业务对象存在 pending 实例则拒绝新提交。"""
    stmt = select(ApprovalInstance.id).where(
        ApprovalInstance.biz_type == biz_type,
        ApprovalInstance.biz_id == biz_id,
        ApprovalInstance.status == InstanceStatus.PENDING,
    )
    if db.scalar(stmt) is not None:
        raise BizError(4091, "该对象存在待审流程，不可重复提交")


def submit(
    db: Session,
    flow_code: str,
    biz_type: str,
    biz_id: int | None,
    payload: dict,
    summary: str,
    submitted_by: int,
) -> int:
    """提交审批：校验互斥 → 创建实例 → 生成首 stage 所有节点的任务（stage 内节点并行）。

    事务边界：调用方（service 层）以 with db.begin() 包裹。
    """
    _check_pending_mutex(db, biz_type, biz_id)
    flow, nodes = _get_flow(db, flow_code)

    first_stage = min(n.stage for n in nodes)
    first_stage_nodes = [n for n in nodes if n.stage == first_stage]

    instance = ApprovalInstance(
        flow_code=flow_code,
        biz_type=biz_type,
        biz_id=biz_id,
        payload=payload,
        summary=summary,
        status=InstanceStatus.PENDING,
        current_step=first_stage_nodes[0].step,
        current_stage=first_stage,
        submitted_by=submitted_by,
    )
    db.add(instance)
    db.flush()  # 取 instance.id

    # 首 stage 所有节点同时生成任务
    for node in first_stage_nodes:
        _create_tasks_for_node(db, instance, node)
    return instance.id


def _create_tasks_for_node(
    db: Session, instance: ApprovalInstance, node: ApprovalFlowNode
) -> None:
    """为单个节点生成审批任务（或签：每人一条任务，任一同意即推进节点）。"""
    approvers = _resolve_approvers(db, node, instance.submitted_by)
    for approver_id in approvers:
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                step=node.step,
                stage=node.stage,
                node_name=node.name,
                approver_id=approver_id,
                status=TaskStatus.PENDING,
            )
        )
    db.flush()


def _is_stage_complete(db: Session, instance_id: int, stage: int) -> bool:
    """判断某个 stage 的所有节点是否都已通过（APPROVED/SKIPPED/CANCELLED）。

    即：该 stage 下没有任何 PENDING 状态的任务。
    """
    pending = db.query(ApprovalTask).filter(
        ApprovalTask.instance_id == instance_id,
        ApprovalTask.stage == stage,
        ApprovalTask.status == TaskStatus.PENDING,
    ).first()
    return pending is None


def _skip_pending_tasks_in_stage(
    db: Session, instance_id: int, stage: int, except_step: int | None = None
) -> None:
    """驳回时：把某个 stage 所有 PENDING 任务置 CANCELLED。"""
    stmt = select(ApprovalTask).where(
        ApprovalTask.instance_id == instance_id,
        ApprovalTask.stage == stage,
        ApprovalTask.status == TaskStatus.PENDING,
    )
    if except_step is not None:
        stmt = stmt.where(ApprovalTask.step != except_step)
    for t in db.scalars(stmt):
        t.status = TaskStatus.CANCELLED


def _finish_stage_and_advance(
    db: Session, instance: ApprovalInstance, flow_code: str
) -> None:
    """当前 stage 全部完成 → 推进到下一 stage（或末节点 executor）。"""
    _, nodes = _get_flow(db, flow_code)
    current_stage_nodes = [n for n in nodes if n.stage == instance.current_stage]
    next_stage = instance.current_stage + 1
    next_stage_nodes = [n for n in nodes if n.stage == next_stage]

    if not next_stage_nodes:
        # 所有 stage 完成 → 实例通过 + executor 应用
        _finish(db, instance, InstanceStatus.APPROVED)
        executor = APPLY_EXECUTORS.get(flow_code)
        if executor is None:
            raise BizError(5001, f"流程 {flow_code} 未注册生效函数")
        executor(db, instance)
        logger.info(
            "approval applied: flow=%s instance=%s biz=%s/%s",
            flow_code, instance.id, instance.biz_type, instance.biz_id,
        )
    else:
        # 推进到下一 stage，同时生成下一 stage 的所有节点任务
        instance.current_stage = next_stage
        instance.current_step = min(n.step for n in next_stage_nodes)
        for node in next_stage_nodes:
            _create_tasks_for_node(db, instance, node)


def act(
    db: Session,
    task_id: int,
    action: int,
    opinion: str | None,
    operator_id: int,
) -> None:
    """审批动作：同意 / 驳回。

    同意：
      同 stage 内同 step（同节点）多审批人——或签，本人同意即节点通过，
      该 step 其余 PENDING 置 SKIPPED；
      然后检查整个 stage 是否完成（所有节点都通过/跳过/取消），
      完成则推进到下一 stage（生成下一 stage 所有节点任务）；
      否则等待 stage 内其他并行节点的审批。
    驳回：整单驳回，当前 stage 所有 PENDING 任务置 CANCELLED。
    """
    task = db.get(ApprovalTask, task_id)
    if task is None or task.approver_id != operator_id:
        raise BizError(4041, "审批任务不存在或无权操作")
    if task.status != TaskStatus.PENDING:
        raise BizError(4091, "该任务已处理")

    instance = db.get(ApprovalInstance, task.instance_id)
    if instance is None or instance.status != InstanceStatus.PENDING:
        raise BizError(4091, "该审批实例已终结")

    now = datetime.now()
    task.acted_at = now

    if action == ApproveAction.REJECT:
        # 驳回：整单驳回，当前 stage 所有 PENDING 置 CANCELLED
        task.status = TaskStatus.REJECTED
        task.opinion = opinion
        for t in db.query(ApprovalTask).filter(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.status == TaskStatus.PENDING,
        ):
            t.status = TaskStatus.CANCELLED
        _finish(db, instance, InstanceStatus.REJECTED)
        return

    # 同意：或签——同 step 其余 PENDING 置 SKIPPED（排除自己正在操作的 task）
    task.status = TaskStatus.APPROVED
    task.opinion = opinion
    _skip_pending_tasks_except(db, instance.id, task.step, except_task_id=task.id)

    # 先 flush 再查！避免 SQLAlchemy identity map 返回内存里已修改的对象
    db.flush()

    # 检查当前 stage 是否全部完成（所有节点都无 PENDING 了）
    if _is_stage_complete(db, instance.id, task.stage):
        _finish_stage_and_advance(db, instance, instance.flow_code)
    # 否则 stage 内还有其他并行节点未完成，等待


def withdraw(db: Session, instance_id: int, operator_id: int, reason: str | None) -> None:
    """提交人撤回（仅 pending 状态可撤）。"""
    instance = db.get(ApprovalInstance, instance_id)
    if instance is None:
        raise BizError(4041, "审批实例不存在")
    if instance.submitted_by != operator_id:
        raise BizError(4031, "仅提交人可撤回")
    if instance.status != InstanceStatus.PENDING:
        raise BizError(4091, "仅审批中的实例可撤回")

    if reason:
        instance.summary = f"{instance.summary}（撤回：{reason}）"
    _finish(db, instance, InstanceStatus.WITHDRAWN)


def _finish(db: Session, instance: ApprovalInstance, status: InstanceStatus) -> None:
    """实例终结：置状态/时间，未决任务全部取消。"""
    instance.status = status
    instance.finished_at = datetime.now()
    tasks = db.scalars(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.status == TaskStatus.PENDING,
        )
    )
    for t in tasks:
        t.status = TaskStatus.CANCELLED


def _skip_pending_tasks_except(
    db: Session, instance_id: int, step: int, except_task_id: int | None = None
) -> None:
    """或签节点通过后，跳过同节点其余待审任务（排除 operator 自己操作的 task id）。"""
    stmt = select(ApprovalTask).where(
        ApprovalTask.instance_id == instance_id,
        ApprovalTask.step == step,
        ApprovalTask.status == TaskStatus.PENDING,
    )
    if except_task_id is not None:
        stmt = stmt.where(ApprovalTask.id != except_task_id)
    for t in db.scalars(stmt):
        t.status = TaskStatus.SKIPPED
