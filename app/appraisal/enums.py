"""评审模块枚举：LabeledIntEnum 自带中文 label。"""

from app.core.enums import LabeledIntEnum, make_labels


class ReviewModel(LabeledIntEnum):
    """评审类型。"""
    INTERNAL = 10, '内审'
    INTERNAL_NON_MEETING = 11, '内审(非会议)'
    EXTERNAL = 20, '外审'
    SIGN = 50, '签批'
    XD_REVIEW = 60, '小贷-评审'
    XD_SIGN = 65, '小贷-签批'


class MeetingState(LabeledIntEnum):
    """评审会状态。"""
    PENDING = 10, '待上会'
    FINISHED = 20, '已上会'


class CommentType(LabeledIntEnum):
    """评委意见。"""
    NONE = 0, '未发表'
    AGREE = 10, '同意'
    RECONSIDER = 20, '复议'
    DISAGREE = 30, '不同意'


class ExpertType(LabeledIntEnum):
    """专家类型。"""
    INTERNAL = 10, '内部评委'
    EXTERNAL = 20, '外部专家'


class SupplyStatus(LabeledIntEnum):
    """补调状态（布尔 + 状态视图映射）。"""
    PENDING = 10, '待补调'     # is_resolved=false
    RESOLVED = 20, '已解决'   # is_resolved=true


LABELS = make_labels(
    ReviewModel, MeetingState, CommentType, ExpertType, SupplyStatus,
)
