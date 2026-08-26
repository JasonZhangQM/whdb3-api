"""机构模块业务枚举。"""

from enum import IntEnum


class InstitutionType(IntEnum):
    BANK = 10
    GUARANTEE = 20
    LAW_FIRM = 30
    APPRAISAL = 40
    ACCOUNTING = 50
    OTHER = 90


class InstitutionSubtype(IntEnum):
    """银行子类型。"""

    STATE_OWNED = 10   # 国有
    JOINT_STOCK = 20   # 股份
    CITY_COMMERCIAL = 30  # 城商
    RURAL_COMMERCIAL = 40  # 农商
    FOREIGN = 50       # 外资
    PRIVATE = 60       # 民营


class InstitutionStatus(IntEnum):
    ACTIVE = 10
    DISABLED = 20
    CANCELLED = 90


class AgreementType(IntEnum):
    COMPREHENSIVE = 10  # 综合授信
    GUARANTEE = 20      # 保函授信
    SERVICE = 30        # 服务协议
    ENTRUSTED = 40      # 委贷协议


class AgreementStatus(IntEnum):
    ACTIVE = 10
    EXPIRED = 20
    EXHAUSTED = 30
    TERMINATED = 90


class CreditChangeType(IntEnum):
    NEW_AGREEMENT = 10
    AMOUNT_ADJUST = 20
    AGREEMENT_EXPIRE = 30
    BALANCE_REFRESH = 40


LABELS: dict[str, dict[int, str]] = {
    "institution_type": {
        10: "银行", 20: "担保", 30: "律所", 40: "评估", 50: "会计师", 90: "其他",
    },
    "institution_subtype": {
        10: "国有", 20: "股份", 30: "城商", 40: "农商", 50: "外资", 60: "民营",
    },
    "institution_status": {10: "正常", 20: "停用", 90: "注销"},
    "agreement_type": {10: "综合授信", 20: "保函授信", 30: "服务协议", 40: "委贷协议"},
    "agreement_status": {10: "生效", 20: "失效", 30: "已用完", 90: "已终止"},
    "credit_change_type": {
        10: "新增协议", 20: "额度调整", 30: "协议到期", 40: "余额刷新",
    },
}
