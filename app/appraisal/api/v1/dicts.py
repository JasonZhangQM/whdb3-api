"""评审模块字典接口（无 data_scope，登录即可）。

纯枚举聚合已统一走 core 的 /dicts/{name} 通配（/dicts/appraisal），
本文件仅保留 DB 数据字典接口。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appraisal.models import ExpertCategory
from app.core.deps import get_current_user
from app.core.db import get_db
from app.core.response import ok

router = APIRouter(prefix="/dicts", tags=["appraisal-dict"])


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
