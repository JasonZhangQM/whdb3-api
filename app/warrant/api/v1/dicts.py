"""权证字典路由（接口 1-9）：枚举字典 + 房产用途树 + 评估公司管理。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok
from app.core.tree import build_tree
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
    """房产用途字典（树形分类，替代旧系统硬编码枚举）。"""
    rows = db.scalars(
        select(WarrantHouseApp).where(WarrantHouseApp.status == 10).order_by(WarrantHouseApp.id)
    ).all()
    return ok(
        build_tree(
            rows,
            parent_getter=lambda r: r.parent_id,
            node_mapper=lambda r: {"id": r.id, "name": r.name},
            parent_id_null=None,  # WarrantHouseApp.parent_id 用 NULL 表示根
        )
    )


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
