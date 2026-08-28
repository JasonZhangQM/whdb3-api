"""分支机构服务：仅银行类机构可维护。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.institution.enums import InstitutionType
from app.institution.models import InstitutionBranch
from app.institution.schemas import BranchCreate, BranchUpdate
from app.institution.services.common import disp, get_or_404


def list_branches(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    get_or_404(db, institution_id)
    rows = db.execute(
        select(InstitutionBranch, User.name)
        .join(User, User.id == InstitutionBranch.created_by)
        .where(InstitutionBranch.institution_id == institution_id)
        .order_by(InstitutionBranch.id)
    ).all()
    return [
        {
            "id": b.id, "name": b.name, "short_name": b.short_name,
            "branch_addr": b.branch_addr, "contact_num": b.contact_num,
            "status": b.status,
            "status_display": disp("institution_status", b.status),
            "created_by_name": bname,
        }
        for b, bname in rows
    ]


def add_branch(
    db: Session, institution_id: int, body: BranchCreate, user_id: int
) -> int:
    inst = get_or_404(db, institution_id)
    if inst.institution_type != InstitutionType.BANK:
        raise BizError(4001, "仅银行类机构可添加分支机构")
    dup = db.scalar(
        select(InstitutionBranch.id).where(
            InstitutionBranch.institution_id == institution_id,
            InstitutionBranch.name == body.name,
        )
    )
    if dup is not None:
        raise BizError(4091, "同名分支机构已存在")
    b = InstitutionBranch(
        institution_id=institution_id, created_by=user_id, **body.model_dump()
    )
    db.add(b)
    db.flush()
    return b.id


def update_branch(
    db: Session, institution_id: int, branch_id: int, body: BranchUpdate
) -> None:
    b = _get_branch(db, institution_id, branch_id)
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(b, k, v)


def delete_branch(db: Session, institution_id: int, branch_id: int) -> None:
    # M3 合同模块落地后增加引用拦截；当前仅校验存在性
    b = _get_branch(db, institution_id, branch_id)
    db.delete(b)


def _get_branch(db: Session, institution_id: int, branch_id: int) -> InstitutionBranch:
    b = db.get(InstitutionBranch, branch_id)
    if b is None or b.institution_id != institution_id:
        raise BizError(4041, "分支机构不存在")
    return b
