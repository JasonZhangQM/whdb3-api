"""项目模块模型：9 张表。

设计决策（AGENTS.md 对齐）：
- A2 FK ondelete 分层：子表→聚合根用 CASCADE；子表→字典/用户用 RESTRICT
- A2 FK 列不显式建索引（MySQL 自动隐式创建）
- A12 lending_orders 不设缓存字段（避免冗余的冗余）
- 所有表继承 Base（自带 id/created_by/created_at/updated_at）
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Article(Base):
    """项目主表。"""

    __tablename__ = "articles"

    # === 业务字段 ===
    article_num: Mapped[str] = mapped_column(String(32), unique=True, comment="项目编号")
    article_state: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="项目状态机"
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), comment="客户"
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("article_products.id", ondelete="RESTRICT"), comment="产品类型"
    )
    renewal: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="续贷金额"
    )
    augment: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=0, comment="新增金额"
    )
    # amount = renewal + augment — 后端计算，不落库
    credit_term: Mapped[int] = mapped_column(SmallInteger, default=12, comment="授信期限(月)")
    repay_method: Mapped[int | None] = mapped_column(SmallInteger, comment="还款方式")
    director_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="项目经理"
    )
    assistant_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="项目助理"
    )
    control_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="风控专员"
    )

    # === 评审/签批信息 ===
    review_date: Mapped[date | None] = mapped_column(Date, comment="上会日期(评审模块写入)")
    summary_num: Mapped[str | None] = mapped_column(
        String(32), unique=True, comment="纪要编号(评审模块生成)"
    )
    summary: Mapped[str | None] = mapped_column(Text, comment="纪要")
    opinion: Mapped[str | None] = mapped_column(Text, comment="项目意见")
    rcd_opinion: Mapped[str | None] = mapped_column(Text, comment="风控部意见(签批时录入)")
    convenor_opinion: Mapped[str | None] = mapped_column(Text, comment="招集人意见")
    sign_detail: Mapped[str | None] = mapped_column(Text, comment="签批人意见")
    sign_type: Mapped[int | None] = mapped_column(SmallInteger, comment="签批结论 1同意 2不同意")
    sign_date: Mapped[date | None] = mapped_column(Date, comment="签批日期")

    # === 列表缓存（分层混合：详情页实时统计覆盖） ===
    notify_sum: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="通知金额(缓存)")
    provide_sum: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="放款金额(缓存)")
    repayment_sum: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="还款金额(缓存)")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="在保余额(缓存)")

    # === 业务索引（仅业务筛选字段显式建；FK 索引 MySQL 自动隐式创建） ===
    __table_args__ = (
        Index("idx_article_created_at", "created_at"),
    )


class ArticleProduct(Base):
    """产品字典表（种子数据，只读）。"""

    __tablename__ = "article_products"

    name: Mapped[str] = mapped_column(String(64), unique=True, comment="产品名称")
    difficulty_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("1.00"), comment="难度系数"
    )
    sort: Mapped[int] = mapped_column(default=1)


class ArticleBorrower(Base):
    """共借人 M2M（项目 ↔ 客户）。"""

    __tablename__ = "article_borrowers"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint("article_id", "customer_id", name="uq_borrower_article_customer"),
    )


class ArticleFeedback(Base):
    """风控反馈（每项目一份，upsert）。"""

    __tablename__ = "article_feedbacks"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True
    )
    propose: Mapped[int | None] = mapped_column(SmallInteger, comment="上会建议")
    analysis: Mapped[str | None] = mapped_column(Text, comment="风险分析")
    suggestion: Mapped[str | None] = mapped_column(Text, comment="风控意见")
    submitted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), comment="提交人"
    )
    submitted_at: Mapped[date | None] = mapped_column(Date, comment="提交日期")


class ArticleMortgageExt(Base):
    """房抵保扩展（仅 product=房抵保 的项目，唯一）。"""

    __tablename__ = "article_mortgage_exts"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), unique=True
    )
    product_type: Mapped[str | None] = mapped_column(String(64), comment="业务品种")
    provide_bank: Mapped[str | None] = mapped_column(String(64), comment="放款银行")
    credit_type: Mapped[str | None] = mapped_column(String(64), comment="授信类型")
    custom_unit: Mapped[str | None] = mapped_column(String(128), comment="申请单位")
    provide_term: Mapped[str | None] = mapped_column(String(32), comment="放款期限")
    entity_name: Mapped[str | None] = mapped_column(String(128), comment="主体名称")
    entity_owner: Mapped[str | None] = mapped_column(String(64), comment="主体所有人")
    owner_link: Mapped[str | None] = mapped_column(String(64), comment="与借款人关系")
    license_type: Mapped[str | None] = mapped_column(String(64), comment="证照类型")
    license_no: Mapped[str | None] = mapped_column(String(64), comment="证照号")
    register_date: Mapped[date | None] = mapped_column(Date, comment="登记日期")
    register_addr: Mapped[str | None] = mapped_column(String(255), comment="登记地址")
    industry_c: Mapped[str | None] = mapped_column(String(64), comment="行业")
    mate_unit: Mapped[str | None] = mapped_column(String(128), comment="配偶单位")
    ownership_structure: Mapped[dict | None] = mapped_column(
        JSON, comment="股东结构（动态行，允许 JSON）"
    )


class ArticleSingleQuota(Base):
    """单项额度（article + credit_model 唯一）。"""

    __tablename__ = "article_single_quotas"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    credit_model: Mapped[int] = mapped_column(SmallInteger, comment="授信类型")
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    flow_rate: Mapped[str | None] = mapped_column(Text, comment="费率（文本）")
    remark: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("article_id", "credit_model", name="uq_single_quota_article_model"),
    )


class ArticleLendingOrder(Base):
    """放款次序（article + seq 唯一）。

    注：旧方案每个次序有 provide_sum/repayment_sum/balance 三个缓存。
    设计决策 A12 删除——放款数据量不大，次序缓存实时 SUM 即可。
    """

    __tablename__ = "article_lending_orders"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(SmallInteger, comment="发放次序 1-5")
    order_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, comment="拟放金额")
    remark: Mapped[str | None] = mapped_column(Text)
    state: Mapped[int] = mapped_column(
        SmallInteger, default=40, comment="次序状态（跟随项目状态机）"
    )

    __table_args__ = (
        UniqueConstraint("article_id", "seq", name="uq_lending_order_article_seq"),
    )


class ArticleSure(Base):
    """反担保措施（项目级）。

    注：article_id + sure_type 唯一——每类型一条，update_or_create 语义。
    抵质押/监管/预售类通过 article_warrant_bindings 关联权证（复用权证模块）。
    """

    __tablename__ = "article_sures"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    sure_type: Mapped[int] = mapped_column(SmallInteger, comment="反担保类型")
    remark: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("article_id", "sure_type", name="uq_sure_article_type"),
    )


class ArticleSureCustomer(Base):
    """保证类反担保人 M2M（sure_id ↔ customer_id）。"""

    __tablename__ = "article_sure_customers"

    sure_id: Mapped[int] = mapped_column(
        ForeignKey("article_sures.id", ondelete="CASCADE")
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint("sure_id", "customer_id", name="uq_sure_customer_sure_customer"),
    )


class ArticleChange(Base):
    """项目变更历史。"""

    __tablename__ = "article_changes"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE")
    )
    change_view: Mapped[int] = mapped_column(SmallInteger, comment="变更结论")
    change_detail: Mapped[str | None] = mapped_column(Text, comment="变更详情")
    change_date: Mapped[date | None] = mapped_column(Date, comment="变更日期")
