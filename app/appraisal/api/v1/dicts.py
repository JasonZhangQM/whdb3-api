"""评审模块字典接口（无 data_scope，登录即可）。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appraisal.enums import LABELS
from app.appraisal.models import ExpertCategory
from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.response import ok

router = APIRouter(prefix="/dicts", tags=["appraisal-dict"])


def _enum(group: str) -> list[dict]:
    return [{"value": v, "label": l} for v, l in LABELS.get(group, {}).items()]


@router.get("/appraisal")
def appraisal_dict(_=Depends(get_current_user)):
    return ok({
        "review_model": _enum("review_model"),
        "meeting_state": _enum("meeting_state"),
        "comment_type": _enum("comment_type"),
        "expert_type": _enum("expert_type"),
        "supply_status": _enum("supply_status"),
    })


@router.get("/expert-categories")
def expert_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """专家类别（种子数据，只读）。"""
    rows = db.scalars(
        select(ExpertCategory).where(ExpertCategory.status == 1).order_by(ExpertCategory.sort)
    ).all()
    return ok([{
        "id": r.id,
        "name": r.name,
        "sort": r.sort,
    } for r in rows])
