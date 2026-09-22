"""评委意见 service（跨模块读 appraisal.AppraisalComment）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appraisal.models import AppraisalComment, ReviewExpert


def list_article_comments(db: Session, article_id: int) -> list[dict]:
    """项目的评委意见列表（含专家姓名）。

    注：AppraisalComment 无 score 字段，返回 None 占位。
    """
    stmt = (
        select(AppraisalComment, ReviewExpert.name.label("expert_name"))
        .outerjoin(ReviewExpert, ReviewExpert.id == AppraisalComment.expert_id)
        .where(AppraisalComment.article_id == article_id)
        .order_by(AppraisalComment.id.asc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "id": c.id,
            "expert_name": expert_name or f"专家#{c.expert_id}",
            "comment": c.comment,
            "comment_display": {10: "同意上会", 20: "复议", 30: "不同意"}.get(c.comment, "未发表"),
            "score": None,
            "detail": c.detail,
            "created_at": str(c.created_at) if c.created_at else None,
        }
        for c, expert_name in rows
    ]
