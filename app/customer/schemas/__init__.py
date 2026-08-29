"""客户模块 Schemas。"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ===== 字典 =====
class IndustryNode(BaseModel):
    id: int
    code: str
    name: str
    ind_typ: Literal[10, 20, 30]
    parent_id: int
    children: list["IndustryNode"] = []


class TagItem(BaseModel):
    id: int
    name: str
    type: Literal[10, 20]
    status: int
    in_use: bool


class TagCreate(BaseModel):
    name: str = Field(..., max_length=255)
    type: Literal[10, 20] = 10


# ===== 集团 =====
class GroupTreeNode(BaseModel):
    id: int
    code: str
    name: str
    parent_id: int
    parent_customer_id: int | None
    parent_customer_name: str | None
    credit_amount: float
    total_insure_amount: float
    member_count: int
    status: int
    children: list["GroupTreeNode"] = []


class GroupDetail(GroupTreeNode):
    description: str | None
    created_by_name: str
    created_at: datetime
    members: list["CustomerBrief"]


class GroupCreate(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    parent_id: int = 0
    parent_customer_id: int
    credit_amount: float = 0
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str
    parent_id: int | None = None
    credit_amount: float = 0
    description: str | None = None
    status: Literal[10, 20] = 10


class GroupMemberAddReq(BaseModel):
    customer_ids: list[int] = Field(..., min_length=1, max_length=100)


# ===== 授信区域 =====
class CreditRegionTreeNode(BaseModel):
    id: int
    code: str
    name: str
    parent_id: int
    platform_name: str | None
    credit_amount: float
    used_amount: float
    member_count: int
    status: int
    children: list["CreditRegionTreeNode"] = []


class CreditRegionDetail(CreditRegionTreeNode):
    description: str | None
    created_by_name: str
    created_at: datetime
    members: list["CustomerBrief"]
    total_credit_amount: float
    total_amount: float


class CreditRegionCreate(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    parent_id: int = 0
    credit_amount: float = 0
    platform_name: str | None = None
    description: str | None = None


class CreditRegionUpdate(BaseModel):
    name: str
    credit_amount: float = 0
    platform_name: str | None = None
    description: str | None = None
    status: Literal[10, 20] = 10


# ===== 核心企业额度 =====
class CoreLimitBrief(BaseModel):
    id: int
    credit_amount: float
    valid_begin_date: date
    valid_end_date: date
    used_amount: float
    remaining_amount: float
    status: int


class CoreLimitCreate(BaseModel):
    credit_amount: float = Field(..., gt=0)
    valid_begin_date: date
    valid_end_date: date
    remark: str | None = None


class CoreLimitUpdate(BaseModel):
    credit_amount: float | None = None
    valid_end_date: date | None = None
    status: Literal[10, 20, 30] | None = None
    used_amount: float | None = None
    remark: str | None = None


class CoreHistoryItem(BaseModel):
    id: int
    change_content: dict
    changed_by_name: str
    updated_at: datetime


class CoreInfoBrief(BaseModel):
    core_rate: float | None
    core_remark: str | None
    current_limit: CoreLimitBrief | None
    total_used_amount: float


# ===== 客户主表 =====
class CustomerBrief(BaseModel):
    id: int
    name: str
    short_name: str
    genre: Literal[1, 2]
    custom_state: Literal[10, 20, 30, 90]
    is_core: bool
    is_acceptor: bool
    managementor_name: str
    credit_amount: float
    amount: float
    classification: Literal[10, 20, 30, 40, 50]


class CustomerListItem(CustomerBrief):
    custom_typ: Literal[10, 20, 30]
    region_name: str | None
    credit_region_id: int | None
    credit_region_name: str | None
    industry_name: str | None
    group_id: int | None
    group_name: str | None
    controler_name: str
    last_provide_date: date | None
    last_review_date: date | None
    day_space: int


class CompanyProfileCreate(BaseModel):
    credit_code: str
    decisionor: Literal[11, 12, 13, 15, 21, 23]
    custom_nature: Literal[11, 21, 31, 41, 51, 61, 71]
    industry_c: int
    capital: float = 0
    paid_capital: float = 0
    registered_addr: str
    representative: str


class PersonalProfileCreate(BaseModel):
    license_num: str = Field(..., min_length=18, max_length=18)
    license_addr: str
    marital_status: Literal[10, 20, 30, 40]
    household_nature: Literal[10, 20]


class CustomerCreate(BaseModel):
    """添加客户（接入审批流 customer_create，审批通过才落库）。"""

    name: str = Field(..., max_length=128)
    short_name: str = Field(..., max_length=16)
    genre: Literal[1, 2]
    contact_addr: str
    linkman: str
    contact_num: str
    region_id: int
    credit_region_id: int | None = None
    industry_id: int
    group_id: int | None = None
    is_core: bool = False
    is_acceptor: bool = False
    core_rate: float | None = None
    core_remark: str | None = None
    managementor_id: int
    controler_id: int
    tags: list[int] = []
    company: CompanyProfileCreate | None = None
    personal: PersonalProfileCreate | None = None


class CustomerUpdate(BaseModel):
    """客户修改（所有可修改字段直接生效，客户审批场景已移除）。"""

    name: str | None = None
    short_name: str | None = None
    credit_amount: float | None = None
    custom_state: int | None = None
    custom_typ: int | None = None
    managementor_id: int | None = None
    contact_addr: str | None = None
    linkman: str | None = None
    contact_num: str | None = None
    region_id: int | None = None
    industry_id: int | None = None
    group_id: int | None = None
    classification: int | None = None
    tags: list[int] | None = None


class CustomerTransferReq(BaseModel):
    customer_ids: list[int] = Field(..., min_length=1, max_length=200)
    to_managementor_id: int
    reason: str


class CustomerExtendCreate(BaseModel):
    sales_revenue: float = Field(..., gt=0)
    total_assets: float = Field(..., gt=0)
    people_engaged: float = Field(..., gt=0)
    data_date: date


class CustomerExtendItem(BaseModel):
    id: int
    sales_revenue: float
    total_assets: float
    people_engaged: float
    data_date: date
    typing: Literal[10, 20, 30, 40, 90]


class ClassificationChange(BaseModel):
    classification: Literal[10, 20, 30, 40, 50]
    reason: str


class ShareholderCreate(BaseModel):
    shareholder_name: str = Field(..., max_length=128)
    invested_amount: float = 0
    shareholding_ratio: float = Field(..., ge=0, le=100)


class DirectorCreate(BaseModel):
    director_name: str = Field(..., max_length=128)


class DirectorOrderReq(BaseModel):
    ordered_ids: list[int]


class SpouseBindReq(BaseModel):
    spouse_customer_id: int


class ControlerChangeReq(BaseModel):
    controler_id: int


class CustomerDetail(CustomerListItem):
    company: dict | None = None
    personal: dict | None = None
    group: dict | None = None
    core_info: CoreInfoBrief | None = None
    custom_flow: float
    custom_accept: float
    custom_back: float
    entrusted_loan: float
    last_synced_at: datetime | None
    shareholder_count: int
    director_count: int
    extend_count: int
    classification_display: str
    g_radio: float
    v_radio: float
    pending_requests: list[dict] | None = None
    latest_extend: CustomerExtendItem | None = None
    tags: list[int] | None = None
    created_at: datetime


class CustomerDictItem(BaseModel):
    id: int
    name: str
    short_name: str
    genre: int
    is_core: bool
    is_acceptor: bool
    custom_state: int
    managementor_name: str | None = None


class CustomerOverview(BaseModel):
    total_count: int
    active_count: int
    core_count: int
    acceptor_count: int
    total_credit_amount: float
    total_amount: float
    classification_distribution: dict[str, int]


class IndustryChartData(BaseModel):
    industry_name: str
    count: int
    total_amount: float
