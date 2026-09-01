"""权证模块 Schemas（M2 范围：他权/项目绑定随 M3）。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

WarrantTypeLiteral = Literal[1, 5, 6, 11, 21, 31, 41, 51, 55]


# ===== 类型扩展 =====
class HouseItem(BaseModel):
    region_id: int
    house_locate: str = Field(..., max_length=255)
    house_app: int
    house_area: float = Field(..., gt=0)
    house_name: str | None = None
    house_build_year: int | None = None
    house_usage: Literal[10, 20, 30] = 10


class GroundItem(BaseModel):
    region_id: int
    ground_locate: str
    ground_app: str
    ground_area: float = Field(..., gt=0)


class ConstructionItem(BaseModel):
    region_id: int
    construct_locate: str = Field(..., max_length=255)
    construct_app: str
    construct_area: float = Field(..., gt=0)


class ReceivableCreate(BaseModel):
    receivable_detail: str
    receive_units: list[str] = []


class StockCreate(BaseModel):
    stock_type: Literal[10, 20, 30]
    target: str
    ratio: float = Field(..., ge=0, le=100)
    registered_capital: float = 0
    paid_capital: float = 0
    remark: str | None = None


class DraftCreate(BaseModel):
    draft_type: Literal[10, 20, 30]
    denomination: float = Field(..., gt=0)
    draft_detail: str


class VehicleCreate(BaseModel):
    frame_num: str = Field(..., max_length=64)
    plate_num: str = Field(..., max_length=32)
    vehicle_brand: str = Field(..., max_length=64)
    remark: str | None = None


class ChattelCreate(BaseModel):
    chattel_type: Literal[10, 20, 30, 99]
    chattel_detail: str


class PatentCreate(BaseModel):
    patent_name: str
    reg_num: str
    patent_ty: int = 10


class SoftwareCreate(BaseModel):
    software_name: str
    reg_num: str


class OtherCreate(BaseModel):
    other_type: Literal[10, 20, 30, 40, 501, 70, 99]
    cost: float = 0
    other_detail: str
    patent: PatentCreate | None = None
    software: SoftwareCreate | None = None


# ===== 所有权人 =====
class OwnershipCreate(BaseModel):
    ownership_num: str = Field(..., max_length=128)
    owner_id: int
    share_ratio: float | None = Field(None, ge=0, le=100)


class OwnershipUpdate(BaseModel):
    ownership_num: str | None = None
    share_ratio: float | None = None


# ===== 类型扩展基类（WarrantCreate / TypeDetailUpdate 共用字段，一处定义）=====
class _ExtBase(BaseModel):
    """9 种权证类型的扩展信息字段集合——WarrantCreate 继承 + 主表元数据，
    TypeDetailUpdate 直接使用做整体替换。子类新增字段加在此处即可。"""

    houses: list[HouseItem] | None = None
    grounds: list[GroundItem] | None = None
    constructions: list[ConstructionItem] | None = None
    receivable: ReceivableCreate | None = None
    stock: StockCreate | None = None
    draft: DraftCreate | None = None
    vehicle: VehicleCreate | None = None
    chattel: ChattelCreate | None = None
    other: OtherCreate | None = None


# ===== 主表 =====
class WarrantCreate(_ExtBase):
    """创建权证：主表 + 按类型的扩展信息 + 所有权人一次性提交（事务原子）。"""

    warrant_num: str = Field(..., max_length=128)
    warrant_type: WarrantTypeLiteral
    owners: list[OwnershipCreate] = []


class WarrantUpdate(BaseModel):
    """修改主表字段（评估/状态/拍卖；扩展信息走 type-detail）。"""

    evaluate_method: int | None = None
    evaluate_value: float | None = None
    evaluate_date: date | None = None
    evaluate_explain: str | None = None
    evaluate_company: str | None = None
    meeting_date: date | None = None
    warrant_state: int | None = None
    storage_explain: str | None = None
    auction_state: int | None = None
    auction_date: date | None = None
    listing_price: float | None = None
    auction_remark: str | None = None
    transaction_date: date | None = None
    auction_amount: float | None = None
    inquiry_date: date | None = None
    inquiry_detail: str | None = None


class TypeDetailUpdate(_ExtBase):
    """按类型更新扩展信息（整体替换；房产全量替换）。"""


# ===== 出入库 / 评估 =====
class StorageCreate(BaseModel):
    storage_type: Literal[10, 20, 30, 60, 110, 120, 310, 410, 990]
    storage_explain: str | None = None
    transfer_id: int | None = None
    storage_date: date


class EvaluateCreate(BaseModel):
    evaluate_method: int
    evaluate_value: float = Field(..., gt=0)
    evaluate_date: date
    evaluate_explain: str | None = None
    evaluate_company: str | None = None


class RecheckCreate(BaseModel):
    check_value: float = Field(..., gt=0)
    recheck_value: float = Field(..., gt=0)
    recheck_channel: str
    remark: str | None = None


# ===== 票据 / 应收明细 =====
class DraftExtendCreate(BaseModel):
    draft_type: Literal[10, 20, 11, 12, 21]
    draft_num: str = Field(..., max_length=128)
    acceptor_id: int
    core_id: int
    draft_amount: float = Field(..., gt=0)
    issue_date: date
    due_date: date


class DraftExtendUpdate(BaseModel):
    draft_state: int | None = None
    draft_amount: float | None = None
    due_date: date | None = None


class ReceiveExtendCreate(BaseModel):
    receive_unit: str = Field(..., max_length=128)


# ===== 批量操作 / 字典 =====
class BatchStorageReq(BaseModel):
    warrant_ids: list[int] = Field(..., min_length=1, max_length=100)
    storage_type: Literal[10, 20, 30, 60, 110, 120, 310, 410, 990]
    storage_explain: str | None = None
    transfer_id: int | None = None
    storage_date: date


class BatchTransferReq(BaseModel):
    warrant_ids: list[int] = Field(..., min_length=1, max_length=100)
    to_conservator_id: int
    reason: str


class BatchCancelReq(BaseModel):
    warrant_ids: list[int] = Field(..., min_length=1, max_length=100)
    reason: str


class EvaluateCompanyCreate(BaseModel):
    name: str = Field(..., max_length=128)


class WarrantBrief(BaseModel):
    id: int
    warrant_num: str
    warrant_type: int
    warrant_state: int
    evaluate_value: float | None
    created_by_name: str
    created_at: datetime
