"""客户模块模型：14 张表。

核心设计（§4.3）：
- 强外键替代弱关联（核心企业/承兑人 FK customers.id）
- 集团/授信区域独立聚合维度
- 冗余统计字段定位为列表页缓存（§4.4 分层混合）
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Region(Base):
    """行政区域树（省/市/区县/乡镇街道，6 位国标行政区划代码）。"""

    __tablename__ = "customer_regions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, comment="行政区划代码")
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(SmallInteger, comment="10省20市30区县40乡镇街道")
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    ordery: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10启用20停用")


class CreditRegion(Base):
    """授信区域（地方平台区域授信，树形）。"""

    __tablename__ = "customer_credit_regions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="区域授信总额度")
    used_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已用额度(冗余,异步刷新)")
    platform_name: Mapped[str | None] = mapped_column(String(128), comment="平台名称")
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10启用20停用")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


class Industry(Base):
    """国民经济行业分类树。"""

    __tablename__ = "customer_industries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    ind_typ: Mapped[int] = mapped_column(SmallInteger, comment="10一产20二产30三产")
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True)


class ExtraTag(Base):
    """额外标签字典（行业/业务标签）。"""

    __tablename__ = "customer_extra_tags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    type: Mapped[int] = mapped_column(SmallInteger, comment="10行业20业务标签")
    status: Mapped[int] = mapped_column(SmallInteger, default=10)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


class Group(Base):
    """集团（聚合多个企业客户，parent_customer_id 指向母公司客户）。"""

    __tablename__ = "customer_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    parent_customer_id: Mapped[int | None] = mapped_column(
        # use_alter：customers.group_id ↔ customer_groups.parent_customer_id 循环依赖，
        # 该约束改为建表后 ALTER 添加（MySQL 不允许引用未建表）
        ForeignKey("customers.id", name="fk_group_parent_customer", use_alter=True),
        index=True,
        comment="母公司客户",
    )
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="集团总授信额度")
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(SmallInteger, default=10)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


class Customer(Base):
    """客户主表。"""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    short_name: Mapped[str] = mapped_column(String(32), unique=True)
    genre: Mapped[int] = mapped_column(SmallInteger, index=True, comment="1企业2个人")
    custom_typ: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10新增20存量30存量新增")
    custom_state: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10正常20反担保30小贷90注销"
    )
    contact_addr: Mapped[str | None] = mapped_column(String(255))
    linkman: Mapped[str | None] = mapped_column(String(64))
    contact_num: Mapped[str | None] = mapped_column(String(64))
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_regions.id"), index=True, comment="行政区域"
    )
    credit_region_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_credit_regions.id"), index=True, comment="授信区域"
    )
    industry_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_industries.id"), comment="国民经济行业"
    )
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_groups.id"), index=True, comment="所属集团"
    )
    is_core: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="票据核心企业")
    is_acceptor: Mapped[bool] = mapped_column(Boolean, default=False, index=True, comment="票据承兑人")
    managementor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, comment="管护经理"
    )
    controler_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="风控专员")
    create_by: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="创建人")
    # 核心企业专属
    core_rate: Mapped[float | None] = mapped_column(Numeric(6, 2), comment="核心企业费率%")
    core_remark: Mapped[str | None] = mapped_column(String(255), comment="核心企业备注")
    # 冗余统计（列表页缓存，异步刷新）
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="授信总额")
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="在保总额")
    custom_flow: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="流贷余额")
    custom_accept: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="承兑余额")
    custom_back: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="保函余额")
    entrusted_loan: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="委贷余额")
    g_value: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="反担保价值")
    g_radio: Mapped[float] = mapped_column(Numeric(8, 2), default=0, comment="授信覆盖率%")
    v_radio: Mapped[float] = mapped_column(Numeric(8, 2), default=0, comment="在保覆盖率%")
    classification: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="五级分类"
    )
    # 最新经营数据快照
    sales_revenue: Mapped[float | None] = mapped_column(Numeric(18, 2))
    total_assets: Mapped[float | None] = mapped_column(Numeric(18, 2))
    people_engaged: Mapped[float | None] = mapped_column(Numeric(12, 2))
    data_date: Mapped[date | None] = mapped_column(comment="快照基准日")
    last_provide_date: Mapped[date | None] = mapped_column(comment="最近放款")
    last_review_date: Mapped[date | None] = mapped_column(comment="最近保后")
    day_space: Mapped[int] = mapped_column(BigInteger, default=0, comment="距上次更新间隔日")
    last_synced_at: Mapped[datetime | None] = mapped_column(comment="冗余字段最后刷新时间")
    tags: Mapped[list | None] = mapped_column(JSON, comment="标签 id 数组")
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


class CompanyProfile(Base):
    """企业客户扩展（OneToOne）。"""

    __tablename__ = "customer_company_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), unique=True, index=True
    )
    credit_code: Mapped[str] = mapped_column(String(32), unique=True, comment="统一社会信用代码")
    decisionor: Mapped[int | None] = mapped_column(SmallInteger, comment="决策机构")
    custom_nature: Mapped[int | None] = mapped_column(SmallInteger, comment="企业性质")
    industry_c: Mapped[int | None] = mapped_column(BigInteger, comment="工信部划分行业")
    typing: Mapped[int] = mapped_column(SmallInteger, default=90, comment="企业划型")
    capital: Mapped[float | None] = mapped_column(Numeric(18, 2), comment="注册资本")
    paid_capital: Mapped[float | None] = mapped_column(Numeric(18, 2), comment="实收资本")
    registered_addr: Mapped[str | None] = mapped_column(String(255))
    representative: Mapped[str | None] = mapped_column(String(64), comment="法人代表")


class PersonalProfile(Base):
    """个人客户扩展（OneToOne）。"""

    __tablename__ = "customer_personal_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), unique=True, index=True
    )
    license_num: Mapped[str] = mapped_column(String(18), unique=True, comment="身份证号")
    license_addr: Mapped[str | None] = mapped_column(String(255))
    marital_status: Mapped[int | None] = mapped_column(SmallInteger, comment="婚姻状态")
    household_nature: Mapped[int | None] = mapped_column(SmallInteger, comment="户籍性质")
    spouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), comment="配偶（双向指向另一条个人客户）"
    )


class Shareholder(Base):
    """股东（挂在企业扩展下）。"""

    __tablename__ = "customer_shareholders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("customer_company_profiles.id"), index=True
    )
    shareholder_name: Mapped[str] = mapped_column(String(128))
    invested_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), comment="投资额")
    shareholding_ratio: Mapped[float] = mapped_column(Numeric(8, 4), comment="持股比例%")

    __table_args__ = (
        UniqueConstraint("company_id", "shareholder_name", name="uq_shareholder"),
    )


class Director(Base):
    """董事。"""

    __tablename__ = "customer_directors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("customer_company_profiles.id"), index=True
    )
    director_name: Mapped[str] = mapped_column(String(128))
    ordery: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        UniqueConstraint("company_id", "director_name", name="uq_director"),
    )


class CustomerExtend(Base):
    """经营信息快照（按年度多条历史）。"""

    __tablename__ = "customer_extends"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    sales_revenue: Mapped[float] = mapped_column(Numeric(18, 2), comment="销售收入")
    total_assets: Mapped[float] = mapped_column(Numeric(18, 2), comment="总资产")
    people_engaged: Mapped[float] = mapped_column(Numeric(12, 2), comment="从业人数")
    data_date: Mapped[date] = mapped_column(comment="快照基准日")
    typing: Mapped[int] = mapped_column(SmallInteger, default=90, comment="划型结果")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("customer_id", "data_date", name="uq_extend_date"),
    )


class CoreLimit(Base):
    """核心企业授信额度（多条含历史，FK customers.id）。"""

    __tablename__ = "customer_core_limits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 2), comment="授信总额")
    valid_begin_date: Mapped[date]
    valid_end_date: Mapped[date]
    used_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已占用额")
    remaining_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="剩余额")
    status: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10生效20失效30已用完"
    )
    remark: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("customer_id", "valid_begin_date", name="uq_core_limit_date"),
    )


class CoreHistory(Base):
    """核心企业变更历史。"""

    __tablename__ = "customer_core_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    change_content: Mapped[dict] = mapped_column(JSON)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )
