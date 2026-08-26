"""机构服务：主表 CRUD / 子资源 / 协议联动 / 统计。

分层混合统计（§4.4）：列表读冗余字段（缓存）；详情/统计实时 SUM——
M2 阶段放款表（lend_provides）未建，实时 SUM 暂以冗余字段值返回，
M3 放款模块落地后接入 recalc_institution_balance 刷新链。
"""

from datetime import datetime

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizError
from app.institution.enums import (
    AgreementStatus,
    AgreementType,
    InstitutionStatus,
    InstitutionType,
    LABELS,
)
from app.institution.models import (
    Institution,
    InstitutionBranch,
    InstitutionContact,
    InstitutionCreditAgreement,
    InstitutionCreditHistory,
)
from app.institution.schemas import (
    AgreementCreate,
    AgreementUpdate,
    BranchCreate,
    BranchUpdate,
    ContactCreate,
    ContactUpdate,
    InstitutionCreate,
    InstitutionStatusUpdate,
    InstitutionUpdate,
)


def _disp(group: str, value: int | None) -> str | None:
    if value is None:
        return None
    return LABELS[group].get(value, str(value))


def _get_or_404(db: Session, institution_id: int) -> Institution:
    inst = db.get(Institution, institution_id)
    if inst is None:
        raise BizError(4041, "机构不存在")
    return inst


