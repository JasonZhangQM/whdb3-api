"""认证 & 个人中心 Schemas。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LoginReq(BaseModel):
    """登录入参：vben 前端传 username；account 字段兼容 API 直调与旧脚本。"""

    username: str | None = None
    account: str | None = None  # 别名（支持 username 或 email 值）
    password: str
    captcha_id: str | None = None
    captcha_code: str | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "LoginReq":
        if not (self.username or self.account):
            raise ValueError("username 不能为空")
        return self

    @property
    def login_name(self) -> str:
        return self.username or self.account or ""


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # access_token 秒数


class LoginResult(BaseModel):
    tokens: TokenPair
    must_change_password: bool


class RefreshReq(BaseModel):
    refresh_token: str


class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str


class ResetPasswordReq(BaseModel):
    new_password: str | None = None  # 为空则生成强随机密码并返回


class RoleBrief(BaseModel):
    id: int
    code: str
    name: str
    data_scope: int


class MenuNode(BaseModel):
    """自有菜单树 schema（/users/me 内嵌形态）。"""

    id: int
    caption: str
    icon: str | None = None
    path: str | None = None
    type: int  # 10目录 20菜单 30按钮
    children: list["MenuNode"] = []


class UserProfile(BaseModel):
    """/users/me：用户信息 + 权限上下文。"""

    id: int
    username: str
    name: str
    email: str
    phone: str | None
    avatar_url: str | None
    gender: int
    position: str | None
    status: int
    status_display: str
    dept_id: int | None
    dept_name: str | None
    dept_path_name: str | None  # "总公司/风控部/合规组" 面包屑
    roles: list[RoleBrief]
    permission_codes: list[str]
    data_scope: int
    data_scope_dept_ids: list[int]
    menus: list[MenuNode]
    is_super_admin: bool
    must_change_password: bool
    last_login_at: datetime | None


class ProfileUpdateReq(BaseModel):
    """本人基础信息（不含角色/部门/权限）。"""

    name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    gender: Literal[0, 1, 2] | None = None
