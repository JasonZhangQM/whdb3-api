"""用户模块业务枚举（LabeledIntEnum 自带中文 label，一处定义零双维护）。"""

from app.core.enums import LabeledIntEnum, make_labels


class UserStatus(LabeledIntEnum):
    ACTIVE = 10, '启用'
    DISABLED = 20, '停用'
    RESIGNED = 30, '离职'


class Gender(LabeledIntEnum):
    UNKNOWN = 0, '未知'
    MALE = 1, '男'
    FEMALE = 2, '女'


class DataScope(LabeledIntEnum):
    SELF = 10, '本人'
    DEPT = 20, '本部门'
    DEPT_AND_CHILD = 30, '本部门及下级'
    ALL = 40, '全部'
    CUSTOM = 50, '自定义'


class PermType(LabeledIntEnum):
    MENU = 10, '菜单'
    ACTION = 20, '操作'
    DATA = 30, '数据'


class MenuType(LabeledIntEnum):
    DIR = 10, '目录'
    PAGE = 20, '菜单'
    BUTTON = 30, '按钮'


class CommonStatus(LabeledIntEnum):
    ACTIVE = 10, '启用'
    DISABLED = 20, '停用'


class LogStatus(LabeledIntEnum):
    SUCCESS = 10, '成功'
    FAILED = 20, '失败'


LABELS = make_labels(
    UserStatus, Gender, DataScope, PermType, MenuType, CommonStatus, LogStatus,
)
