"""机构模块 Schemas。"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ===== 机构主表 =====
class ContactCreate(BaseModel):
    name: str = Field(..., max_length=32)
    job: str | None = None
    phone: str = Field(..., max_length=16)
    email: str | None = None
    is_primary: bool = False
    remark: str | None = None


class ContactItem(ContactCreate):
    id: int
    created_by_name: str


class BranchCreate(BaseModel):
    name: str = Field(..., max_length=128)
    short_name: str = Field(..., max_length=32)
    branch_addr: str | None = None
    contact_num: str | None = None


class BranchItem(BranchCreate):
    id: int
    status: Literal[10, 20, 90]
    status_display: str
    created_by_name: str


class BranchUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    branch_addr: str | None = None
    contact_num: str | None = None
    status: Literal[10, 20, 90] | None = None


class AgreementBrief(BaseModel):
    id: int
    agreement_type: int
    agreement_type_display: str
    flow_credit: float
    back_credit: float
    valid_begin_date: date
    valid_end_date: date
    status: int
    status_display: str


class AgreementDetail(AgreementBrief):
    flow_limit: float
    back_limit: float
    entrusted_credit: float | None
    remark: str | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime


class AgreementCreate(BaseModel):
    agreement_type: Literal[10, 20, 30, 40]
    flow_credit: float = 0
    flow_limit: float = 0
    back_credit: float = 0
    back_limit: float = 0
    entrusted_credit: float | None = None
    valid_begin_date: date
    valid_end_date: date
    remark: str | None = None


class AgreementUpdate(BaseModel):
    flow_credit: float | None = None
    flow_limit: float | None = None
    back_credit: float | None = None
    back_limit: float | None = None
    valid_end_date: date | None = None
    status: Literal[10, 20, 30, 90] | None = None
    remark: str | None = None


class InstitutionListItem(BaseModel):
    id: int
    name: str
    short_name: str
    institution_type: int
    institution_type_display: str
    institution_subtype: int | None
    institution_subtype_display: str | None
    legal_representative: str | None
    contact_num: str | None
    current_agreement: AgreementBrief | None
    used_flow: float
    used_accept: float
    used_back: float
    used_entrusted: float
    used_amount: float
    last_synced_at: datetime | None
    contact_count: int
    branch_count: int
    status: int
    status_display: str
    created_by_name: str
    created_at: datetime


class InstitutionDetail(InstitutionListItem):
    credit_code: str | None
    registered_addr: str | None
    contact_addr: str | None
    email: str | None
    up_scale: float | None
    updated_at: datetime
    contacts: list[ContactItem]
    branches: list[BranchItem]
    agreements: list[AgreementDetail]


class InstitutionCreate(BaseModel):
    name: str = Field(..., max_length=128)
    short_name: str = Field(..., max_length=32)
    institution_type: Literal[10, 20, 30, 40, 50, 90]
    institution_subtype: int | None = None
    credit_code: str | None = None
    legal_representative: str | None = None
    registered_addr: str | None = None
    contact_addr: str | None = None
    contact_num: str | None = None
    email: str | None = None
    up_scale: float | None = None
    contacts: list[ContactCreate] = []


class InstitutionUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    institution_subtype: int | None = None
    credit_code: str | None = None
    legal_representative: str | None = None
    registered_addr: str | None = None
    contact_addr: str | None = None
    contact_num: str | None = None
    email: str | None = None
    up_scale: float | None = None


class InstitutionStatusUpdate(BaseModel):
    status: Literal[10, 20, 90]
    reason: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    job: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool | None = None
    remark: str | None = None


class CreditHistoryItem(BaseModel):
    id: int
    agreement_id: int | None
    agreement_type_display: str | None
    change_type: int
    change_type_display: str
    change_content: dict
    changed_by_name: str
    created_at: datetime


class InstitutionOverview(BaseModel):
    total_count: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    total_flow_credit: float
    total_back_credit: float
    active_agreement_count: int


class BalanceSummary(BaseModel):
    institution_id: int
    institution_name: str
    used_flow: float
    used_accept: float
    used_back: float
    used_entrusted: float
    used_amount: float
