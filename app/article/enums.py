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


class Propose(LabeledIntEnum):
    """风控反馈上会建议。"""
    QUALIFIED = 10, '符合上会'
    NOT_YET = 20, '暂不符合'
    TERMINATE = 30, '建议终止'


# ============== 反担保类型二维拆分 ==============
# 第一维度：担保物 × 第二维度：担保方式 —— 共同确定一条反担保措施

class WareCategory(LabeledIntEnum):
    """担保物类别（9 + 保证）。"""
    GUARANTOR = 1, '保证'          # 保证类专用
    HOUSE = 11, '房产'
    GROUND = 14, '土地'
    CONSTRUCTION = 16, '在建工程'
    RECEIVABLE = 21, '应收账款'
    DRAFT = 31, '票据'
    STOCK = 41, '股权'
    VEHICLE = 51, '车辆'
    CHATTEL = 61, '动产'
    OTHER = 91, '其他'


class MethodCategory(LabeledIntEnum):
    """担保方式类别（6 + "企业"、"个人"）。"""
    COMPANY = 1, '企业'            # 保证类专用
    PERSONAL = 2, '个人'            # 保证类专用
    MORTGAGE = 11, '抵押'
    SUCCESSION = 15, '顺位抵押'
    PLEDGE = 21, '质押'
    SUPERVISE = 31, '监管'
    PRESALE = 61, '预售'
    OTHER = 91, '其他'


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
    ArticleState, Propose,
    WareCategory, MethodCategory,
    CreditTermUnit, ChangeView, ProductCategory,
)