def _agreement_brief(a: InstitutionCreditAgreement) -> dict:
    return {
        "id": a.id,
        "agreement_type": a.agreement_type,
        "agreement_type_display": _disp("agreement_type", a.agreement_type),
        "flow_credit": float(a.flow_credit),
        "back_credit": float(a.back_credit),
        "valid_begin_date": a.valid_begin_date,
        "valid_end_date": a.valid_end_date,
        "status": a.status,
        "status_display": _disp("agreement_status", a.status),
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


# ===== 机构主管理 =====

def list_institutions(
    db: Session,
    page: int,
    page_size: int,
    institution_type: int | None = None,
    institution_subtype: int | None = None,
    status: int | None = None,
    has_active_agreement: bool | None = None,
    q: str | None = None,
) -> tuple[list[dict], int]:
    from app.user.models import User

    stmt = select(Institution, User.name).join(User, User.id == Institution.created_by)

    if institution_type is not None:
        stmt = stmt.where(Institution.institution_type == institution_type)
    if institution_subtype is not None:
        stmt = stmt.where(Institution.institution_subtype == institution_subtype)
    if status is not None:
        stmt = stmt.where(Institution.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Institution.name.like(like),
                Institution.short_name.like(like),
                Institution.credit_code.like(like),
            )
        )
    if has_active_agreement:
        stmt = stmt.where(
            Institution.id.in_(
                select(InstitutionCreditAgreement.institution_id).where(
                    InstitutionCreditAgreement.status == AgreementStatus.ACTIVE
                )
            )
        )

    total = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows = db.execute(
        stmt.order_by(Institution.institution_type, Institution.short_name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # 批量取子资源计数与当前协议，避免 N+1
    ids = [inst.id for inst, _ in rows]
    contact_counts = dict(
        db.execute(
            select(InstitutionContact.institution_id, func.count())
            .where(InstitutionContact.institution_id.in_(ids))
            .group_by(InstitutionContact.institution_id)
        ).all()
    )
    branch_counts = dict(
        db.execute(
            select(InstitutionBranch.institution_id, func.count())
            .where(InstitutionBranch.institution_id.in_(ids))
            .group_by(InstitutionBranch.institution_id)
        ).all()
    )
    current_agreements = {}
    for a in db.scalars(
        select(InstitutionCreditAgreement).where(
            and_(
                InstitutionCreditAgreement.institution_id.in_(ids),
                InstitutionCreditAgreement.status == AgreementStatus.ACTIVE,
            )
        )
    ):
        # 同机构取最新一条（id 最大）为当前协议
        if a.institution_id not in current_agreements or a.id > current_agreements[a.institution_id].id:
            current_agreements[a.institution_id] = a

    items = []
    for inst, creator in rows:
        cur = current_agreements.get(inst.id)
        items.append(
            {
                "id": inst.id,
                "name": inst.name,
                "short_name": inst.short_name,
                "institution_type": inst.institution_type,
                "institution_type_display": _disp("institution_type", inst.institution_type),
                "institution_subtype": inst.institution_subtype,
                "institution_subtype_display": _disp("institution_subtype", inst.institution_subtype),
                "legal_representative": inst.legal_representative,
                "contact_num": inst.contact_num,
                "current_agreement": _agreement_brief(cur) if cur else None,
                "used_flow": float(inst.used_flow),
                "used_accept": float(inst.used_accept),
                "used_back": float(inst.used_back),
                "used_entrusted": float(inst.used_entrusted),
                "used_amount": float(inst.used_amount),
                "last_synced_at": inst.last_synced_at,
                "contact_count": contact_counts.get(inst.id, 0),
                "branch_count": branch_counts.get(inst.id, 0),
                "status": inst.status,
                "status_display": _disp("institution_status", inst.status),
                "created_by_name": creator,
                "created_at": inst.created_at,
            }
        )
    return items, total


def get_detail(db: Session, institution_id: int) -> dict:
    from app.user.models import User

    inst = _get_or_404(db, institution_id)
    creator = db.scalar(select(User.name).where(User.id == inst.created_by)) or ""

    contacts = db.execute(
        select(InstitutionContact, User.name)
        .join(User, User.id == InstitutionContact.created_by)
        .where(InstitutionContact.institution_id == institution_id)
        .order_by(InstitutionContact.is_primary.desc(), InstitutionContact.id)
    ).all()
    branches = db.execute(
        select(InstitutionBranch, User.name)
        .join(User, User.id == InstitutionBranch.created_by)
        .where(InstitutionBranch.institution_id == institution_id)
        .order_by(InstitutionBranch.id)
    ).all()
    agreements = db.execute(
        select(InstitutionCreditAgreement, User.name)
        .join(User, User.id == InstitutionCreditAgreement.created_by)
        .where(InstitutionCreditAgreement.institution_id == institution_id)
        .order_by(InstitutionCreditAgreement.status, InstitutionCreditAgreement.id.desc())
    ).all()

    cur = next(
        (a for a, _ in agreements if a.status == AgreementStatus.ACTIVE), None
    )

    detail = {
        "id": inst.id,
        "name": inst.name,
        "short_name": inst.short_name,
        "institution_type": inst.institution_type,
        "institution_type_display": _disp("institution_type", inst.institution_type),
        "institution_subtype": inst.institution_subtype,
        "institution_subtype_display": _disp("institution_subtype", inst.institution_subtype),
        "legal_representative": inst.legal_representative,
        "contact_num": inst.contact_num,
        "current_agreement": _agreement_brief(cur) if cur else None,
        "used_flow": float(inst.used_flow),
        "used_accept": float(inst.used_accept),
        "used_back": float(inst.used_back),
        "used_entrusted": float(inst.used_entrusted),
        "used_amount": float(inst.used_amount),
        "last_synced_at": inst.last_synced_at,
        "contact_count": len(contacts),
        "branch_count": len(branches),
        "status": inst.status,
        "status_display": _disp("institution_status", inst.status),
        "created_by_name": creator,
        "created_at": inst.created_at,
        "credit_code": inst.credit_code,
        "registered_addr": inst.registered_addr,
        "contact_addr": inst.contact_addr,
        "email": inst.email,
        "up_scale": float(inst.up_scale) if inst.up_scale is not None else None,
        "updated_at": inst.updated_at,
        "contacts": [
            {
                "id": c.id,
                "name": c.name,
                "job": c.job,
                "phone": c.phone,
                "email": c.email,
                "is_primary": c.is_primary,
                "remark": c.remark,
                "created_by_name": cname,
            }
            for c, cname in contacts
        ],
        "branches": [
            {
                "id": b.id,
                "name": b.name,
                "short_name": b.short_name,
                "branch_addr": b.branch_addr,
                "contact_num": b.contact_num,
                "status": b.status,
                "status_display": _disp("institution_status", b.status),
                "created_by_name": bname,
            }
            for b, bname in branches
        ],
        "agreements": [_agreement_detail(a, aname) for a, aname in agreements],
    }
    return detail


def create(db: Session, body: InstitutionCreate, user_id: int) -> int:
    # 唯一性校验
    dup = db.scalar(
        select(Institution.id).where(
            or_(Institution.name == body.name, Institution.short_name == body.short_name)
        )
    )
    if dup is not None:
        raise BizError(4091, "机构名称或简称已存在")
    # 银行类 subtype 必填
    if body.institution_type == InstitutionType.BANK and body.institution_subtype is None:
        raise BizError(4001, "银行类机构必须指定子类型（国有/股份/城商/农商/外资/民营）")

    inst = Institution(
        name=body.name,
        short_name=body.short_name,
        institution_type=body.institution_type,
        institution_subtype=body.institution_subtype,
        credit_code=body.credit_code,
        legal_representative=body.legal_representative,
        registered_addr=body.registered_addr,
        contact_addr=body.contact_addr,
        contact_num=body.contact_num,
        email=body.email,
        up_scale=body.up_scale,
        status=InstitutionStatus.ACTIVE,
        created_by=user_id,
    )
    db.add(inst)
    db.flush()

    for c in body.contacts:
        db.add(
            InstitutionContact(
                institution_id=inst.id,
                name=c.name,
                job=c.job,
                phone=c.phone,
                email=c.email,
                is_primary=c.is_primary,
                remark=c.remark,
                created_by=user_id,
            )
        )
    return inst.id


def update(db: Session, institution_id: int, body: InstitutionUpdate) -> None:
    inst = _get_or_404(db, institution_id)
    if inst.status == InstitutionStatus.CANCELLED:
        raise BizError(4091, "已注销机构不可修改")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        return
    if "name" in data or "short_name" in data:
        cond = []
        if "name" in data:
            cond.append(Institution.name == data["name"])
        if "short_name" in data:
            cond.append(Institution.short_name == data["short_name"])
        dup = db.scalar(
            select(Institution.id).where(
                and_(or_(*cond), Institution.id != institution_id)
            )
        )
        if dup is not None:
            raise BizError(4091, "机构名称或简称已存在")
    for k, v in data.items():
        setattr(inst, k, v)


def change_status(
    db: Session, institution_id: int, body: InstitutionStatusUpdate, user_id: int
) -> None:
    inst = _get_or_404(db, institution_id)
    if inst.status == InstitutionStatus.CANCELLED:
        raise BizError(4091, "已注销机构不可再变更状态")
    inst.status = body.status


def delete(db: Session, institution_id: int) -> None:
    inst = _get_or_404(db, institution_id)
    # 拦截：生效协议 / 分支机构 / 在保余额
    active = db.scalar(
        select(InstitutionCreditAgreement.id).where(
            InstitutionCreditAgreement.institution_id == institution_id,
            InstitutionCreditAgreement.status == AgreementStatus.ACTIVE,
        )
    )
    if active is not None:
        raise BizError(4091, "机构存在生效协议，不可删除")
    branch = db.scalar(
        select(InstitutionBranch.id).where(
            InstitutionBranch.institution_id == institution_id
        )
    )
    if branch is not None:
        raise BizError(4091, "机构存在分支机构，不可删除")
    if float(inst.used_amount) > 0:
        raise BizError(4091, "机构在保余额大于零，不可删除")
    # 逻辑删除：置注销状态（保留审计事实）
    inst.status = InstitutionStatus.CANCELLED


# ===== 联系人 =====

def list_contacts(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, institution_id)
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
    _get_or_404(db, institution_id)
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


# ===== 分支机构 =====

def list_branches(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, institution_id)
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
            "status_display": _disp("institution_status", b.status),
            "created_by_name": bname,
        }
        for b, bname in rows
    ]


