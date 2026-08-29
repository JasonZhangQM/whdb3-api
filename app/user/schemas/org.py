"""部门 / 角色 / 菜单 / 权限 Schemas。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# ===== 部门 =====
class DeptBrief(BaseModel):
    id: int
    parent_id: int
    name: str
    status: int
    member_count: int = 0


class DeptNode(BaseModel):
    id: int
    parent_id: int
    name: str
    leader_user_id: int | None
    leader_name: str | None
    ordery: int
    status: int
    status_display: str
    description: str | None = None
    member_count: int = 0
    created_by_name: str = ""
    children: list["DeptNode"] = []


class DeptCreate(BaseModel):
    parent_id: int = 0
    name: str
    leader_user_id: int | None = None
    ordery: int = 0
    description: str | None = None


class DeptUpdate(BaseModel):
    parent_id: int | None = None
    name: str | None = None
    leader_user_id: int | None = None
    ordery: int | None = None
    status: Literal[10, 20] | None = None
    description: str | None = None


# ===== 角色 =====
class RoleListItem(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    is_builtin: bool
    data_scope: int
    data_scope_display: str
    user_count: int = 0
    permission_count: int = 0
    created_at: datetime
    created_by_name: str = ""


class RoleDetail(RoleListItem):
    permission_codes: list[str]
    users: list[dict] = []  # 绑定用户（id/username/name/dept_name/position）


class RoleCreate(BaseModel):
    code: str  # 自定义角色 code（唯一）
    name: str
    description: str | None = None
    data_scope: Literal[10, 20, 30, 40] = 10


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    data_scope: Literal[10, 20, 30, 40] | None = None


class RolePermAssignReq(BaseModel):
    permission_ids: list[int]


class RoleUserAssignReq(BaseModel):
    user_ids: list[int]


# ===== 菜单 & 权限 =====
class PermItem(BaseModel):
    id: int
    code: str
    name: str
    module: str
    type: int
    type_display: str
    menu_id: int | None
    ordery: int


class MenuCreate(BaseModel):
    parent_id: int = 0
    caption: str
    icon: str | None = None
    path: str | None = None
    component: str | None = None
    ordery: int = 0
    type: Literal[10, 20, 30]
    visible: bool = True
    keep_alive: bool = False
    redirect: str | None = None
    permission_code: str | None = None  # 为空则自动生成


class MenuUpdate(BaseModel):
    parent_id: int | None = None
    caption: str | None = None
    icon: str | None = None
    path: str | None = None
    component: str | None = None
    ordery: int | None = None
    visible: bool | None = None
    keep_alive: bool | None = None
    redirect: str | None = None
    permission_code: str | None = None
