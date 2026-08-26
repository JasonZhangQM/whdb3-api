"""用户模块业务枚举（int 值存 SmallInteger，label 供字典接口输出）。"""

from enum import IntEnum


class UserStatus(IntEnum):
    ACTIVE = 10
    DISABLED = 20
    RESIGNED = 30


class Gender(IntEnum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2


class DataScope(IntEnum):
    SELF = 10            # 本人
    DEPT = 20            # 本部门
    DEPT_AND_CHILD = 30  # 本部门及下级
    ALL = 40             # 全部
    CUSTOM = 50          # 自定义


class PermType(IntEnum):
    MENU = 10      # 菜单权限
    ACTION = 20    # 操作权限
    DATA = 30      # 数据权限


class MenuType(IntEnum):
    DIR = 10       # 目录
    PAGE = 20      # 菜单
    BUTTON = 30    # 按钮


class CommonStatus(IntEnum):
    ACTIVE = 10
    DISABLED = 20


class LogStatus(IntEnum):
    SUCCESS = 10
    FAILED = 20


LABELS: dict[str, dict[int, str]] = {
    "user_status": {10: "启用", 20: "停用", 30: "离职"},
    "gender": {0: "未知", 1: "男", 2: "女"},
    "data_scope": {10: "本人", 20: "本部门", 30: "本部门及下级", 40: "全部", 50: "自定义"},
    "perm_type": {10: "菜单", 20: "操作", 30: "数据"},
    "menu_type": {10: "目录", 20: "菜单", 30: "按钮"},
    "common_status": {10: "启用", 20: "停用"},
    "log_status": {10: "成功", 20: "失败"},
}
