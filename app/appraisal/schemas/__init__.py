"""评审模块 Schemas。"""

from datetime import date

from pydantic import BaseModel, Field


class AppraisalCreate(BaseModel):
    """创建评审会。"""
    review_model: int
    review_date: date
    compere_id: int | None = None
    article_ids: list[int] = Field(default_factory=list)


class AppraisalArrange(BaseModel):
    """排会：添加/移除项目。"""
    article_ids: list[int] = Field(min_length=1)


class AppraisalFinish(BaseModel):
    """会议完成。"""
    finish_date: date | None = None


class CommentBatchCreate(BaseModel):
    """批量录入评委意见。"""
    items: list["CommentItem"]


class CommentItem(BaseModel):
    expert_id: int
    comment: int = Field(..., ge=0, le=30)
    detail: str | None = None


class AppraisalExpertCreate(BaseModel):
    """新增评审专家。v1.9：category_id 已删除。"""
    name: str = Field(max_length=64)
    org_name: str | None = Field(default=None, max_length=128)
    title: str | None = None
    expert_type: int
    contact_numb: str | None = None
    email: str | None = None
    remark: str | None = None


class SupplyCreate(BaseModel):
    """添加补调问题。"""
    supply_detail: str = Field(min_length=1)


class SupplyResolve(BaseModel):
    """补调完成登记。"""
    resolve_reply: str = Field(min_length=1)


class SupplyUpdate(BaseModel):
    """补调修改（#26 PATCH）。

    - supply_detail: 改问题描述（可选）
    - reopen: 补调重开（可选，设为 true 时 is_resolved→false）
    两者至少传一个。
    """
    supply_detail: str | None = Field(default=None, min_length=1)
    reopen: bool | None = None


class SummaryUpdate(BaseModel):
    """纪要编辑。"""
    summary: str | None = None
    opinion: str | None = None


class ExpertSortItem(BaseModel):
    """拖拽排序单项。"""
    id: int
    sort: int


class ExpertSortBatch(BaseModel):
    """批量排序请求体（#17 PUT）。"""
    items: list[ExpertSortItem]
