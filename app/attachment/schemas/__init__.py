"""附件 Schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentItem(BaseModel):
    id: int
    resource_type: str
    resource_id: int
    file_name: str
    file_size: int
    mime_type: str | None
    remark: str | None
    uploaded_by_name: str
    created_at: datetime
    url: str  # 下载地址 /media/attachments/...


class AttachmentQuery(BaseModel):
    resource_type: str = Field(..., max_length=32)
    resource_id: int
