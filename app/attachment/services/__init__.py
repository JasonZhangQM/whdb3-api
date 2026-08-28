"""附件服务聚合出口（单 model，业务在 attachment_service.py），此处仅 re-export。"""

from app.attachment.services.attachment_service import (  # noqa: F401
    MEDIA_ROOT,
    delete,
    file_abs_path,
    get_attachment,
    list_by_resource,
    upload,
)
