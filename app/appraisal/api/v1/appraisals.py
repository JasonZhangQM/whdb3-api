"""评审会主路由。"""

from fastapi import APIRouter, Depends, Query

from app.appraisal.services import appraisal_service, expert_service
from app.appraisal.schemas import (
    AppraisalArrange,
    AppraisalCreate,
    AppraisalFinish,
    CommentBatchCreate,
    ReviewExpertCreate,
    SupplyCreate,
    SupplyResolve,
    SummaryUpdate,
)
from app.core.deps import AuthContext, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok, page as page_result

router = APIRouter(tags=["评审管理"])


# ============ 评审会 ============

@router.get("/appraisals")
def list_appraisals(
    db=Depends(get_db),
    ctx: AuthContext = Depends(get_current_user),
    _=Depends(require_perm("appraisal:list")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    year: int | None = None,
    review_model: int | None = None,
    meeting_state: int | None = None,
):
    items, total = appraisal_service.list_appraisals(
        db, page=page, page_size=page_size,
        year=year, review_model=review_model, meeting_state=meeting_state,
    )
    return page_result(items, total, page, page_size)


@router.post("/appraisals")
def create_appraisal(
    body: AppraisalCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:create")),
):
    aid = appraisal_service.create_appraisal(db, body, user.user_id)
    return ok({"id": aid}, message="评审会已创建")



@router.get("/appraisals/{appraisal_id}/articles")
def list_appraisal_articles(
    appraisal_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:read")),
):
    return ok(appraisal_service.list_appraisal_articles(db, appraisal_id))

@router.post("/appraisals/{appraisal_id}/articles")
def arrange_articles(
    appraisal_id: int,
    body: AppraisalArrange,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:update")),
):
    appraisal_service.arrange_articles(db, appraisal_id, body, user.user_id)
    return ok(message="项目已排入评审会")


@router.delete("/appraisals/{appraisal_id}/articles/{article_id}")
def remove_article(
    appraisal_id: int,
    article_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:update")),
):
    appraisal_service.remove_article(db, appraisal_id, article_id, user.user_id)
    return ok(message="项目已移出")


@router.post("/appraisals/{appraisal_id}/finish")
def finish_appraisal(
    appraisal_id: int,
    body: AppraisalFinish | None = None,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:finish")),
):
    appraisal_service.finish_appraisal(db, appraisal_id, body, user.user_id)
    return ok(message="会议已完成")


@router.delete("/appraisals/{appraisal_id}")
def delete_appraisal(
    appraisal_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:delete")),
):
    appraisal_service.delete_appraisal(db, appraisal_id, user.user_id)
    return ok(message="评审会已删除")


# ============ 评委意见 ============

@router.post("/articles/{article_id}/comments")
def batch_upsert_comments(
    article_id: int,
    body: CommentBatchCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    count = appraisal_service.batch_upsert_comments(db, article_id, body, user.user_id)
    return ok({"count": count}, message="意见已保存")


# ============ 补调问题 ============

@router.post("/articles/{article_id}/supplies")
def add_supply(
    article_id: int,
    body: SupplyCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:create")),
):
    appraisal_service.add_supply(db, article_id, body, user.user_id)
    return ok(message="补调问题已添加")


@router.post("/supplies/{supply_id}/resolve")
def resolve_supply(
    supply_id: int,
    body: SupplyResolve,
    db=Depends(get_db),
    user: AuthContext = Depends(get_current_user),
):
    appraisal_service.resolve_supply(db, supply_id, body, user.user_id)
    return ok(message="补调已登记解决")


# ============ 纪要 ============

@router.patch("/articles/{article_id}/summary")
def update_summary(
    article_id: int,
    body: SummaryUpdate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:update")),
):
    appraisal_service.update_summary(db, article_id, body, user.user_id)
    return ok(message="纪要已更新")


# ============ 评审专家 ============

@router.get("/review-experts")
def list_experts(
    db=Depends(get_db),
    ctx: AuthContext = Depends(get_current_user),
    expert_type: int | None = None,
    category_id: int | None = None,
    status: int | None = None,
):
    return ok(expert_service.list_experts(
        db, expert_type=expert_type, category_id=category_id, status=status
    ))


@router.post("/review-experts")
def create_expert(
    body: ReviewExpertCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:expert_create")),
):
    eid = expert_service.create_expert(db, body, user.user_id)
    return ok({"id": eid}, message="专家已添加")


@router.put("/review-experts/{expert_id}")
def update_expert(
    expert_id: int,
    body: ReviewExpertCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:expert_update")),
):
    expert_service.update_expert(db, expert_id, body, user.user_id)
    return ok(message="专家已更新")


@router.delete("/review-experts/{expert_id}")
def delete_expert(
    expert_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:expert_delete")),
):
    expert_service.delete_expert(db, expert_id, user.user_id)
    return ok(message="专家已删除")
