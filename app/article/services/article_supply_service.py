"""补调记录 service（跨模块读 appraisal.AppraisalSupply）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appraisal.models import AppraisalSupply
from app.user.models import User


def list_article_supplies(db: Session, article_id: int) -> list[dict]:
    """项目的补调记录列表。"""
    stmt = (
        select(AppraisalSupply, User.name.label("supplyor_name"))
        .outerjoin(User, User.id == AppraisalSupply.supplyor_id)
        .where(AppraisalSupply.article_id == article_id)
        .order_by(AppraisalSupply.id.desc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "id": s.id,
            "supply_detail": s.supply_detail,
            "is_resolved": s.is_resolved,
            "resolve_reply": s.resolve_reply,
            "supplyor_name": supplyor_name or f"#{s.supplyor_id}",
            "created_at": str(s.created_at) if s.created_at else None,
            "resolved_at": None,
        }
        for s, supplyor_name in rows
    ]
