"""评审专家 Service（P5：独立文件，专家库管理相对独立）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appraisal.models import AppraisalComment, ReviewExpert
from app.appraisal.schemas import ReviewExpertCreate
from app.core.exceptions import BizError


# ============ 顶部标配 ============

def _get_or_404(db: Session, expert_id: int) -> ReviewExpert:
    e = db.get(ReviewExpert, expert_id)
    if e is None:
        raise BizError(4041, "评审专家不存在")
    return e


# ============ CRUD ============

def list_experts(
    db: Session,
    *,
    expert_type: int | None = None,
    category_id: int | None = None,
    status: int | None = None,
) -> list[dict]:
    """专家列表。"""
    stmt = select(ReviewExpert).where(ReviewExpert.deleted_at.is_(None))
    if expert_type is not None:
        stmt = stmt.where(ReviewExpert.expert_type == expert_type)
    if category_id is not None:
        stmt = stmt.where(ReviewExpert.category_id == category_id)
    if status is not None:
        stmt = stmt.where(ReviewExpert.status == status)

    items = db.scalars(stmt.order_by(ReviewExpert.sort, ReviewExpert.id)).all()
    # TODO: 批量取 category 名称
    return [
        {
            "id": e.id,
            "name": e.name,
            "title": e.title,
            "org_name": e.org_name,
            "expert_type": e.expert_type,
            "category_id": e.category_id,
            "category_name": None,
            "contact_numb": e.contact_numb,
            "email": e.email,
            "sort": e.sort,
            "status": e.status,
        }
        for e in items
    ]


def create_expert(
    db: Session, body: ReviewExpertCreate, user_id: int
) -> int:
    """新增专家（唯一性：姓名 + 单位）。"""
    exists = db.scalar(
        select(ReviewExpert).where(
            ReviewExpert.name == body.name,
            ReviewExpert.org_name == body.org_name,
        )
    )
    if exists:
        raise BizError(4091, "该专家已存在")

    expert = ReviewExpert(
        name=body.name,
        title=body.title,
        org_name=body.org_name,
        expert_type=body.expert_type,
        category_id=body.category_id,
        contact_numb=body.contact_numb,
        email=body.email,
    )
    db.add(expert)
    db.commit()
    return expert.id


def update_expert(
    db: Session, expert_id: int, body: ReviewExpertCreate, user_id: int
) -> None:
    """修改专家。"""
    expert = _get_or_404(db, expert_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(expert, k, v)
    db.commit()


def delete_expert(db: Session, expert_id: int, user_id: int) -> None:
    """删除专家（有意见引用时软删停用）。"""
    expert = _get_or_404(db, expert_id)

    has_ref = db.scalar(
        select(AppraisalComment).where(AppraisalComment.expert_id == expert_id)
    )
    if has_ref is not None:
        # 软删：停用 + 记录 deleted_at
        expert.status = 0
        expert.deleted_at = str(__import__("datetime").datetime.now())
    else:
        db.delete(expert)

    db.commit()


def sort_experts(db: Session, items: list[dict], user_id: int) -> None:
    """批量更新排序。"""
    for item in items:
        expert = db.get(ReviewExpert, item["id"])
        if expert:
            expert.sort = item.get("sort", expert.sort)
    db.commit()
