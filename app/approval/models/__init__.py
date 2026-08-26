"""审批引擎模型：流程定义 / 节点 / 实例 / 任务。

外键按 R1 规则用字符串表名（users），模型层不 import 其他模块的模型类。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApprovalFlowDef(Base):
    """流程定义：code（如 customer_create）+ 版本 + 启用状态。

    流程定义走代码版本管理（seed 脚本写入），新增 flow_code 需评审。
    """

    __tablename__ = "approval_flow_defs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, comment="流程编码")
    name: Mapped[str] = mapped_column(String(64), comment="流程名称")
    version: Mapped[int] = mapped_column(SmallInteger, default=1, comment="版本号")
    status: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10启用20停用")
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (Index("idx_flow_def_code", "code"),)


class ApprovalFlowNode(Base):
    """流程节点：step 顺序 + 审批岗位 + 范围 + 跳过条件 + 或签。

    approver_role_code：审批岗位（对应 user_roles.code，如 dept_manager）
    approver_scope：10 提交人本部门拥有该角色者；20 提交人部门负责人
    or_sign：或签（任一人同意即过）——M2 场景均为单节点或签
    skip_condition：跳过条件表达式（预留，如提交人即审批人时自审跳过）
    """

    __tablename__ = "approval_flow_nodes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flow_def_id: Mapped[int] = mapped_column(
        ForeignKey("approval_flow_defs.id"), index=True
    )
    step: Mapped[int] = mapped_column(SmallInteger, comment="节点顺序，从 1 开始")
    name: Mapped[str] = mapped_column(String(64), comment="节点名称")
    approver_role_code: Mapped[str] = mapped_column(
        String(64), comment="审批岗位角色 code"
    )
    approver_scope: Mapped[int] = mapped_column(
        SmallInteger, default=10, comment="10提交人本部门20提交人部门负责人"
    )
    or_sign: Mapped[bool] = mapped_column(default=True, comment="或签：任一人同意即过")
    skip_condition: Mapped[str | None] = mapped_column(String(255), comment="预留跳过条件")

    __table_args__ = (
        Index("idx_flow_node_def_step", "flow_def_id", "step"),
    )


class ApprovalInstance(Base):
    """审批实例：flow_code + biz_type + biz_id + payload(JSON) + 状态 + 当前节点。

    payload 三模式：
      创建 = 完整草稿 JSON（不落库，通过后由 executor 落库）
      修改 = 字段级 diff（通过后由 executor 应用）
      移交 = 批量 ID 列表（≤200，通过后一条 UPDATE 批量生效）
    """

    __tablename__ = "approval_instances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flow_code: Mapped[str] = mapped_column(String(64), index=True, comment="流程编码")
    biz_type: Mapped[str] = mapped_column(String(32), index=True, comment="业务对象类型")
    # 创建场景无业务行，biz_id 可空（用 payload 唯一性约束兜底）
    biz_id: Mapped[int | None] = mapped_column(BigInteger, index=True, comment="业务对象 id")
    payload: Mapped[dict] = mapped_column(JSON, comment="三模式载荷")
    summary: Mapped[str] = mapped_column(String(255), comment="申请摘要（列表展示）")
    status: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10审批中20通过30驳回40撤回"
    )
    current_step: Mapped[int] = mapped_column(SmallInteger, default=1, comment="当前节点 step")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP")
    )
    finished_at: Mapped[datetime | None]

    __table_args__ = (
        # 互斥规则：同一业务对象同时只允许一个 pending 实例（部分索引由 service 层校验实现）
        Index("idx_inst_biz", "biz_type", "biz_id", "status"),
    )


class ApprovalTask(Base):
    """审批任务：instance + node + 审批人 + 状态 + 意见 + 操作时间。"""

    __tablename__ = "approval_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("approval_instances.id"), index=True
    )
    step: Mapped[int] = mapped_column(SmallInteger, comment="对应节点 step")
    node_name: Mapped[str] = mapped_column(String(64), comment="节点名称冗余")
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[int] = mapped_column(
        SmallInteger, default=10, index=True, comment="10待审20同意30驳回40跳过50取消"
    )
    opinion: Mapped[str | None] = mapped_column(String(500), comment="审批意见")
    acted_at: Mapped[datetime | None]

    __table_args__ = (
        Index("idx_task_instance_step", "instance_id", "step"),
    )
