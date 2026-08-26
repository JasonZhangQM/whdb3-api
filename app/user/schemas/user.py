"""用户管理 Schemas。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.user.schemas.auth import RoleBrief
from app.user.schemas.log import OperationLogBrief


class UserListItem(BaseModel):
    id: int
    username: str
    name: str
    email: str
    phone: str | None
    avatar_url: str | None
    gender: int
    status: int
    status_display: str
    position: str | None
    dept_id: int | None
    dept_name: str | None
    role_names: list[str]
    is_super_admin: bool
    last_login_at: datetime | None
    created_at: datetime


class UserDetail(UserListItem):
    dept_path_name: str | None
    roles: list[RoleBrief]
    permission_count: int
    recent_logs: list[OperationLogBrief]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    name: str
    email: EmailStr
    phone: str | None = None
    gender: Literal[0, 1, 2] = 0
    dept_id: int | None = None
    position: str | None = None
    role_ids: list[int] = Field(min_length=1)
    default_password: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    gender: Literal[0, 1, 2] | None = None
    dept_id: int | None = None
    position: str | None = None


class UserStatusReq(BaseModel):
    status: Literal[10, 20, 30]


class RoleAssignReq(BaseModel):
    role_ids: list[int]


class TransferResource(BaseModel):
    managed_customers: bool = True   # 管护客户
    directed_articles: bool = True   # 主办项目
    controlled_articles: bool = True  # 风控项目
    review_todos: bool = True        # 保后待办
    pending_approvals: bool = True   # 待审批任务
    created_customers: bool = False  # 创建人（审计事实，默认不改写）


class TransferReq(BaseModel):
    to_user_id: int
    resources: TransferResource = TransferResource()
    reason: str | None = None


class TransferReport(BaseModel):
    from_user_id: int
    to_user_id: int
    counts: dict[str, int]  # 资源类型 -> 转移数量
