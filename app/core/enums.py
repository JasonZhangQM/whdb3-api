"""跨模块通用枚举基类与工厂。

各业务模块的 enums.py 应继承 LabeledIntEnum，让枚举值自带中文 label，
消除 IntEnum + LABELS 字典双维护的不同步风险。
"""

from enum import IntEnum


class LabeledIntEnum(IntEnum):
    """枚举自带中文 label，一个地方定义同时满足代码逻辑和接口翻译。

    用法::

        class Classification(LabeledIntEnum):
            NORMAL = 10, '正常'       # 第二个值是中文 label
            WATCH = 20, '关注'

    - 业务代码：``Classification.NORMAL == 10`` ✅（仍是 int 子类，SQLAlchemy SmallInteger 兼容）
    - 取中文：``Classification(20).label`` → ``"关注"``
    - 生成字典：``{e.value: e.label for e in Classification}`` → ``{10: '正常', 20: '关注'}``
    """

    label: str  # 实例属性，类型标注帮助 IDE

    def __new__(cls, value: int, label: str):
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj


def make_labels(*enum_classes: type[LabeledIntEnum]) -> dict[str, dict[int, str]]:
    """从枚举类自动生成 LABELS 字典（兼容层，旧代码零改动）。

    用法::

        LABELS = make_labels(Classification, Genre)
        # LABELS['classification'] = {10: '正常', 20: '关注', ...}

    字典 key 为枚举类名 snake_case 形式。
    """
    import re

    result: dict[str, dict[int, str]] = {}
    for cls in enum_classes:
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        result[name] = {e.value: e.label for e in cls}
    return result
