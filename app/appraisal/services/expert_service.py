"""评审专家 Service（P5：独立文件，专家库管理相对独立）。

v1.2：list_experts 补 created_by_name（AGENTS.md §6.4 列表页硬约束）；
      service 签名加 ctx 铺路——但专家库是共享资源库（类似 regions/industries），
      不加 apply_data_scope_filter，pm 需要看到全量专家组建评委组。
v1.5：新增专家评审历史/统计接口（#18/#19）——三跳 JOIN：
      AppraisalComment → AppraisalArticle → Appraisal。
"""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.appraisal.enums import LABELS as APPRAISAL_LABELS
from app.appraisal.models import (
    Appraisal,
    AppraisalArticle,
    AppraisalComment,
    ExpertCategory,
    ReviewExpert,
)
from app.appraisal.schemas import ReviewExpertCreate
from app.article.models import Article
from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.user.models import User


# ============ 顶部标配 ============

def _get_or_404(db: Session, expert_id: int) -> ReviewExpert:
    e = db.get(ReviewExpert, expert_id)
    if e is None:
        raise BizError(4041, "评审专家不存在")
    return e


def _disp(label: dict[int, str] | None, value) -> str | None:
    """从模块 LABELS 字典取中文 label（§3.7.2 标准模式）。"""
    if value is None:
        return None
    if label is None:
        return str(value)
    return label.get(value, str(value))


# ============ CRUD ============

def list_experts(
    db: Session,
    ctx: AuthContext,
    *,
    page: int = 1,
    page_size: int = 20,
    expert_type: int | None = None,
    category_id: int | None = None,
    status: int | None = None,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    """专家列表（§3.7.1 标准分页 + §6.4 created_by_name）。

    v1.3 变更：补 page/page_size 参数（AGENTS.md §3.7.1 主资源列表标准模式）。
    data_scope 豁免：专家库是全局共享资源（类似 regions/industries），
    pm 需要在排会时看到全量专家组建评委组，不加 apply_data_scope_filter。
    权限码 appraisal:expert_list 控制管理页可见性即可。
    v1.8 变更：加 keyword 参数——按 name / org_name 模糊匹配。
    """
    stmt = select(ReviewExpert).where(ReviewExpert.deleted_at.is_(None))
    if expert_type is not None:
        stmt = stmt.where(ReviewExpert.expert_type == expert_type)
    if category_id is not None:
        stmt = stmt.where(ReviewExpert.category_id == category_id)
    if status is not None:
        stmt = stmt.where(ReviewExpert.status == status)
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(sa.or_(
            ReviewExpert.name.like(like),
            ReviewExpert.org_name.like(like),
        ))

    total = db.scalar(select(sa.func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(ReviewExpert.sort, ReviewExpert.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    # §3.7.3 N+1 消除：批量取 category 名称 + created_by 名称
    cat_ids = {e.category_id for e in items if e.category_id}
    cat_names: dict[int, str] = {}
    if cat_ids:
        cat_names = dict(
            db.execute(
                select(ExpertCategory.id, ExpertCategory.name).where(
                    ExpertCategory.id.in_(cat_ids)
                )
            ).all()
        )

    # 批量取创建人名称（AGENTS.md §6.4）
    created_ids = {e.created_by for e in items if e.created_by}
    creator_names: dict[int, str] = {}
    if created_ids:
        creator_names = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(created_ids))
            ).all()
        )

    return [
        {
            "id": e.id,
            "name": e.name,
            "title": e.title,
            "org_name": e.org_name,
            "expert_type": e.expert_type,
            "expert_type_display": _disp(
                APPRAISAL_LABELS.get("expert_type"), e.expert_type
            ),
            "category_id": e.category_id,
            "category_name": cat_names.get(e.category_id),
            "contact_numb": e.contact_numb,
            "email": e.email,
            "sort": e.sort,
            "status": e.status,
            "created_by": e.created_by,
            "created_by_name": creator_names.get(e.created_by),
        }
        for e in items
    ], total


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
    """删除专家（有意见引用时软删停用，AGENTS.md §4.1 时间约定）。"""
    expert = _get_or_404(db, expert_id)

    has_ref = db.scalar(
        select(AppraisalComment).where(AppraisalComment.expert_id == expert_id)
    )
    if has_ref is not None:
        # 软删：停用 + 记录 deleted_at（DateTime 类型）
        expert.status = 0
        expert.deleted_at = datetime.now()
    else:
        db.execute(
            delete(ReviewExpert).where(ReviewExpert.id == expert_id)
        )

    db.commit()


def sort_experts(db: Session, items: list[dict], user_id: int) -> None:
    """批量更新排序。"""
    for item in items:
        expert = db.get(ReviewExpert, item["id"])
        if expert:
            expert.sort = item.get("sort", expert.sort)
    db.commit()


# ============ 专家评审历史/统计（v1.5 #18/#19）============

def get_expert_history(db: Session, expert_id: int) -> dict:
    """专家评审历史（#18）。

    三跳 JOIN 链路：AppraisalComment(article_id, expert_id)
                   → AppraisalArticle(article_id, appraisal_id)
                   → Appraisal(id, num, review_date)

    返回：参评会议列表 + 历史意见明细（项目/结论/详情）。
    """
    expert = _get_or_404(db, expert_id)

    # ---- Query 1：distinct 参评会议 ----
    meeting_rows = db.execute(
        select(
            Appraisal.id,
            Appraisal.num,
            Appraisal.review_date,
            func.count(AppraisalArticle.id).label("articles_count"),
        ).join(
            AppraisalArticle, AppraisalArticle.appraisal_id == Appraisal.id
        ).join(
            AppraisalComment, AppraisalComment.article_id == AppraisalArticle.article_id
        ).where(
            AppraisalComment.expert_id == expert_id
        ).group_by(
            Appraisal.id, Appraisal.num, Appraisal.review_date
        ).order_by(
            Appraisal.review_date.desc(), Appraisal.id.desc()
        )
    ).all()

    meetings = [
        {
            "appraisal_id": aid,
            "num": num,
            "review_date": str(d) if d else None,
            "articles_count": int(cnt),
        }
        for aid, num, d, cnt in meeting_rows
    ]

    # ---- Query 2：历史意见明细（最近 50 条，避免一次返回太多） ----
    comment_rows = db.execute(
        select(
            AppraisalComment.id,
            AppraisalComment.comment_type,
            AppraisalComment.concrete,
            AppraisalComment.created_at,
            Article.article_num,
            Article.customer_id,
        ).join(
            Article, Article.id == AppraisalComment.article_id
        ).where(
            AppraisalComment.expert_id == expert_id
        ).order_by(
            AppraisalComment.created_at.desc()
        ).limit(50)
    ).all()

    customer_ids = {r.customer_id for r in comment_rows if r.customer_id}
    customers = {}
    if customer_ids:
        customers = dict(
            db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
            ).all()
        )

    comments = []
    for cid, ctype, concrete, created_at, anum, cid_customer in comment_rows:
        comments.append({
            "comment_id": cid,
            "article_num": anum,
            "customer_name": customers.get(cid_customer),
            "comment_type": ctype,
            "comment_type_display": _disp(APPRAISAL_LABELS.get("comment_type"), ctype),
            "concrete": concrete,
            "created_at": str(created_at) if created_at else None,
        })

    return {
        "expert": {
            "id": expert.id,
            "name": expert.name,
            "org_name": expert.org_name,
            "title": expert.title,
        },
        "meetings": meetings,
        "comments": comments,
        "meetings_count": len(meetings),
        "comments_count": len(comments),
    }


