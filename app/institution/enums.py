"""机构模块业务枚举（LabeledIntEnum 自带中文 label，一处定义零双维护）。"""

from app.core.enums import LabeledIntEnum, make_labels


class InstitutionType(LabeledIntEnum):
    BANK = 10, '银行'
    GUARANTEE = 20, '担保'
    LAW_FIRM = 30, '律所'
    APPRAISAL = 40, '评估'
    ACCOUNTING = 50, '会计师'
    OTHER = 90, '其他'


class InstitutionSubtype(LabeledIntEnum):
    """银行子类型。"""

    STATE_OWNED = 10, '国有'
    JOINT_STOCK = 20, '股份'
    CITY_COMMERCIAL = 30, '城商'
    RURAL_COMMERCIAL = 40, '农商'
    FOREIGN = 50, '外资'
    PRIVATE = 60, '民营'


class InstitutionStatus(LabeledIntEnum):
    ACTIVE = 10, '正常'
    DISABLED = 20, '停用'
    CANCELLED = 90, '注销'


class AgreementType(LabeledIntEnum):
    COMPREHENSIVE = 10, '综合授信'
    GUARANTEE = 20, '保函授信'
    SERVICE = 30, '服务协议'
    ENTRUSTED = 40, '委贷协议'


class AgreementStatus(LabeledIntEnum):
    ACTIVE = 10, '生效'
    EXPIRED = 20, '失效'
    EXHAUSTED = 30, '已用完'
    TERMINATED = 90, '已终止'


class CreditChangeType(LabeledIntEnum):
    NEW_AGREEMENT = 10, '新增协议'
    AMOUNT_ADJUST = 20, '额度调整'
    AGREEMENT_EXPIRE = 30, '协议到期'
    BALANCE_REFRESH = 40, '余额刷新'


LABELS = make_labels(
    InstitutionType, InstitutionSubtype, InstitutionStatus,
    AgreementType, AgreementStatus, CreditChangeType,
)
