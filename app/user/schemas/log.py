"""日志 / 字典 Schemas。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class OperationLogBrief(BaseModel):
    id: int
    module: str | None
    action: str | None
    target_name: str | None
    status: int
    created_at: datetime


class OperationLogItem(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    user_name: str | None
    module: str | None
    action: str | None
    target_type: str | None
    target_id: str | None
    target_name: str | None
    method: str | None
    path: str | None
    ip: str | None
    status: int
    message: str | None
    created_at: datetime


class OperationLogDetail(OperationLogItem):
    before_data: dict | None
    after_data: dict | None
    diff: dict | None


class LoginLogItem(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    login_type: str | None
    ip: str | None
    status: int
    message: str | None
    created_at: datetime


# ===== 字典 =====
class DictItem(BaseModel):
    value: int
    label: str


class UserOption(BaseModel):
    """员工下拉。"""

    id: int
    username: str
    name: str
    dept_name: str | None
    position: str | None
