"""权证模块业务枚举（LabeledIntEnum 自带中文 label，一处定义零双维护）。"""

from app.core.enums import LabeledIntEnum, make_labels


class WarrantType(LabeledIntEnum):
    HOUSE = 1, '房产'
    GROUND = 5, '土地'
    CONSTRUCTION = 6, '在建工程'
    RECEIVABLE = 11, '应收账款'
    STOCK = 21, '股权'
    DRAFT = 31, '票据'
    VEHICLE = 41, '车辆'
    CHATTEL = 51, '动产'
    OTHER = 55, '其他'
    HYPOTHEC = 99, '他权'


class WarrantState(LabeledIntEnum):
    NOT_STORED = 10, '未入库'
    STORED = 20, '已入库'
    GUARDED = 30, '已加保'
    NO_NEED = 60, '无需入库'
    RENEW_OUT = 110, '续抵出库'
    LENT = 210, '已借出'
    RELEASED = 310, '解保出库'
    TRANSFERRED = 410, '已移交'
    CANCELLED = 990, '已注销'


class AuctionState(LabeledIntEnum):
    NORMAL = 10, '正常'
    SEALED = 20, '查封'
    EVALUATING = 30, '评估'
    LISTED = 50, '挂网'
    DEALT = 110, '成交'
    FAILED = 210, '流拍'
    REVERSED = 310, '回转'
    CANCELLED = 990, '注销'


class StorageType(LabeledIntEnum):
    STORE_IN = 10, '入库'
    RENEW_OUT = 20, '续抵出库'
    GUARD = 30, '已加保'
    NO_NEED = 60, '无需入库'
    LEND_OUT = 110, '借出'
    RETURN = 120, '归还'
    RELEASE_OUT = 310, '解保出库'
    TRANSFER = 410, '移交'
    CANCELLED = 990, '注销'


class DraftMainType(LabeledIntEnum):
    """票据主表类型。"""

    COMMERCIAL = 10, '商业承兑'
    BANK = 20, '银行承兑'
    CHEQUE = 30, '支票'


class DraftDetailType(LabeledIntEnum):
    """票据明细类型。"""

    E_BANK = 10, '电银承'
    BANK = 20, '银承'
    E_COMMERCIAL = 11, '电商承'
    COMMERCIAL = 12, '商承'
    CHEQUE = 21, '支票'


class DraftState(LabeledIntEnum):
    NOT_STORED = 10, '未入库'
    STORED = 20, '已入库'
    GUARDED = 30, '已加保'
    RETURNED = 120, '已归还'
    SWAP_OUT = 210, '置换出库'
    RELEASED = 310, '解保出库'
    COLLECTION_OUT = 410, '托收出库'
    CANCELLED = 990, '已注销'


class HouseUsage(LabeledIntEnum):
    SELF = 10, '自用'
    RENT = 20, '出租'
    VACANT = 30, '空置'


class StockType(LabeledIntEnum):
    LTD = 10, '有限公司股权'
    JOINT_STOCK = 20, '股份公司股份'
    PROMOTER = 30, '举办者权益'


class ChattelType(LabeledIntEnum):
    INVENTORY = 10, '存货'
    MACHINERY = 20, '机器设备'
    MEDICAL = 30, '医疗设备'
    OTHER = 99, '动产'


class OtherType(LabeledIntEnum):
    PURCHASE_CONTRACT = 10, '购房合同'
    VEHICLE_CERT = 20, '车辆合格证'
    PATENT = 30, '专利'
    TRADEMARK = 40, '商标'
    SOFTWARE = 501, '软件著作权'
    ACCOUNT = 70, '账户'
    OTHER = 99, '其他'


class EvaluateMethod(LabeledIntEnum):
    COST = 10, '成本法'
    MARKET = 20, '市场法'
    INCOME = 30, '收益法'
    ASSUMED_DEV = 40, '假设开发法'
    OTHER = 90, '其他'


class CommonStatus(LabeledIntEnum):
    ACTIVE = 10, '启用'
    DISABLED = 20, '停用'


LABELS = make_labels(
    WarrantType, WarrantState, AuctionState, StorageType,
    DraftMainType, DraftDetailType, DraftState,
    HouseUsage, StockType, ChattelType, OtherType, EvaluateMethod,
    CommonStatus,
)
