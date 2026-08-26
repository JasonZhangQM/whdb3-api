"""机构模块路由：22 接口（字典 1 + 主管理 6 + 联系人 4 + 分支机构 4 + 协议 4 + 历史 1 + 统计 2）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.response import page as page_result
from app.institution.enums import LABELS
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
from app.institution import services as svc

router = APIRouter()


@router.get("/dicts/institution-types", tags=["dict"])
def institution_types(user: AuthContext = Depends(get_current_user)):
    """机构类型字典（含银行子类型）。"""
    return ok(
        {
            "institution_type": [
                {"value": v, "label": l} for v, l in LABELS["institution_type"].items()
            ],
            "institution_subtype": [
                {"value": v, "label": l} for v, l in LABELS["institution_subtype"].items()
            ],
            "agreement_type": [
                {"value": v, "label": l} for v, l in LABELS["agreement_type"].items()
            ],
        }
    )


# ===== 机构主管理 =====

@router.get("/institutions")
def list_institutions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    institution_type: int | None = None,
    institution_subtype: int | None = None,
    status: int | None = None,
    has_active_agreement: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:list")),
):
    items, total = svc.list_institutions(
        db, page, page_size, institution_type, institution_subtype,
        status, has_active_agreement, q,
    )
    return page_result(items, total, page, page_size)


@router.post("/institutions")
def create_institution(
    body: InstitutionCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:create")),
):
    institution_id = svc.create(db, body, user.user_id)
    db.commit()
    return ok({"id": institution_id}, message="创建成功")


@router.get("/institutions/stats/overview")
def stats_overview(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:list")),
):
    return ok(svc.stats_overview(db))


@router.get("/institutions/stats/balance-summary")
def stats_balance_summary(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:list")),
):
    return ok(svc.stats_balance_summary(db))


@router.get("/institutions/{institution_id}")
def get_institution(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:detail")),
):
    return ok(svc.get_detail(db, institution_id))


@router.patch("/institutions/{institution_id}")
def update_institution(
    institution_id: int,
    body: InstitutionUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.update(db, institution_id, body)
    db.commit()
    return ok(message="修改成功")


@router.patch("/institutions/{institution_id}/status")
def change_institution_status(
    institution_id: int,
    body: InstitutionStatusUpdate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:update")),
):
    svc.change_status(db, institution_id, body, user.user_id)
    db.commit()
    return ok(message="状态已变更")


@router.delete("/institutions/{institution_id}")
def delete_institution(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:delete")),
):
    svc.delete(db, institution_id)
    db.commit()
    return ok(message="已注销")


# ===== 联系人 =====

@router.get("/institutions/{institution_id}/contacts")
def list_contacts(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:detail")),
):
    return ok(svc.list_contacts(db, institution_id))


@router.post("/institutions/{institution_id}/contacts")
def add_contact(
    institution_id: int,
    body: ContactCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:update")),
):
    contact_id = svc.add_contact(db, institution_id, body, user.user_id)
    db.commit()
    return ok({"id": contact_id}, message="添加成功")


@router.patch("/institutions/{institution_id}/contacts/{contact_id}")
def update_contact(
    institution_id: int,
    contact_id: int,
    body: ContactUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.update_contact(db, institution_id, contact_id, body)
    db.commit()
    return ok(message="修改成功")


@router.delete("/institutions/{institution_id}/contacts/{contact_id}")
def delete_contact(
    institution_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.delete_contact(db, institution_id, contact_id)
    db.commit()
    return ok(message="已删除")


# ===== 分支机构 =====

@router.get("/institutions/{institution_id}/branches")
def list_branches(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:detail")),
):
    return ok(svc.list_branches(db, institution_id))


@router.post("/institutions/{institution_id}/branches")
def add_branch(
    institution_id: int,
    body: BranchCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:update")),
):
    branch_id = svc.add_branch(db, institution_id, body, user.user_id)
    db.commit()
    return ok({"id": branch_id}, message="添加成功")


@router.patch("/institutions/{institution_id}/branches/{branch_id}")
def update_branch(
    institution_id: int,
    branch_id: int,
    body: BranchUpdate,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.update_branch(db, institution_id, branch_id, body)
    db.commit()
    return ok(message="修改成功")


@router.delete("/institutions/{institution_id}/branches/{branch_id}")
def delete_branch(
    institution_id: int,
    branch_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.delete_branch(db, institution_id, branch_id)
    db.commit()
    return ok(message="已删除")


# ===== 授信协议 =====

@router.get("/institutions/{institution_id}/agreements")
def list_agreements(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:detail")),
):
    return ok(svc.list_agreements(db, institution_id))


@router.post("/institutions/{institution_id}/agreements")
def add_agreement(
    institution_id: int,
    body: AgreementCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:update")),
):
    agreement_id = svc.add_agreement(db, institution_id, body, user.user_id)
    db.commit()
    return ok({"id": agreement_id}, message="协议已创建")


@router.patch("/institutions/{institution_id}/agreements/{agreement_id}")
def update_agreement(
    institution_id: int,
    agreement_id: int,
    body: AgreementUpdate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("institution:update")),
):
    svc.update_agreement(db, institution_id, agreement_id, body, user.user_id)
    db.commit()
    return ok(message="修改成功")


@router.delete("/institutions/{institution_id}/agreements/{agreement_id}")
def delete_agreement(
    institution_id: int,
    agreement_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:update")),
):
    svc.delete_agreement(db, institution_id, agreement_id)
    db.commit()
    return ok(message="已删除")


# ===== 额度历史 =====

@router.get("/institutions/{institution_id}/credit-histories")
def list_credit_histories(
    institution_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("institution:detail")),
):
    return ok(svc.list_credit_histories(db, institution_id))
