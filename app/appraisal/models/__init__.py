"""评审模块模型：6 张表。

设计决策：
- P2 FK CASCADE/RESTRICT 分层；FK 列不显式建索引
- P4 专家类别降为只读字典（appraisal_expert_categories 保留表，接口只读）
- 评审模块写项目状态（appraisal_articles/finish）是合理的——评审是评审流程 owner
"""

from sqlalchemy import (
    Date,
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
    seq: Mapped[int] = mapped_column(comment="评审次序（年份内递增）")
    review_model: Mapped[int] = mapped_column(
        SmallInteger, comment="评审类型"
    )
    review_date: Mapped[Date] = mapped_column(Date, comment="评审日期")
    compere_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="主持人"
    )
    meeting_state: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10待上会/20已上会"
    )

    __table_args__ = (
        UniqueConstraint("year", "seq", "review_model", name="uq_appraisal_year_seq_model"),
        Index("idx_appraisal_created_at", "created_at"),
    )


class AppraisalArticle(Base):
    """评审会 ↔ 项目 M2M。"""

    __tablename__ = "appraisal_articles"

    appraisal_id: Mapped[int] = mapped_column(
        ForeignKey("appraisals.id", ondelete="CASCADE")
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint("appraisal_id", "article_id", name="uq_appraisal_article"),
    )


class AppraisalComment(Base):
    """评委意见（article + expert 唯一）。"""

    __tablename__ = "appraisal_comments"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    expert_id: Mapped[int] = mapped_column(
        ForeignKey("appraisal_review_experts.id", ondelete="RESTRICT")
    )
    comment_type: Mapped[int] = mapped_column(
        SmallInteger, default=0, comment="0未发表/10同意/20复议/30不同意"
    )
    concrete: Mapped[str | None] = mapped_column(Text, comment="意见详情")

    __table_args__ = (
        UniqueConstraint("article_id", "expert_id", name="uq_comment_article_expert"),
    )


class ReviewExpert(Base):
    """评审专家。"""

    __tablename__ = "appraisal_review_experts"

    name: Mapped[str] = mapped_column(String(64), comment="姓名")
    title: Mapped[str | None] = mapped_column(String(64), comment="职务")
    org_name: Mapped[str | None] = mapped_column(String(128), comment="挂靠单位（文本快照）")
    expert_type: Mapped[int] = mapped_column(SmallInteger, comment="10内部/20外部")
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("appraisal_expert_categories.id", ondelete="RESTRICT"), comment="专家类别"
    )
    contact_numb: Mapped[str | None] = mapped_column(String(16), comment="联系电话")
    email: Mapped[str | None] = mapped_column(String(64), comment="邮箱")
    sort: Mapped[int] = mapped_column(default=1)
    status: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1启用/0停用(软删)")
    remark: Mapped[str | None] = mapped_column(String(255))
    deleted_at: Mapped[str | None] = mapped_column(String(32), comment="软删时间")


class AppraisalSupply(Base):
    """补调问题（旧系统无完成状态，新增强）。"""

    __tablename__ = "appraisal_supplies"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    supply_detail: Mapped[str] = mapped_column(Text, comment="补调问题")
    is_resolved: Mapped[bool] = mapped_column(default=False, comment="是否已解决")
    resolve_reply: Mapped[str | None] = mapped_column(Text, comment="补调回复")
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="解决登记人"
    )
    supplyor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="创建人"
    )


class ExpertCategory(Base):
    """专家类别（P4：降为只读字典，seed 数据）。"""

    __tablename__ = "appraisal_expert_categories"

    name: Mapped[str] = mapped_column(String(32), unique=True, comment="类别名称")
    sort: Mapped[int] = mapped_column(default=1)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
