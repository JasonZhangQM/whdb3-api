"""项目模块枚举：LabeledIntEnum 自带中文 label，一处定义零双维护。"""

from app.core.enums import LabeledIntEnum, make_labels


class ArticleState(LabeledIntEnum):
    """项目状态机。"""
    PENDING_FEEDBACK = 10, '待反馈'
    FEEDBACK_DONE = 20, '已反馈'
    PENDING_REVIEW = 30, '待上会'
    REVIEW_DONE = 40, '已上会'
    SIGNED = 50, '已签批'
    DISBURSED = 51, '已放款'
    DONE = 55, '已解保'
    PENDING_CHANGE = 61, '待变更'
    CANCELLED = 99, '已注销'


class RepayMethod(LabeledIntEnum):
    """还款方式。"""
    MONTHLY_INTEREST = 10, '按月付息到期还本'
    EQUAL_INSTALLMENT = 20, '等额本息'
    MONTHLY_INTEREST_INSTALLMENT = 30, '按月付息分期还本'
    LUMP_SUM = 40, '到期一次还本付息'
    BALLOON = 50, '气球贷'


class Propose(LabeledIntEnum):
    """风控反馈上会建议。"""
    QUALIFIED = 10, '符合上会'
    NOT_YET = 20, '暂不符合'
    TERMINATE = 30, '建议终止'


class CreditModel(LabeledIntEnum):
    """授信类型（单项额度）。"""
    FLOW_LOAN = 10, '流贷'
    BANK_ACCEPT = 20, '银承敞口'
    GUARANTEE_LETTER = 30, '保函'
    COMPREHENSIVE = 40, '综合授信'
    ENTRUSTED_LOAN = 50, '委托贷款'
    MORTGAGE = 60, '按揭'
    DRAFT_GUARANTEE = 70, '票据保'
    DRAFT_EASY = 71, '上银票易保'
    DRAFT_CORE = 72, '票据保(核心企业授信)'


class SureType(LabeledIntEnum):
    """反担保类型。"""
    # 保证类
    CORP_GUARANTEE = 1, '企业保证'
    PERSONAL_GUARANTEE = 2, '个人保证'
    # 抵押类
    HOUSE_MORTGAGE = 11, '房产抵押'
    GROUND_MORTGAGE = 12, '土地抵押'
    CHATTEL_MORTGAGE = 13, '动产抵押'
    CONSTRUCTION_MORTGAGE = 14, '在建工程抵押'
    VEHICLE_MORTGAGE = 15, '车辆抵押'
    # 顺位
    HOUSE_SUCCESSION = 21, '房产顺位'
    GROUND_SUCCESSION = 22, '土地顺位'
    CONSTRUCTION_SUCCESSION = 23, '在建顺位'
    CHATTEL_SUCCESSION = 24, '动产顺位'
    # 质押
    RECEIVABLE_PLEDGE = 31, '应收质押'
    STOCK_PLEDGE = 32, '股权质押'
    DRAFT_PLEDGE = 33, '票据质押'
    CHATTEL_PLEDGE = 34, '动产质押'
    OTHER_PLEDGE = 39, '其他权利质押'
    # 监管
    HOUSE_SUPERVISE = 42, '房产监管'
    GROUND_SUPERVISE = 43, '土地监管'
    DRAFT_SUPERVISE = 44, '票据监管'
    CHATTEL_SUPERVISE = 47, '动产监管'
    OTHER_SUPERVISE = 49, '其他监管'
    # 预售
    STOCK_PRESALE = 51, '股权预售'
    HOUSE_PRESALE = 52, '房产预售'
    GROUND_PRESALE = 53, '土地预售'
    # 其他
    OTHER = 59, '其他'
    MULTI_DRAW = 61, '分次提用协议'


class CreditTermUnit(LabeledIntEnum):
    """期限单位。"""
    YEAR = 10, '年'
    MONTH = 20, '月'
    DAY = 30, '天'


class ChangeView(LabeledIntEnum):
    """变更结论。"""
    APPLY = 10, '变更申请'
    APPROVED = 11, '同意变更'
    REJECTED = 21, '否决变更'


class ProductCategory(LabeledIntEnum):
    """产品类别。"""
    FINANCING = 10, '融资担保'
    NON_FINANCING = 20, '非融资担保'
    ENTRUSTED_LOAN = 30, '委托贷款'
    OTHER = 90, '其他业务'


LABELS = make_labels(
    ArticleState, RepayMethod, Propose,
    CreditModel, SureType, CreditTermUnit, ChangeView, ProductCategory,
)
