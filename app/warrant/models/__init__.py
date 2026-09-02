"""权证模块模型：19 张表（M2 范围，他权/项目绑定随 M3 合同模块落地）。

核心设计（§0.1 / §0.3）：
- 所有权人统一走 warrant_ownerships 中间表（支持共有），消除旧系统两种模式
- warrants 主表 + 11 种类型扩展表（OneToOne，房产为 1:N 房产包模式）
- 他权（warrant_hypothecs）与项目绑定（article_warrant_bindings）依赖 agrees/articles 表，M3 建
"""

from datetime import date

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Warrant(Base):
    """担保物主表：基本信息 + 入库状态。

    评估历史走 warrant_evaluates 子表（含复核）；
    出入库走 warrant_storages 子表（含联动状态）；
    查封拍卖字段全部删除，后续如需独立评估/拍卖模块再建。
    """

    __tablename__ = "warrants"

    warrant_num: Mapped[str] = mapped_column(String(128), unique=True, comment="权证编号")
    warrant_type: Mapped[int] = mapped_column(SmallInteger, index=True, comment="1房产5土地6在建11应收21股权31票据41车辆51动产55其他99他权")
    remark: Mapped[str | None] = mapped_column(String(128), comment="备注")

    warrant_state: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10未入库20已入库30已加保60无需入库110续抵出库210已借出310解保出库410已移交990已注销"
    )


class WarrantOwnership(Base):
    """产权证/所有权人（统一中间表，支持多人按份共有）。"""

    __tablename__ = "warrant_ownerships"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    ownership_num: Mapped[str] = mapped_column(String(128), unique=True, comment="产权证编号（全局唯一）")
    owner_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    share_ratio: Mapped[float | None] = mapped_column(Numeric(5, 2), comment="共有份额%，null=独有")


    __table_args__ = (
        UniqueConstraint("warrant_id", "owner_id", name="uq_ownership_warrant_owner"),
    )


class WarrantHouse(Base):
    """房产（type=1，1:N 多套房产包模式）。"""

    __tablename__ = "warrant_houses"

    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    region_id: Mapped[int] = mapped_column(ForeignKey("user_regions.id", ondelete="RESTRICT"),comment="行政区域（必填，方便按区域统计）")
    house_locate: Mapped[str] = mapped_column(String(255), comment="详细地址（换证后同坐落可能出现多套证，不唯一）")
    house_app: Mapped[int] = mapped_column(BigInteger, comment="房产用途（字典）")
    house_area: Mapped[float] = mapped_column(Numeric(12, 2), comment="面积")
    house_name: Mapped[str | None] = mapped_column(String(128), comment="楼盘名")
    house_build_year: Mapped[int | None] = mapped_column(SmallInteger)
    house_usage: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10自用20出租30空置")



class WarrantGround(Base):
    """土地（type=5）。"""

    __tablename__ = "warrant_grounds"

    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    region_id: Mapped[int] = mapped_column(ForeignKey("user_regions.id", ondelete="RESTRICT"),comment="行政区域（必填，方便按区域统计）")
    ground_locate: Mapped[str] = mapped_column(String(255), comment="详细地址")
    ground_app: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="土地用途")
    ground_area: Mapped[float] = mapped_column(Numeric(12, 2))



class WarrantConstruction(Base):
    """在建工程（type=6）。"""

    __tablename__ = "warrant_constructions"

    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    region_id: Mapped[int] = mapped_column(ForeignKey("user_regions.id", ondelete="RESTRICT"),comment="行政区域（必填，方便按区域统计）")
    construct_locate: Mapped[str] = mapped_column(String(255), comment="详细地址")
    construct_app: Mapped[str] = mapped_column(String(128), comment="工程用途")
    construct_area: Mapped[float] = mapped_column(Numeric(12, 2))



class WarrantReceiveExtend(Base):
    """应收单位明细（直接关联权证主表）。"""

    __tablename__ = "warrant_receive_extends"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    receive_unit: Mapped[str] = mapped_column(String(128), comment="应收单位名称")


    __table_args__ = (
        UniqueConstraint("warrant_id", "receive_unit", name="uq_receive_extend_unit"),
    )


class WarrantStock(Base):
    """股权（type=21）。"""

    __tablename__ = "warrant_stocks"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"), unique=True)
    stock_type: Mapped[int] = mapped_column(SmallInteger, comment="10有限公司股权20股份公司股份30举办者权益")
    target: Mapped[str] = mapped_column(String(128), comment="标的公司")
    ratio: Mapped[float] = mapped_column(Numeric(5, 2), comment="持股%")
    registered_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    paid_capital: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    remark: Mapped[str | None] = mapped_column(String(255))



