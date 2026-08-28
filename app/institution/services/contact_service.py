"""机构联系人服务。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.institution.models import InstitutionContact
from app.institution.schemas import ContactCreate, ContactUpdate
from app.institution.services.common import get_or_404


def list_contacts(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    get_or_404(db, institution_id)
    rows = db.execute(
        select(InstitutionContact, User.name)
        .join(User, User.id == InstitutionContact.created_by)
        .where(InstitutionContact.institution_id == institution_id)
        .order_by(InstitutionContact.is_primary.desc(), InstitutionContact.id)
    ).all()
    return [
        {
            "id": c.id, "name": c.name, "job": c.job, "phone": c.phone,
            "email": c.email, "is_primary": c.is_primary, "remark": c.remark,
            "created_by_name": cname,
        }
        for c, cname in rows
    ]


def add_contact(
    db: Session, institution_id: int, body: ContactCreate, user_id: int
) -> int:
    get_or_404(db, institution_id)
    dup = db.scalar(
        select(InstitutionContact.id).where(
            InstitutionContact.institution_id == institution_id,
            InstitutionContact.name == body.name,
        )
    )
    if dup is not None:
        raise BizError(4091, "同名联系人已存在")
    c = InstitutionContact(
        institution_id=institution_id, created_by=user_id, **body.model_dump()
    )
    db.add(c)
    db.flush()
    return c.id


def update_contact(
    db: Session, institution_id: int, contact_id: int, body: ContactUpdate
) -> None:
    c = _get_contact(db, institution_id, contact_id)
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(c, k, v)


def delete_contact(db: Session, institution_id: int, contact_id: int) -> None:
    c = _get_contact(db, institution_id, contact_id)
    db.delete(c)


def _get_contact(db: Session, institution_id: int, contact_id: int) -> InstitutionContact:
    c = db.get(InstitutionContact, contact_id)
    if c is None or c.institution_id != institution_id:
        raise BizError(4041, "联系人不存在")
    return c
