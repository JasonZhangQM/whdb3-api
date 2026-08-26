"""机构模块模型：主表 / 联系人 / 分支机构 / 授信协议 / 额度历史。

冗余余额（used_*）定位为列表页缓存（§4.4 分层混合），异步刷新。
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


class Institution(Base):
    """机构主表：统一管理所有外部机构。"""

    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, comment="机构全称")
    short_name: Mapped[str] = mapped_column(String(32), unique=True, comment="简称")
    institution_type: Mapped[int] = mapped_column(
        SmallInteger, index=True, comment="10银行20担保30律所40评估50会计师90其他"
    )
    institution_subtype: Mapped[int | None] = mapped_column(
        SmallInteger, comment="银行子类型"
    )
    credit_code: Mapped[str | None] = mapped_column(String(32), comment="统一社会信用代码")
    legal_representative: Mapped[str | None] = mapped_column(String(64), comment="法人代表")
    registered_addr: Mapped[str | None] = mapped_column(String(255), comment="注册地址")
    contact_addr: Mapped[str | None] = mapped_column(String(255), comment="联系地址")
    contact_num: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(128))
    up_scale: Mapped[float | None] = mapped_column(
        Numeric(6, 2), comment="最高额上浮比例%（银行类）"
    )
    # 冗余余额（列表页缓存角色，异步刷新，容忍短暂偏差）
    used_flow: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已用流贷余额")
    used_accept: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已用承兑余额")
    used_back: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="已用保函余额")
    used_entrusted: Mapped[float] = mapped_column(
        Numeric(18, 2), default=0, comment="已用委贷余额"
    )
    used_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="在保总额")
    last_synced_at: Mapped[datetime | None] = mapped_column(
        comment="冗余字段最后刷新时间"
    )
    status: Mapped[int] = mapped_column(SmallInteger, default=10, index=True, comment="10正常20停用90注销")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )


class InstitutionContact(Base):
    """机构联系人（1:N）。"""

    __tablename__ = "institution_contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(32))
    job: Mapped[str | None] = mapped_column(String(64), comment="职务")
    phone: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(128))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, comment="首选联系人")
    remark: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_contact_inst_name"),
    )


class InstitutionBranch(Base):
    """分支机构/网点（银行类专用，1:N）。"""

    __tablename__ = "institution_branches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    short_name: Mapped[str] = mapped_column(String(32))
    branch_addr: Mapped[str | None] = mapped_column(String(255))
    contact_num: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[int] = mapped_column(SmallInteger, default=10, index=True, comment="10正常20停用90注销")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_branch_inst_name"),
    )


class InstitutionCreditAgreement(Base):
    """授信/合作协议（1:N，含历史）。"""

    __tablename__ = "institution_credit_agreements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    agreement_type: Mapped[int] = mapped_column(
        SmallInteger, index=True, comment="10综合授信20保函授信30服务协议40委贷协议"
    )
    flow_credit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="综合额度")
    flow_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="单笔限额-综合")
    back_credit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="保函额度")
    back_limit: Mapped[float] = mapped_column(Numeric(18, 2), default=0, comment="单笔限额-保函")
    entrusted_credit: Mapped[float | None] = mapped_column(Numeric(18, 2), comment="委贷额度")
    valid_begin_date: Mapped[date]
    valid_end_date: Mapped[date]
    status: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10生效20失效30已用完90已终止"
    )
    remark: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index("idx_agreement_inst_status_type", "institution_id", "status", "agreement_type"),
    )


class InstitutionCreditHistory(Base):
    """机构额度变更历史。"""

    __tablename__ = "institution_credit_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    agreement_id: Mapped[int | None] = mapped_column(
        ForeignKey("institution_credit_agreements.id"), comment="关联协议"
    )
    change_type: Mapped[int] = mapped_column(
        SmallInteger, comment="10新增协议20额度调整30协议到期40余额刷新"
    )
    change_content: Mapped[dict] = mapped_column(JSON, comment="{field,before,after,...}")
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))
