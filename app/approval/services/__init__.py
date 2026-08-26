"""审批引擎核心服务。

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

from sqlalchemy import Select, and_, func, select
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
    """解析节点审批人：提交人本部门中拥有指定角色的用户（排除提交人自己）。"""
    # approval(L1) -> user(L1) 同层引用；局部 import 保持模块顶层干净
    from app.user.models import Role, User, UserRole

    submitter = db.get(User, submitted_by)
    if submitter is None or submitter.dept_id is None:
        raise BizError(4001, "提交人无部门归属，无法解析审批人")

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
    """提交审批：校验互斥 → 创建实例 → 解析首节点审批人 → 生成任务。

    事务边界：调用方（service 层）以 with db.begin() 包裹。
    """
    _check_pending_mutex(db, biz_type, biz_id)
    flow, nodes = _get_flow(db, flow_code)

    instance = ApprovalInstance(
        flow_code=flow_code,
        biz_type=biz_type,
        biz_id=biz_id,
        payload=payload,
        summary=summary,
        status=InstanceStatus.PENDING,
        current_step=nodes[0].step,
        submitted_by=submitted_by,
    )
    db.add(instance)
    db.flush()  # 取 instance.id

    _create_tasks_for_step(db, instance, nodes[0])
    return instance.id


def _create_tasks_for_step(
    db: Session, instance: ApprovalInstance, node: ApprovalFlowNode
) -> None:
    """为节点生成审批任务（或签：每人一条任务，任一同意即推进）。"""
    approvers = _resolve_approvers(db, node, instance.submitted_by)
    for approver_id in approvers:
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                step=node.step,
                node_name=node.name,
                approver_id=approver_id,
                status=TaskStatus.PENDING,
            )
        )
    db.flush()


def act(
    db: Session,
    task_id: int,
    action: int,
    opinion: str | None,
    operator_id: int,
) -> None:
    """审批动作：同意（或签推进）/ 驳回（整单驳回）。

    同意且为末节点时，单事务内调用 executor 应用生效。
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
        task.status = TaskStatus.REJECTED
        task.opinion = opinion
        _finish(db, instance, InstanceStatus.REJECTED)
        return

    # 同意：或签——本人同意即节点通过，其余任务置跳过
    task.status = TaskStatus.APPROVED
    task.opinion = opinion
    _skip_pending_tasks(db, instance.id, task.step)

    _, nodes = _get_flow(db, instance.flow_code)
    current = next(n for n in nodes if n.step == task.step)
    next_nodes = [n for n in nodes if n.step > task.step]

    if next_nodes:
        # 推进到下一节点
        nxt = next_nodes[0]
        instance.current_step = nxt.step
        _create_tasks_for_step(db, instance, nxt)
    else:
        # 末节点通过：实例置通过 + executor 应用（同一事务，原子生效）
        _finish(db, instance, InstanceStatus.APPROVED)
        executor = APPLY_EXECUTORS.get(instance.flow_code)
        if executor is None:
            # 未注册 executor 属配置错误：回滚整个事务，避免"通过但未生效"
            raise BizError(5001, f"流程 {instance.flow_code} 未注册生效函数")
        executor(db, instance)
        logger.info(
            "approval applied: flow=%s instance=%s biz=%s/%s",
            instance.flow_code, instance.id, instance.biz_type, instance.biz_id,
        )


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


def _skip_pending_tasks(db: Session, instance_id: int, step: int) -> None:
    """或签节点通过后，跳过同节点其余待审任务。"""
    tasks = db.scalars(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == instance_id,
            ApprovalTask.step == step,
            ApprovalTask.status == TaskStatus.PENDING,
        )
    )
    for t in tasks:
        t.status = TaskStatus.SKIPPED


# ===== 查询（我的申请 / 待我审批 / 实例详情）=====

def list_my_submitted(
    db: Session, user_id: int, page: int, page_size: int
) -> tuple[list, int]:
    stmt = _instance_list_stmt().where(ApprovalInstance.submitted_by == user_id)
    return _paginate_instances(db, stmt, page, page_size)


def list_my_tasks(
    db: Session, user_id: int, page: int, page_size: int
) -> tuple[list, int]:
    """待我审批：pending 实例中我的 pending 任务（当前节点）。

    返回行 (instance, flow_name, submitter_name, task_id)。
    """
    stmt = (
        _instance_list_stmt()
        .join(ApprovalTask, ApprovalTask.instance_id == ApprovalInstance.id)
        .where(
            ApprovalTask.approver_id == user_id,
            ApprovalTask.status == TaskStatus.PENDING,
            ApprovalInstance.status == InstanceStatus.PENDING,
        )
        .add_columns(ApprovalTask.id.label("task_id"))
    )
    sub = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def get_instance_detail(db: Session, instance_id: int, user_id: int) -> ApprovalInstance:
    """实例详情：提交人或审批参与者可见。"""
    instance = db.get(ApprovalInstance, instance_id)
    if instance is None:
        raise BizError(4041, "审批实例不存在")
    participated = db.scalar(
        select(ApprovalTask.id).where(
            ApprovalTask.instance_id == instance_id,
            ApprovalTask.approver_id == user_id,
        )
    )
    if instance.submitted_by != user_id and participated is None:
        raise BizError(4031, "无权查看该审批实例")
    return instance


def _instance_list_stmt() -> Select:
    from app.user.models import User

    return (
        select(ApprovalInstance, ApprovalFlowDef.name, User.name)
        .join(ApprovalFlowDef, ApprovalFlowDef.code == ApprovalInstance.flow_code)
        .join(User, User.id == ApprovalInstance.submitted_by)
        .order_by(ApprovalInstance.submitted_at.desc())
    )


def _paginate_instances(
    db: Session, stmt: Select, page: int, page_size: int
) -> tuple[list, int]:
    sub = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def has_pending_instance(db: Session, biz_type: str, biz_id: int) -> bool:
    """供业务模块判断对象是否处于待审状态（如客户删除拦截）。"""
    stmt = select(ApprovalInstance.id).where(
        and_(
            ApprovalInstance.biz_type == biz_type,
            ApprovalInstance.biz_id == biz_id,
            ApprovalInstance.status == InstanceStatus.PENDING,
        )
    )
    return db.scalar(stmt) is not None
