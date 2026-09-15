"""项目模块 Schemas。"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class ArticleCreate(BaseModel):
    """创建项目。"""
    customer_id: int
    product_id: int
    renewal: Decimal = Decimal("0")
    augment: Decimal = Decimal("0")
    credit_term: int = Field(default=1, ge=1)
    credit_term_unit: int = Field(default=10)
    director_id: int
    assistant_id: int | None = None
    control_id: int | None = None
    borrower_ids: list[int] = Field(default_factory=list)


class ArticleUpdate(BaseModel):
    """修改项目（允许的自由字段）。"""
    renewal: Decimal | None = None
    augment: Decimal | None = None
    credit_term: int | None = Field(default=None, ge=1)
    credit_term_unit: int | None = None
    director_id: int | None = None
    assistant_id: int | None = None
    control_id: int | None = None
    borrower_ids: list[int] | None = None


class ArticleItem(BaseModel):
    """列表项。"""
    id: int
    article_num: str
    article_state: int
    article_state_display: str | None = None
    customer_id: int
    customer_name: str | None = None
    product_id: int
    product_name: str | None = None
    renewal: Decimal
    augment: Decimal
    credit_term: int
    credit_term_unit: int
    credit_term_unit_display: str | None = None
    director_id: int
    director_name: str | None = None
    assistant_id: int | None = None
    assistant_name: str | None = None
    control_id: int | None = None
    control_name: str | None = None
    balance: Decimal
    notify_sum: Decimal
    provide_sum: Decimal
    repayment_sum: Decimal
    sign_date: date | None = None
    created_at: str | None = None
    created_by_name: str | None = None


class ArticleDetail(ArticleItem):
    """详情（含更多字段，扁平化）。"""
    summary_num: str | None = None
    summary: str | None = None
    opinion: str | None = None
    rcd_opinion: str | None = None
    convenor_opinion: str | None = None
    sign_detail: str | None = None
    sign_type: int | None = None
    review_date: date | None = None


class FeedbackCreate(BaseModel):
    """风控反馈。"""
    propose: int | None = None
    analysis: str | None = None
    suggestion: str | None = None


class SignRequestCreate(BaseModel):
    """发起签批。"""
    sign_type: int = Field(..., description="1同意 2不同意")
    renewal: Decimal
    augment: Decimal
    credit_amount: Decimal = Decimal("0")
    g_value: Decimal = Decimal("0")
    rcd_opinion: str | None = None
    convenor_opinion: str | None = None
    sign_detail: str | None = None
    sign_date: date


class ChangeRequestCreate(BaseModel):
    """发起变更。"""
    change_detail: str
    change_date: date | None = None


class SureCreate(BaseModel):
    """反担保措施（按放款次序 upsert）。

    旧系统对应 LendingSures + LendingCustoms + LendingWarrants。
    """

    lending_order_id: int = Field(..., description="放款次序 ID（article_order.id）")
    sure_type: int
    remark: str | None = None
    customer_ids: list[int] = Field(default_factory=list)  # 保证类
    warrant_ids: list[int] = Field(default_factory=list)   # 抵质押类


class SingleQuotaCreate(BaseModel):
    """单项额度。"""
    credit_model: int
    credit_amount: Decimal
    flow_rate: str | None = None
    remark: str | None = None


class LendingOrderCreate(BaseModel):
    """放款次序。"""
    seq: int = Field(..., ge=1, le=5)
    order_amount: Decimal
    remark: str | None = None


class LendingOrderUpdate(BaseModel):
    """放款次序部分更新（仅支持金额 + 备注，次序序号不允许改）。"""
    order_amount: Decimal | None = None
    remark: str | None = None


# ---------- Response models（仅供列表聚合返回，不作为请求体）----------

class SureResponse(BaseModel):
    """反担保措施嵌套结构（含保证人 / 抵质押物名称，供详情 Tab 渲染）。"""
    sure_type: int
    sure_type_display: str
    remark: str | None = None
    # 保证类：客户 ID + 名称
    customer_ids: list[int] = []
    customer_names: list[str] = []
    # 抵质押类：权证 ID + 名称
    warrant_ids: list[int] = []
    warrant_names: list[str] = []


class LendingOrderResponse(BaseModel):
    """放款次序嵌套（含该次序下的反担保措施列表）。"""
    id: int
    seq: int
    order_amount: Decimal
    state: int
    remark: str | None = None
    sures: list[SureResponse] = []
