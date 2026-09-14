"""权证评估 service + 评估公司字典。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import (
    Warrant, WarrantEvaluate, WarrantEvaluateRecheck, WarrantEvaluateCompany,
)
from app.warrant.schemas import EvaluateCreate, RecheckCreate


def _get_or_404(db: Session, warrant_id: int) -> Warrant:
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


def list_evaluates(db: Session, warrant_id: int, ctx: AuthContext) -> list[dict]:
    """评估历史列表（含复核）。独立接口 + get_detail 内部复用。"""
    _get_warrant_with_scope(db, warrant_id, ctx)
    evaluates = db.scalars(
        select(WarrantEvaluate)
        .where(WarrantEvaluate.warrant_id == warrant_id)
        .order_by(WarrantEvaluate.evaluate_date.desc(), WarrantEvaluate.id.desc())
    ).all()
    user_names = _user_names(db, {e.created_by for e in evaluates if e.created_by})
    eval_ids = [e.id for e in evaluates]
    recheck_map = dict()
    if eval_ids:
        rr = db.scalars(
            select(WarrantEvaluateRecheck).where(WarrantEvaluateRecheck.evaluate_id.in_(eval_ids))
        ).all()
        recheck_map = {r.evaluate_id: r for r in rr}
    return [
        {
            "id": e.id,
            "evaluate_method": e.evaluate_method,
            "evaluate_method_display": _disp("evaluate_method", e.evaluate_method),
            "evaluate_value": float(e.evaluate_value),
            "evaluate_date": e.evaluate_date,
            "evaluate_explain": e.evaluate_explain,
            "evaluate_company": e.evaluate_company,
            "created_by_name": user_names.get(e.created_by, ""),
            "recheck": (
                {
                    "id": rc.id,
                    "check_value": float(rc.check_value),
                    "recheck_value": float(rc.recheck_value),
                    "recheck_channel": rc.recheck_channel,
                    "remark": rc.remark,
                }
                if (rc := recheck_map.get(e.id)) else None
            ),
        }
        for e in evaluates
    ]


# ===== 详情（一次性聚合）=====

def add_evaluate(db: Session, warrant_id: int, body, user_id: int, ctx: AuthContext) -> int:
    """新增评估记录（仅写 warrant_evaluates 子表，主表已无评估字段）。"""
    _get_warrant_with_scope(db, warrant_id, ctx)
    e = WarrantEvaluate(
        warrant_id=warrant_id, **body.model_dump(), created_by=user_id
    )
    db.add(e)
    db.flush()
    return e.id


def add_recheck(db: Session, warrant_id: int, evaluate_id: int, body, user_id: int, ctx: AuthContext) -> int:
    _get_warrant_with_scope(db, warrant_id, ctx)
    e = db.get(WarrantEvaluate, evaluate_id)
    if e is None or e.warrant_id != warrant_id:
        raise BizError(4041, "评估记录不存在")
    existing = db.scalar(
        select(WarrantEvaluateRecheck.id).where(
            WarrantEvaluateRecheck.evaluate_id == evaluate_id
        )
    )
    if existing is not None:
        raise BizError(4091, "该评估已有复核记录")
    r = WarrantEvaluateRecheck(
        evaluate_id=evaluate_id, **body.model_dump(), created_by=user_id
    )
    db.add(r)
    db.flush()
    return r.id


# ===== 批量操作 =====

def list_evaluate_companies(db: Session) -> list[dict]:
    rows = db.scalars(select(WarrantEvaluateCompany).order_by(WarrantEvaluateCompany.id)).all()
    return [{"id": r.id, "name": r.name} for r in rows]


def create_evaluate_company(db: Session, name: str, user_id: int) -> int:
    dup = db.scalar(
        select(WarrantEvaluateCompany.id).where(WarrantEvaluateCompany.name == name)
    )
    if dup is not None:
        raise BizError(4091, "评估公司已存在")
    c = WarrantEvaluateCompany(name=name, created_by=user_id)
    db.add(c)
    db.flush()
    return c.id


def delete_evaluate_company(db: Session, company_id: int) -> None:
    """删除拦截：已被评估记录引用。"""
    c = db.get(WarrantEvaluateCompany, company_id)
    if c is None:
        raise BizError(4041, "评估公司不存在")
    used = db.scalar(
        select(WarrantEvaluate.id).where(WarrantEvaluate.evaluate_company == c.name).limit(1)
    )
    if used is not None:
        raise BizError(4091, "评估公司已被评估记录引用，不可删除")
    db.delete(c)