def add_branch(
    db: Session, institution_id: int, body: BranchCreate, user_id: int
) -> int:
    inst = _get_or_404(db, institution_id)
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


# ===== 授信协议 =====

def list_agreements(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, institution_id)
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
    inst = _get_or_404(db, institution_id)
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
                "agreement_type": _disp("agreement_type", a.agreement_type),
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
    inst = _get_or_404(db, institution_id)
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


# ===== 额度历史 =====

def list_credit_histories(db: Session, institution_id: int) -> list[dict]:
    from app.user.models import User

    _get_or_404(db, institution_id)
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
            "change_type_display": _disp("credit_change_type", h.change_type),
            "change_content": h.change_content,
            "changed_by_name": hname,
            "created_at": h.created_at,
        }
        for h, hname in rows
    ]


# ===== 统计 =====

def stats_overview(db: Session) -> dict:
    total = db.scalar(select(func.count(Institution.id))) or 0
    by_type_rows = db.execute(
        select(Institution.institution_type, func.count())
        .group_by(Institution.institution_type)
    ).all()
    by_status_rows = db.execute(
        select(Institution.status, func.count()).group_by(Institution.status)
    ).all()
    agg = db.execute(
        select(
            func.coalesce(func.sum(InstitutionCreditAgreement.flow_credit), 0),
            func.coalesce(func.sum(InstitutionCreditAgreement.back_credit), 0),
            func.count(InstitutionCreditAgreement.id),
        ).where(InstitutionCreditAgreement.status == AgreementStatus.ACTIVE)
    ).one()

    return {
        "total_count": total,
        "by_type": {
            _disp("institution_type", t): n for t, n in by_type_rows
        },
        "by_status": {
            _disp("institution_status", s): n for s, n in by_status_rows
        },
        "total_flow_credit": float(agg[0]),
        "total_back_credit": float(agg[1]),
        "active_agreement_count": agg[2],
    }


