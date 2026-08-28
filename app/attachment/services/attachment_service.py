"""附件服务：本地存储（media/attachments/YYYY/MM/uuid.ext）+ 元数据落库。"""

import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attachment.models import Attachment
from app.core.exceptions import BizError

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path(__file__).resolve().parent.parent.parent / "media"

# 允许的文件后缀（白名单，防上传可执行文件）
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".zip", ".rar", ".7z", ".txt", ".csv",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _save_file(data: bytes, original_name: str) -> str:
    """落盘：media/attachments/YYYY/MM/uuid.ext，返回相对路径。"""
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise BizError(4001, f"不支持的文件类型: {ext}")
    if len(data) > MAX_FILE_SIZE:
        raise BizError(4001, "文件超过 50MB 限制")

    now = datetime.now()
    rel_dir = Path("attachments") / f"{now:%Y}" / f"{now:%m}"
    abs_dir = MEDIA_ROOT / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    (abs_dir / filename).write_bytes(data)
    return str(rel_dir / filename).replace("\\", "/")


def upload(
    db: Session,
    resource_type: str,
    resource_id: int,
    file_name: str,
    data: bytes,
    mime_type: str | None,
    user_id: int,
    remark: str | None = None,
) -> int:
    """上传附件：落盘 + 元数据落库（调用方包事务）。"""
    rel_path = _save_file(data, file_name)
    att = Attachment(
        resource_type=resource_type,
        resource_id=resource_id,
        file_name=file_name,
        file_path=rel_path,
        file_size=len(data),
        mime_type=mime_type,
        remark=remark,
        uploaded_by=user_id,
    )
    db.add(att)
    db.flush()
    return att.id


def list_by_resource(
    db: Session, resource_type: str, resource_id: int
) -> list[tuple[Attachment, str]]:
    """按资源查询附件，返回 (attachment, uploader_name) 列表。"""
    from app.user.models import User

    rows = db.execute(
        select(Attachment, User.name)
        .join(User, User.id == Attachment.uploaded_by)
        .where(
            Attachment.resource_type == resource_type,
            Attachment.resource_id == resource_id,
        )
        .order_by(Attachment.id.desc())
    ).all()
    return rows


def delete(db: Session, attachment_id: int, user_id: int) -> None:
    """删除附件：仅上传者或超管可删；文件软删（保留磁盘，元数据删行）。"""
    att = db.get(Attachment, attachment_id)
    if att is None:
        raise BizError(4041, "附件不存在")
    if att.uploaded_by != user_id:
        raise BizError(4031, "仅上传者可删除该附件")
    db.delete(att)


def get_attachment(db: Session, attachment_id: int) -> Attachment:
    att = db.get(Attachment, attachment_id)
    if att is None:
        raise BizError(4041, "附件不存在")
    return att


def file_abs_path(att: Attachment) -> Path:
    """附件磁盘绝对路径（下载用）。"""
    p = MEDIA_ROOT / att.file_path
    if not p.is_file():
        raise BizError(4041, "附件文件缺失")
    return p
