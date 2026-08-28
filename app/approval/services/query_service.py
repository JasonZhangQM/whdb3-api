"""审批引擎读链路：我的申请 / 待我审批 / 实例详情 / 互斥判断。"""

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.approval.enums import InstanceStatus, TaskStatus
from app.approval.models import (
    ApprovalFlowDef,
    ApprovalInstance,
    ApprovalTask,
)
from app.core.exceptions import BizError


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