class WarrantDraftExtend(Base):
    """票据明细（关联核心企业/承兑人客户，直接关联权证主表）。"""

    __tablename__ = "warrant_draft_extends"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    draft_type: Mapped[int] = mapped_column(SmallInteger, comment="10电银承20银承11电商承12商承21支票")
    draft_num: Mapped[str] = mapped_column(String(128), comment="票据编号")
    acceptor_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), comment="承兑人"
    )
    core_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), comment="核心企业"
    )
    draft_amount: Mapped[float] = mapped_column(Numeric(18, 2))
    issue_date: Mapped[date]
    due_date: Mapped[date]
    draft_state: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True,
        comment="10未入库20已入库30已加保120已归还210置换出库310解保出库410托收出库990已注销",
    )

    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (Index("idx_draft_extend_num", "draft_num"),)


class WarrantVehicle(Base):
    """车辆（type=41）。"""

    __tablename__ = "warrant_vehicles"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"), unique=True)
    frame_num: Mapped[str] = mapped_column(String(64), unique=True, comment="车架号")
    plate_num: Mapped[str] = mapped_column(String(32), unique=True, comment="车牌号")
    vehicle_brand: Mapped[str] = mapped_column(String(64))
    remark: Mapped[str | None] = mapped_column(String(255))



class WarrantChattel(Base):
    """动产（type=51）。"""

    __tablename__ = "warrant_chattels"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"), unique=True)
    chattel_type: Mapped[int] = mapped_column(SmallInteger, comment="10存货20机器设备30医疗设备99动产")
    chattel_detail: Mapped[str] = mapped_column(String(255))



class WarrantOther(Base):
    """其他（type=55）。"""

    __tablename__ = "warrant_others"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"), unique=True)
    other_type: Mapped[int] = mapped_column(
        SmallInteger, comment="10购房合同20车辆合格证30专利40商标501软件著作权70账户99其他"
    )
    cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    other_detail: Mapped[str] = mapped_column(String(255))



class WarrantPatent(Base):
    """商标（other_type=40 时 OneToOne）。"""

    __tablename__ = "warrant_patents"


    other_id: Mapped[int] = mapped_column(ForeignKey("warrant_others.id", ondelete="CASCADE"), unique=True)
    patent_name: Mapped[str] = mapped_column(String(128))
    reg_num: Mapped[str] = mapped_column(String(64), unique=True)
    patent_ty: Mapped[int] = mapped_column(SmallInteger, comment="商标类型")



class WarrantSoftware(Base):
    """软件著作权（other_type=501 时 OneToOne）。"""

    __tablename__ = "warrant_softwares"


    other_id: Mapped[int] = mapped_column(ForeignKey("warrant_others.id", ondelete="CASCADE"), unique=True)
    software_name: Mapped[str] = mapped_column(String(128))
    reg_num: Mapped[str] = mapped_column(String(64), unique=True)



class WarrantStorage(Base):
    """出入库历史。"""

    __tablename__ = "warrant_storages"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    storage_type: Mapped[int] = mapped_column(
        SmallInteger, comment="10入库20续抵出库30已加保60无需入库110借出120归还310解保出库410移交990注销"
    )
    storage_explain: Mapped[str | None] = mapped_column(String(255))
    transfer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), comment="移交/接收者"
    )
    conservator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="权证管理岗")
    storage_date: Mapped[date]


class WarrantEvaluate(Base):
    """评估历史。"""

    __tablename__ = "warrant_evaluates"


    warrant_id: Mapped[int] = mapped_column(ForeignKey("warrants.id", ondelete="CASCADE"))
    evaluate_method: Mapped[int] = mapped_column(SmallInteger)
    evaluate_value: Mapped[float] = mapped_column(Numeric(18, 2))
    evaluate_date: Mapped[date]
    evaluate_explain: Mapped[str | None] = mapped_column(String(255))
    evaluate_company: Mapped[str | None] = mapped_column(String(128))



class WarrantEvaluateRecheck(Base):
    """评估复核（评估的延伸，OneToOne）。"""

    __tablename__ = "warrant_evaluate_rechecks"


    evaluate_id: Mapped[int] = mapped_column(ForeignKey("warrant_evaluates.id", ondelete="CASCADE"))
    check_value: Mapped[float] = mapped_column(Numeric(18, 2), comment="核查价值")
    recheck_value: Mapped[float] = mapped_column(Numeric(18, 2), comment="复核价值")
    recheck_channel: Mapped[str] = mapped_column(String(128), comment="复核渠道")
    remark: Mapped[str | None] = mapped_column(String(255))



class WarrantEvaluateCompany(Base):
    """评估公司字典。"""

    __tablename__ = "warrant_evaluate_companies"


    name: Mapped[str] = mapped_column(String(128), unique=True)



class WarrantHouseApp(Base):
    """房产用途字典（树形分类，替代旧系统 100+ 硬编码枚举）。"""

    __tablename__ = "warrant_house_apps"


    name: Mapped[str] = mapped_column(String(64))
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None, index=True)
    status: Mapped[int] = mapped_column(SmallInteger, default=10)
