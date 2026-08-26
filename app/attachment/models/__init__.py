"""附件模型：通用资源挂载（resource_type + resource_id）。"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    resource_type: Mapped[str] = mapped_column(
        String(32), comment="资源类型：customer/agree/article/lend..."
    )
    resource_id: Mapped[int] = mapped_column(BigInteger, comment="资源 id")
    file_name: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    # 相对 media/ 的路径，如 attachments/2026/08/uuid.pdf
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, comment="字节")
    mime_type: Mapped[str | None] = mapped_column(String(128))
    remark: Mapped[str | None] = mapped_column(String(255))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index("idx_attachment_resource", "resource_type", "resource_id"),
    )