def stats_balance_summary(db: Session) -> list[dict]:
    rows = db.scalars(
        select(Institution)
        .where(Institution.institution_type == InstitutionType.BANK)
        .order_by(Institution.used_amount.desc())
    ).all()
    return [
        {
            "institution_id": i.id,
            "institution_name": i.name,
            "used_flow": float(i.used_flow),
            "used_accept": float(i.used_accept),
            "used_back": float(i.used_back),
            "used_entrusted": float(i.used_entrusted),
            "used_amount": float(i.used_amount),
        }
        for i in rows
    ]


def recalc_institution_balance(db: Session, institution_id: int) -> None:
    """刷新列表页余额缓存（供放款/还款事件异步调用，M3 接入）。

    算法：SUM 该机构下所有在保放款，按业务类型分组。
    M2 阶段无放款表，仅刷新 last_synced_at 占位。
    """
    inst = db.get(Institution, institution_id)
    if inst is None:
        return
    inst.last_synced_at = datetime.now()


def expire_agreements_job(db: Session) -> int:
    """APScheduler 每日任务：到期协议自动失效 + 写历史。"""
    today = datetime.now().date()
    expired = db.scalars(
        select(InstitutionCreditAgreement).where(
            InstitutionCreditAgreement.status == AgreementStatus.ACTIVE,
            InstitutionCreditAgreement.valid_end_date < today,
        )
    ).all()
    for a in expired:
        a.status = AgreementStatus.EXPIRED
        db.add(
            InstitutionCreditHistory(
                institution_id=a.institution_id,
                agreement_id=a.id,
                change_type=30,
                change_content={"field": "status", "before": "10", "after": "20",
                                 "reason": "到期自动失效"},
                changed_by=a.created_by,  # 系统任务，记创建人
            )
        )
    return len(expired)
