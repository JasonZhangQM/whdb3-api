"""审批中心路由：我的申请 / 待我审批 / 审批动作 / 撤回 / 实例详情。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.approval.enums import LABELS
from app.approval.schemas import ApproveReq, WithdrawReq
from app.approval import services as approval_service
from app.core.deps import AuthContext, get_current_user
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result

router = APIRouter(prefix="/approvals", tags=["approval"])


def _serialize_row(row) -> dict:
    """列表行 (instance, flow_name, submitter_name) -> dict。"""
    inst, flow_name, submitter_name = row
    return {
        "id": inst.id,
        "flow_code": inst.flow_code,
        "flow_name": flow_name,
        "biz_type": inst.biz_type,
        "biz_id": inst.biz_id,
        "summary": inst.summary,
        "status": inst.status,
        "status_display": LABELS["instance_status"].get(inst.status, str(inst.status)),
        "current_step": inst.current_step,
        "current_node_name": None,  # 列表层不查节点名，详情接口返回
        "submitted_by_name": submitter_name,
        "submitted_at": inst.submitted_at,
        "finished_at": inst.finished_at,
    }


@router.get("/my-submitted")
def my_submitted(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    rows, total = approval_service.list_my_submitted(db, user.user_id, page, page_size)
    return page_result([_serialize_row(r) for r in rows], total, page, page_size)


@router.get("/my-tasks")
def my_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    rows, total = approval_service.list_my_tasks(db, user.user_id, page, page_size)
    items = []
    for inst, flow_name, submitter_name, task_id in rows:
        item = _serialize_row((inst, flow_name, submitter_name))
        item["current_task_id"] = task_id
        items.append(item)
    return page_result(items, total, page, page_size)


@router.post("/tasks/{task_id}/act")
def act_task(
    task_id: int,
    body: ApproveReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    approval_service.act(db, task_id, body.action, body.opinion, user.user_id)
    db.commit()
    return ok(message="审批完成")


@router.post("/instances/{instance_id}/withdraw")
def withdraw_instance(
    instance_id: int,
    body: WithdrawReq,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    approval_service.withdraw(db, instance_id, user.user_id, body.reason)
    db.commit()
    return ok(message="已撤回")


@router.get("/instances/{instance_id}")
def instance_detail(
    instance_id: int,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    inst = approval_service.get_instance_detail(db, instance_id, user.user_id)
    from sqlalchemy import select

    from app.approval.models import ApprovalTask
    from app.user.models import User

    task_rows = db.execute(
        select(ApprovalTask, User.name)
        .join(User, User.id == ApprovalTask.approver_id)
        .where(ApprovalTask.instance_id == instance_id)
        .order_by(ApprovalTask.step, ApprovalTask.id)
    ).all()
    tasks = [
        {
            "id": t.id,
            "step": t.step,
            "node_name": t.node_name,
            "approver_name": approver_name,
            "status": t.status,
            "status_display": LABELS["task_status"].get(t.status, str(t.status)),
            "opinion": t.opinion,
            "acted_at": t.acted_at,
        }
        for t, approver_name in task_rows
    ]
    return ok(
        {
            "id": inst.id,
            "flow_code": inst.flow_code,
            "biz_type": inst.biz_type,
            "biz_id": inst.biz_id,
            "payload": inst.payload,
            "summary": inst.summary,
            "status": inst.status,
            "status_display": LABELS["instance_status"].get(
                inst.status, str(inst.status)
            ),
            "current_step": inst.current_step,
            "submitted_by": inst.submitted_by,
            "submitted_at": inst.submitted_at,
            "finished_at": inst.finished_at,
            "tasks": tasks,
        }
    )
