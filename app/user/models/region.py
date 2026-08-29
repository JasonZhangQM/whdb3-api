"""行政区域模型（从 customer 模块迁入，作为用户模块基础数据）。"""

from sqlalchemy import BigInteger, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Region(Base):
    """行政区域树（省/市/区县/乡镇街道，12 位国标行政区划代码）。"""

    __tablename__ = "user_regions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, comment="行政区划代码")
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(SmallInteger, comment="10省20市30区县40乡镇街道")
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    ordery: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[int] = mapped_column(SmallInteger, default=10, comment="10启用20停用")
