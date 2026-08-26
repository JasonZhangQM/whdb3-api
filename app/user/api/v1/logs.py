"""日志审计路由：操作日志 + 登录日志（接口文档 §1 组7）。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import AuthContext, require_perm
from app.core.response import ok
from app.core.response import page as page_result
from app.user.schemas.log import LoginLogItem, OperationLogDetail
from app.user.services import org_service

router = APIRouter(tags=["日志审计"])


@router.get("/operation-logs")
def list_operation_logs(page: int = 1, page_size: int = 20,
                        module: str | None = None,
                        username: str | None = None,
                        target_id: int | None = None,
                        start_time: datetime | None = None,
                        end_time: datetime | None = None,
                        ctx: AuthContext = Depends(require_perm("log:operation")),
                        db: Session = Depends(get_db)):
    """操作日志列表（筛选：模块/操作人/时间/对象）。"""
    logs, total = org_service.list_operation_logs(
        db, page, page_size, module=module, username=username,
        target_id=target_id, start_time=start_time, end_time=end_time,
    )
    items = [OperationLogDetail(
        id=l.id, user_id=l.user_id, username=l.username, user_name=l.user_name,
        module=l.module, action=l.action, target_type=l.target_type,
        target_id=l.target_id, target_name=l.target_name, method=l.method,
        path=l.path, ip=l.ip, status=l.status, message=l.message,
        created_at=l.created_at,
        before_data=l.before_data, after_data=l.after_data, diff=l.diff,
    ).model_dump(mode="json") for l in logs]
    return page_result(items, total, page, page_size)


@router.get("/operation-logs/{log_id}")
def get_operation_log(log_id: int,
                      ctx: AuthContext = Depends(require_perm("log:operation")),
                      db: Session = Depends(get_db)):
    """日志详情（before/after/diff 对比）。"""
    l = org_service.get_operation_log(db, log_id)
    return ok(OperationLogDetail(
        id=l.id, user_id=l.user_id, username=l.username, user_name=l.user_name,
        module=l.module, action=l.action, target_type=l.target_type,
        target_id=l.target_id, target_name=l.target_name, method=l.method,
        path=l.path, ip=l.ip, status=l.status, message=l.message,
        created_at=l.created_at,
        before_data=l.before_data, after_data=l.after_data, diff=l.diff,
    ).model_dump(mode="json"))


@router.get("/login-logs")
def list_login_logs(page: int = 1, page_size: int = 20,
                    username: str | None = None,
                    status: int | None = Query(None),
                    ctx: AuthContext = Depends(require_perm("log:login")),
                    db: Session = Depends(get_db)):
    """登录日志（成功/失败、IP、UA、锁定记录）。"""
    logs, total = org_service.list_login_logs(db, page, page_size, username, status)
    items = [LoginLogItem(
        id=l.id, user_id=l.user_id, username=l.username, login_type=l.login_type,
        ip=l.ip, status=l.status, message=l.message, created_at=l.created_at,
    ).model_dump(mode="json") for l in logs]
    return page_result(items, total, page, page_size)
