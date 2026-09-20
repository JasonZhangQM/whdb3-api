"""权证字典路由（接口 1-9）：枚举字典 + 房产用途 + 评估公司管理。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.warrant.enums import LABELS
from app.warrant.models import WarrantHouseApp
from app.warrant.schemas import EvaluateCompanyCreate
from app.warrant.services import warrant_service

router = APIRouter(prefix="/dicts", tags=["warrant-dict"])


def _enum(group: str) -> list[dict]:
    return [{"value": v, "label": l} for v, l in LABELS[group].items()]


@router.get("/warrant-types")
def warrant_types(_: AuthContext = Depends(get_current_user)):
    """权证类型字典（含票据明细类型）。"""
    return ok(
        {
            "warrant_type": _enum("warrant_type"),
            "draft_type": _enum("draft_type"),
        }
    )


@router.get("/warrants")
def warrants_dict(
    q: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """权证下拉字典（表单选择用）。无 data_scope——业务模块选抵质押权证时
    需要看到全量权证，不应被 created_by 归属过滤。
    """
    items, total = warrant_service.warrant_dict(db, q, page, page_size)
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/warrant-states")
def warrant_states(_: AuthContext = Depends(get_current_user)):
    """权证状态 + 出入库类型字典（出入库联动状态，一并下发）。"""
    return ok(
        {
            "warrant_state": _enum("warrant_state"),
            "storage_type": _enum("storage_type"),
        }
    )


@router.get("/storage-types")
def storage_types(_: AuthContext = Depends(get_current_user)):
    """出入库类型字典。"""
    return ok({"storage_type": _enum("storage_type")})


@router.get("/evaluate-methods")
def evaluate_methods(_: AuthContext = Depends(get_current_user)):
    """评估方式字典。"""
    return ok({"evaluate_method": _enum("evaluate_method")})


@router.get("/auction-states")
def auction_states(_: AuthContext = Depends(get_current_user)):
    """拍卖状态字典。"""
    return ok({"auction_state": _enum("auction_state")})


@router.get("/house-apps")
def house_apps(db: Session = Depends(get_db), _: AuthContext = Depends(get_current_user)):
    """房产用途字典（扁平列表，按 category 分组，替代旧系统硬编码枚举）。"""
    rows = db.scalars(
        select(WarrantHouseApp).where(WarrantHouseApp.status == 10).order_by(WarrantHouseApp.category.is_(None), WarrantHouseApp.category, WarrantHouseApp.ordery, WarrantHouseApp.id)
    ).all()
    cat_labels = LABELS.get("house_app_category", {})
    items = [
        {
            "id": r.id,
            "name": r.name,
            "category": r.category,
            "category_label": cat_labels.get(r.category, None) if r.category is not None else None,
        }
        for r in rows
    ]
    return ok(items)


@router.get("/evaluate-companies")
def list_evaluate_companies(
    db: Session = Depends(get_db),
    _: AuthContext = Depends(get_current_user),
):
    """评估公司字典。"""
    return ok(warrant_service.list_evaluate_companies(db))


@router.post("/evaluate-companies")
def create_evaluate_company(
    body: EvaluateCompanyCreate,
    db: Session = Depends(get_db),
    user: AuthContext = Depends(require_perm("warrant:update")),
):
    """新增评估公司。"""
    cid = warrant_service.create_evaluate_company(db, body.name, user.user_id)
    db.commit()
    return ok({"id": cid}, message="评估公司已创建")


@router.delete("/evaluate-companies/{company_id}")
def delete_evaluate_company(
    company_id: int,
    db: Session = Depends(get_db),
    _: AuthContext = Depends(require_perm("warrant:update")),
):
    """删除评估公司（拦截：已被评估记录引用）。"""
    warrant_service.delete_evaluate_company(db, company_id)
    db.commit()
    return ok(message="评估公司已删除")
