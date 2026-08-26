"""附件路由：上传 / 按资源查询 / 删除 / 下载。"""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.attachment import services as attachment_service
from app.core.deps import AuthContext, get_current_user
from app.core.db import get_db
from app.core.response import ok

router = APIRouter(prefix="/attachments", tags=["attachment"])


@router.post("")
async def upload_attachment(
    file: UploadFile = File(...),
    resource_type: str = Form(..., max_length=32),
    resource_id: int = Form(...),
    remark: str | None = Form(None, max_length=255),
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    data = await file.read()
    attachment_id = attachment_service.upload(
        db,
        resource_type,
        resource_id,
        file.filename or "unnamed",
        data,
        file.content_type,
        user.user_id,
        remark,
    )
    db.commit()
    return ok({"id": attachment_id}, message="上传成功")


@router.get("")
def list_attachments(
    resource_type: str = Query(..., max_length=32),
    resource_id: int = Query(...),
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    rows = attachment_service.list_by_resource(db, resource_type, resource_id)
    items = [
        {
            "id": att.id,
            "resource_type": att.resource_type,
            "resource_id": att.resource_id,
            "file_name": att.file_name,
            "file_size": att.file_size,
            "mime_type": att.mime_type,
            "remark": att.remark,
            "uploaded_by_name": uploader_name,
            "created_at": att.created_at,
            "url": f"/media/{att.file_path}",
        }
        for att, uploader_name in rows
    ]
    return ok(items)


@router.delete("/{attachment_id}")
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    attachment_service.delete(db, attachment_id, user.user_id)
    db.commit()
    return ok(message="已删除")


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    att = attachment_service.get_attachment(db, attachment_id)
    path = attachment_service.file_abs_path(att)
    return FileResponse(path, filename=att.file_name, media_type=att.mime_type)
