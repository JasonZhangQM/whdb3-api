"""客户模块业务枚举（LabeledIntEnum 自带中文 label，一处定义零双维护）。"""

from app.core.enums import LabeledIntEnum, make_labels


class Genre(LabeledIntEnum):
    COMPANY = 1, '企业'
    PERSONAL = 2, '个人'


class CustomTyp(LabeledIntEnum):
    NEW = 10, '新增'
    EXISTING = 20, '存量'
    EXISTING_NEW = 30, '存量新增'


class CustomState(LabeledIntEnum):
    NORMAL = 10, '正常'
    COUNTER_GUARANTEE = 20, '反担保'
    MICRO_LOAN = 30, '小贷'
    CANCELLED = 90, '注销'


class Classification(LabeledIntEnum):
    """五级分类。"""

    NORMAL = 10, '正常'
    SPECIAL_MENTION = 20, '关注'
    SUBSTANDARD = 30, '次级'
    DOUBTFUL = 40, '可疑'
    LOSS = 50, '损失'


class IndTyp(LabeledIntEnum):
    PRIMARY = 10, '一产'
    SECONDARY = 20, '二产'
    TERTIARY = 30, '三产'


class TagType(LabeledIntEnum):
    INDUSTRY = 10, '行业'
    BUSINESS = 20, '业务'


class Typing(LabeledIntEnum):
    """企业划型（工信部）。"""

    MICRO = 10, '微型'
    SMALL = 20, '小型'
    MEDIUM = 30, '中型'
    LARGE = 40, '大型'
    UNTYPED = 90, '未划型'


class Decisionor(LabeledIntEnum):
    """决策机构。"""

    SHAREHOLDER_MEETING = 11, '股东会'
    BOARD = 12, '董事会'
    CHAIRMAN = 13, '董事长'
    GENERAL_MEETING = 15, '总经理办公会'
    OTHER_ORGANIZATION = 21, '其他机构'
    LEGAL_PERSON = 23, '法定代表人'


class CustomNature(LabeledIntEnum):
    """企业性质。"""

    STATE_OWNED = 11, '国有'
    COLLECTIVE = 21, '集体'
    PRIVATE = 31, '民营'
    FOREIGN = 41, '外资'
    JOINT_VENTURE = 51, '合资'


class MaritalStatus(LabeledIntEnum):
    UNMARRIED = 10, '未婚'
    MARRIED = 20, '已婚'
    DIVORCED = 30, '离异未再婚'
    WIDOWED = 40, '丧偶'


class HouseholdNature(LabeledIntEnum):
    URBAN = 10, '城镇'
    RURAL = 20, '农村'


class CoreLimitStatus(LabeledIntEnum):
    ACTIVE = 10, '生效'
    EXPIRED = 20, '失效'
    EXHAUSTED = 30, '已用完'


class CommonStatus(LabeledIntEnum):
    ACTIVE = 10, '启用'
    DISABLED = 20, '停用'


# 自动从枚举类生成 LABELS 字典（兼容层，旧代码零改动）
LABELS = make_labels(
    Genre, CustomTyp, CustomState, Classification, IndTyp, TagType,
    Typing, Decisionor, CustomNature, MaritalStatus, HouseholdNature,
    CoreLimitStatus, CommonStatus,
)