def get_expert_stats(db: Session, expert_id: int) -> dict:
    """专家出席统计（#19）。

    - meetings_count：参与过的评审会议数（distinct Appraisal）
    - articles_count：参评项目数（distinct Article via AppraisalComment）
    - opinion_distribution：按 comment_type 统计意见分布，key 为字符串（与前端字典协议对齐）
    - recent_meetings：最近 5 次评审会（用于前端"活动"Tab）
    """
    expert = _get_or_404(db, expert_id)

    # ---- meetings_count + articles_count（一次 GROUP BY 拿到两个 distinct） ----
    agg_row = db.execute(
        select(
            func.count(func.distinct(AppraisalArticle.appraisal_id)).label("meetings_count"),
            func.count(func.distinct(AppraisalComment.article_id)).label("articles_count"),
        ).select_from(AppraisalComment).outerjoin(
            AppraisalArticle, AppraisalArticle.article_id == AppraisalComment.article_id
        ).where(
            AppraisalComment.expert_id == expert_id
        )
    ).one()

    meetings_count = int(agg_row.meetings_count or 0)
    articles_count = int(agg_row.articles_count or 0)

    # ---- opinion_distribution ----
    type_rows = db.execute(
        select(
            AppraisalComment.comment_type,
            func.count().label("cnt"),
        ).where(
            AppraisalComment.expert_id == expert_id
        ).group_by(AppraisalComment.comment_type)
    ).all()
    opinion_distribution = {
        str(ctype): int(cnt) for ctype, cnt in type_rows if ctype is not None
    }

    # ---- recent_meetings ----
    recent_rows = db.execute(
        select(
            Appraisal.id,
            Appraisal.num,
            Appraisal.review_date,
            func.count(AppraisalArticle.id).label("articles_count"),
        ).join(
            AppraisalArticle, AppraisalArticle.appraisal_id == Appraisal.id
        ).join(
            AppraisalComment, AppraisalComment.article_id == AppraisalArticle.article_id
        ).where(
            AppraisalComment.expert_id == expert_id
        ).group_by(
            Appraisal.id, Appraisal.num, Appraisal.review_date
        ).order_by(
            Appraisal.review_date.desc(), Appraisal.id.desc()
        ).limit(5)
    ).all()

    recent_meetings = [
        {
            "appraisal_id": aid,
            "num": num,
            "review_date": str(d) if d else None,
            "articles_count": int(cnt),
        }
        for aid, num, d, cnt in recent_rows
    ]

    return {
        "expert": {
            "id": expert.id,
            "name": expert.name,
            "org_name": expert.org_name,
            "title": expert.title,
        },
        "meetings_count": meetings_count,
        "articles_count": articles_count,
        "opinion_distribution": opinion_distribution,
        "recent_meetings": recent_meetings,
    }
