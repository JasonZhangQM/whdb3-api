"""客户模块业务枚举。"""

from enum import IntEnum


class Genre(IntEnum):
    COMPANY = 1
    PERSONAL = 2


class CustomTyp(IntEnum):
    NEW = 10        # 新增
    EXISTING = 20   # 存量
    EXISTING_NEW = 30  # 存量新增


class CustomState(IntEnum):
    NORMAL = 10
    COUNTER_GUARANTEE = 20  # 反担保
    MICRO_LOAN = 30         # 小贷
    CANCELLED = 90          # 注销


class Classification(IntEnum):
    """五级分类。"""

    NORMAL = 10     # 正常
    SPECIAL_MENTION = 20  # 关注
    SUBSTANDARD = 30  # 次级
    DOUBTFUL = 40   # 可疑
    LOSS = 50       # 损失


class RegionLevel(IntEnum):
    PROVINCE = 10
    CITY = 20
    DISTRICT = 30
    TOWNSHIP = 40


class IndTyp(IntEnum):
    PRIMARY = 10   # 一产
    SECONDARY = 20  # 二产
    TERTIARY = 30  # 三产


class TagType(IntEnum):
    INDUSTRY = 10
    BUSINESS = 20


class Typing(IntEnum):
    """企业划型（工信部）。"""

    MICRO = 10
    SMALL = 20
    MEDIUM = 30
    LARGE = 40
    UNTYPED = 90


class Decisionor(IntEnum):
    """决策机构。"""

    SHAREHOLDER_MEETING = 11   # 股东会
    BOARD = 12                 # 董事会
    CHAIRMAN = 13              # 董事长
    GENERAL_MEETING = 15       # 总经理办公会
    OTHER_ORGANIZATION = 21    # 其他机构
    LEGAL_PERSON = 23          # 法定代表人


class CustomNature(IntEnum):
    """企业性质。"""

    STATE_OWNED = 11      # 国有
    COLLECTIVE = 21       # 集体
    PRIVATE = 31          # 民营
    FOREIGN = 41          # 外资
    JOINT_VENTURE = 51    # 合资
    LIMITED = 61          # 有限责任
    STOCK = 71            # 股份有限


class MaritalStatus(IntEnum):
    UNMARRIED = 10
    MARRIED = 20
    DIVORCED = 30
    WIDOWED = 40


class HouseholdNature(IntEnum):
    URBAN = 10
    RURAL = 20


class CoreLimitStatus(IntEnum):
    ACTIVE = 10
    EXPIRED = 20
    EXHAUSTED = 30


LABELS: dict[str, dict[int, str]] = {
    "genre": {1: "企业", 2: "个人"},
    "custom_typ": {10: "新增", 20: "存量", 30: "存量新增"},
    "custom_state": {10: "正常", 20: "反担保", 30: "小贷", 90: "注销"},
    "classification": {10: "正常", 20: "关注", 30: "次级", 40: "可疑", 50: "损失"},
    "region_level": {10: "省", 20: "市", 30: "区县", 40: "乡镇街道"},
    "ind_typ": {10: "一产", 20: "二产", 30: "三产"},
    "tag_type": {10: "行业", 20: "业务"},
    "typing": {10: "微型", 20: "小型", 30: "中型", 40: "大型", 90: "未划型"},
    "decisionor": {
        11: "股东会", 12: "董事会", 13: "董事长",
        15: "总经理办公会", 21: "其他机构", 23: "法定代表人",
    },
    "custom_nature": {
        11: "国有", 21: "集体", 31: "民营", 41: "外资",
        51: "合资", 61: "有限责任", 71: "股份有限",
    },
    "marital_status": {10: "未婚", 20: "已婚", 30: "离异未再婚", 40: "丧偶"},
    "household_nature": {10: "城镇", 20: "农村"},
    "core_limit_status": {10: "生效", 20: "失效", 30: "已用完"},
    "common_status": {10: "启用", 20: "停用"},
}
