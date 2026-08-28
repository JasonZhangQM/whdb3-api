"""授信协议服务：协议 CRUD / 同类型互斥失效 / 额度历史轨迹。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.institution.enums import (
    AgreementStatus,
    AgreementType,
    InstitutionStatus,
)
from app.institution.models import (
    Institution,
    InstitutionCreditAgreement,
    InstitutionCreditHistory,
)
from app.institution.schemas import (
    AgreementCreate,
    AgreementUpdate,
)
from app.institution.services.common import disp, get_or_404


def _agreement_brief(a: InstitutionCreditAgreement) -> dict:
    return {
        "id": a.id,
        "agreement_type": a.agreement_type,
        "agreement_type_display": disp("agreement_type", a.agreement_type),
        "flow_credit": float(a.flow_credit),
        "back_credit": float(a.back_credit),
        "valid_begin_date": a.valid_begin_date,
        "valid_end_date": a.valid_end_date,
        "status": a.status,
        "status_display": disp("agreement_status", a.status),
    }


def _agreement_detail(a: InstitutionCreditAgreement, creator: str) -> dict:
    d = _agreement_brief(a)
    d.update(
        {
            "flow_limit": float(a.flow_limit),
            "back_limit": float(a.back_limit),
            "entrusted_credit": (
                float(a.entrusted_credit) if a.entrusted_credit is not None else None
            ),
            "remark": a.remark,
            "created_by_name": creator,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
    )
    return d


def list_agreements(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    get_or_404(db, institution_id)
    rows = db.execute(
        select(InstitutionCreditAgreement, User.name)
        .join(User, User.id == InstitutionCreditAgreement.created_by)
        .where(InstitutionCreditAgreement.institution_id == institution_id)
        .order_by(InstitutionCreditAgreement.status, InstitutionCreditAgreement.id.desc())
    ).all()
    return [_agreement_detail(a, aname) for a, aname in rows]


def add_agreement(
    db: Session, institution_id: int, body: AgreementCreate, user_id: int
) -> int:
    inst = get_or_404(db, institution_id)
    if inst.status == InstitutionStatus.CANCELLED:
        raise BizError(4091, "已注销机构不可新增协议")
    if body.agreement_type in (AgreementType.COMPREHENSIVE, AgreementType.GUARANTEE) and body.flow_credit <= 0:
        raise BizError(4001, "授信类协议综合额度必须大于 0")
    if body.valid_end_date <= body.valid_begin_date:
        raise BizError(4001, "协议到期日必须晚于起始日")

    # 同类型旧生效协议自动失效
    olds = db.scalars(
        select(InstitutionCreditAgreement).where(
            InstitutionCreditAgreement.institution_id == institution_id,
            InstitutionCreditAgreement.agreement_type == body.agreement_type,
            InstitutionCreditAgreement.status == AgreementStatus.ACTIVE,
        )
    ).all()

    a = InstitutionCreditAgreement(
        institution_id=institution_id,
        created_by=user_id,
        status=AgreementStatus.ACTIVE,
        **body.model_dump(),
    )
    db.add(a)
    db.flush()

    for old in olds:
        old.status = AgreementStatus.EXPIRED
        db.add(
            InstitutionCreditHistory(
                institution_id=institution_id,
                agreement_id=old.id,
                change_type=30,
                change_content={
                    "field": "status",
                    "before": "10",
                    "after": "20",
                    "reason": f"新协议 #{a.id} 生效自动失效",
                },
                changed_by=user_id,
            )
        )
    db.add(
        InstitutionCreditHistory(
            institution_id=institution_id,
            agreement_id=a.id,
            change_type=10,
            change_content={
                "agreement_type": disp("agreement_type", a.agreement_type),
                "flow_credit": float(a.flow_credit),
                "back_credit": float(a.back_credit),
                "valid_begin_date": str(a.valid_begin_date),
                "valid_end_date": str(a.valid_end_date),
            },
            changed_by=user_id,
        )
    )
    return a.id


def update_agreement(
    db: Session, institution_id: int, agreement_id: int, body: AgreementUpdate, user_id: int
) -> None:
    a = _get_agreement(db, institution_id, agreement_id)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        return

    changes: dict = {}
    for k, v in data.items():
        old_v = getattr(a, k)
        if old_v != v:
            changes[k] = {"before": str(old_v), "after": str(v)}
        setattr(a, k, v)

    if changes:
        db.add(
            InstitutionCreditHistory(
                institution_id=institution_id,
                agreement_id=a.id,
                change_type=20,
                change_content=changes,
                changed_by=user_id,
            )
        )


def delete_agreement(db: Session, institution_id: int, agreement_id: int) -> None:
    inst: Institution = get_or_404(db, institution_id)
    a = _get_agreement(db, institution_id, agreement_id)
    if a.status == AgreementStatus.ACTIVE and float(inst.used_amount) > 0:
        raise BizError(4091, "协议有在保余额，不可删除")
    db.delete(a)


def _get_agreement(
    db: Session, institution_id: int, agreement_id: int
) -> InstitutionCreditAgreement:
    a = db.get(InstitutionCreditAgreement, agreement_id)
    if a is None or a.institution_id != institution_id:
        raise BizError(4041, "协议不存在")
    return a


def list_credit_histories(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    get_or_404(db, institution_id)
    rows = db.execute(
        select(InstitutionCreditHistory, User.name)
        .join(User, User.id == InstitutionCreditHistory.changed_by)
        .where(InstitutionCreditHistory.institution_id == institution_id)
        .order_by(InstitutionCreditHistory.id.desc())
    ).all()
    return [
        {
            "id": h.id,
            "agreement_id": h.agreement_id,
            "agreement_type_display": None,
            "change_type": h.change_type,
            "change_type_display": disp("credit_change_type", h.change_type),
            "change_content": h.change_content,
            "changed_by_name": hname,
            "created_at": h.created_at,
        }
        for h, hname in rows
    ]
