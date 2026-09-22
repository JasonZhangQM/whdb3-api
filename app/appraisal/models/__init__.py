"""评审模块模型：5 张表。

设计决策：
- P2 FK CASCADE/RESTRICT 分层；FK 列不显式建索引
- P4 专家类别（ExpertCategory）2026-09-21 删除——专家类型改走枚举 expert_type
  （10内部/20外部），不再维护独立字典表，迁移 e5f7a9b1c3d4 drop FK + drop table
- 评审模块写项目状态（appraisal_articles/finish）是合理的——评审是评审流程 owner

AGENTS.md §4.1 对齐：
- 软删用 DateTime（deleted_at DATETIME NULL），禁止 String 模拟
- 时间字段统一 datetime，不用 Date 存非纯日期场景
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Appraisal(Base):
    """评审会。"""

    __tablename__ = "appraisals"

    num: Mapped[str] = mapped_column(String(32), unique=True, comment="评审会编号 年-次序")
    year: Mapped[int] = mapped_column(comment="评审年份")
    seq: Mapped[int] = mapped_column(comment="评审次序:年份内递增")
    review_model: Mapped[int] = mapped_column(SmallInteger, comment="评审类型:ReviewModel")
    review_date: Mapped[Date] = mapped_column(Date, comment="评审日期")
    compere_id: Mapped[int | None] = mapped_column(ForeignKey("appraisal_experts.id"), comment="主持人(评审委员)")
    meeting_state: Mapped[int] = mapped_column(SmallInteger, default=10, index=True, comment="状态:MeetingState")

    __table_args__ = (
        UniqueConstraint("year", "seq", "review_model", name="uq_appraisal_year_seq_model"),
        Index("idx_appraisal_created_at", "created_at"),
    )


class AppraisalArticle(Base):
    """评审会 ↔ 项目 M2M。"""

    __tablename__ = "appraisal_articles"

    appraisal_id: Mapped[int] = mapped_column(ForeignKey("appraisals.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))

    __table_args__ = (
        UniqueConstraint("appraisal_id", "article_id", name="uq_appraisal_article"),
    )


class AppraisalComment(Base):
    """评委意见（article + expert 唯一）。"""

    __tablename__ = "appraisal_comments"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    expert_id: Mapped[int] = mapped_column(ForeignKey("appraisal_experts.id"))
    comment: Mapped[int] = mapped_column(SmallInteger, default=0, comment="意见:CommentType")
    detail: Mapped[str | None] = mapped_column(Text, comment="意见详情")

    __table_args__ = (
        UniqueConstraint("article_id", "expert_id", name="uq_comment_article_expert"),
    )


class AppraisalExpert(Base):
    """评审专家。"""

    __tablename__ = "appraisal_experts"

    name: Mapped[str] = mapped_column(String(64), comment="姓名")
    org_name: Mapped[str | None] = mapped_column(String(128), comment="单位")
    title: Mapped[str | None] = mapped_column(String(64), comment="职务")
    expert_type: Mapped[int] = mapped_column(SmallInteger, comment="类别:ExpertType")
    contact_numb: Mapped[str | None] = mapped_column(String(16), comment="联系电话")
    email: Mapped[str | None] = mapped_column(String(64), comment="邮箱")
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="状态:True启用/False停用")
    sort: Mapped[int] = mapped_column(default=1, comment="排序")


class AppraisalSupply(Base):
    """补调问题（旧系统无完成状态，新增强）。"""

    __tablename__ = "appraisal_supplies"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    supply_detail: Mapped[str] = mapped_column(Text, comment="补调问题")
    is_resolved: Mapped[bool] = mapped_column(default=False, comment="是否已解决")
    resolve_reply: Mapped[str | None] = mapped_column(Text, comment="补调回复")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, comment="完成登记时间")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="解决登记人")
    supplier_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), comment="补调创建人")
