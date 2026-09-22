"""评审会主路由。"""

from fastapi import APIRouter, Depends, Query

from app.appraisal.services import appraisal_service, expert_service
from app.article.services import article_supply_service
from app.appraisal.schemas import (
    AppraisalArrange,
    AppraisalCreate,
    AppraisalFinish,
    CommentBatchCreate,
    ExpertSortBatch,
    ReviewExpertCreate,
    SupplyCreate,
    SupplyResolve,
    SupplyUpdate,
    SummaryUpdate,
)
from app.core.deps import AuthContext, require_perm
from app.core.db import get_db
from app.core.response import ok, page as page_result

router = APIRouter(tags=["评审管理"])


# ============ 评审会 ============

@router.get("/appraisals")
def list_appraisals(
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:list")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    year: int | None = None,
    review_model: int | None = None,
    meeting_state: int | None = None,
):
    items, total = appraisal_service.list_appraisals(
        db, ctx, page=page, page_size=page_size,
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


@router.get("/appraisals/pending-projects")
def list_pending_projects(
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:list")),
):
    data = appraisal_service.list_pending_projects(db, ctx)
    return ok(data)



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


@router.get("/appraisals/{appraisal_id}")
def get_appraisal(
    appraisal_id: int,
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    data = appraisal_service.get_appraisal(db, ctx, appraisal_id)
    return ok(data)


@router.get("/appraisals/{appraisal_id}/comments")
def get_appraisal_comment_matrix(
    appraisal_id: int,
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    data = appraisal_service.list_appraisal_comment_matrix(db, ctx, appraisal_id)
    return ok(data)


@router.delete("/appraisals/{appraisal_id}")
def delete_appraisal(
    appraisal_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:delete")),
):
    appraisal_service.delete_appraisal(db, appraisal_id, user.user_id)
    return ok(message="评审会已删除")


# ============ 评委意见 ============

@router.get("/articles/{article_id}/comments")
def list_article_comments(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:list")),
):
    data = appraisal_service.list_article_comments(db, article_id)
    return ok(data)


@router.post("/articles/{article_id}/comments")
def batch_upsert_comments(
    article_id: int,
    body: CommentBatchCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:comment")),
):
    count = appraisal_service.batch_upsert_comments(db, article_id, body, user.user_id)
    return ok({"count": count}, message="意见已保存")


# ============ 补调问题 ============

@router.get("/articles/{article_id}/supplies")
def list_article_supplies(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:list")),
):
    data = article_supply_service.list_article_supplies(db, article_id)
    return ok(data)


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
    user: AuthContext = Depends(require_perm("appraisal:supply_resolve")),
):
    appraisal_service.resolve_supply(db, supply_id, body, user.user_id)
    return ok(message="补调已登记解决")


@router.patch("/supplies/{supply_id}")
def update_supply(
    supply_id: int,
    body: SupplyUpdate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:update")),
):
    if body.supply_detail is None and body.reopen is None:
        return ok(message="无变更")
    appraisal_service.update_supply(
        db, supply_id,
        supply_detail=body.supply_detail,
        reopen=body.reopen,
        user_id=user.user_id,
        ctx=user,  # reopen 需要校验角色（dept_manager+）
    )
    return ok(message="补调已更新")


@router.delete("/supplies/{supply_id}")
def delete_supply(
    supply_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:update")),
):
    appraisal_service.delete_supply(db, supply_id, user.user_id)
    return ok(message="补调已删除")


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


@router.get("/articles/{article_id}/appraisal-report")
def get_article_appraisal_report(
    article_id: int,
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    """单项目评审材料包（#30）。"""
    return ok(appraisal_service.get_article_appraisal_report(db, ctx, article_id))


@router.get("/appraisals/{appraisal_id}/material-report")
def get_appraisal_material_report(
    appraisal_id: int,
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    """会议评审材料包（#9）。"""
    return ok(appraisal_service.get_appraisal_material_report(db, ctx, appraisal_id))


# ============ 评审专家 ============

@router.get("/review-experts")
def list_experts(
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:expert_list")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    expert_type: int | None = None,
    status: bool | None = None,
    keyword: str | None = Query(None, description="姓名/单位模糊搜索"),
):
    items, total = expert_service.list_experts(
        db, ctx, page=page, page_size=page_size,
        expert_type=expert_type, status=status, keyword=keyword,
    )
    return page_result(items, total, page, page_size)


@router.get("/review-experts/{expert_id}")
def get_expert(
    expert_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:expert_list")),
):
    return ok(expert_service.get_expert(db, expert_id))


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
    """修改专家。前端用 PUT（vben requestClient 只提供 get/post/put/delete，无 patch）。

    service 层用 body.model_dump(exclude_unset=True) + setattr 循环，
    未传字段保持原值——PUT 方法 + PATCH 语义。
    """
    expert_service.update_expert(db, expert_id, body, user.user_id)
    return ok(message="专家已更新")


@router.post("/review-experts/{expert_id}/toggle-status")
def toggle_expert_status(
    expert_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:expert_update")),
):
    """切换专家启用/停用状态（1↔0），返回新状态。"""
    new_status = expert_service.toggle_expert_status(db, expert_id)
    return ok({"status": new_status}, message="状态已变更")


@router.delete("/review-experts/{expert_id}")
def delete_expert(
    expert_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:expert_delete")),
):
    expert_service.delete_expert(db, expert_id, user.user_id)
    return ok(message="专家已删除")


@router.put("/review-experts/sort")
def sort_experts(
    body: ExpertSortBatch,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("appraisal:expert_update")),
):
    """专家拖拽排序（#17 PUT）。"""
    expert_service.sort_experts(db, [item.model_dump() for item in body.items], user.user_id)
    return ok(message="排序已更新")


@router.get("/review-experts/{expert_id}/history")
def get_expert_history(
    expert_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:read")),
):
    """专家评审历史（#18）：参评会议 + 意见明细。"""
    return ok(expert_service.get_expert_history(db, expert_id))


@router.get("/review-experts/{expert_id}/stats")
def get_expert_stats(
    expert_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("appraisal:read")),
):
    """专家出席统计（#19）：会议数/项目数/意见分布/最近 5 次。"""
    return ok(expert_service.get_expert_stats(db, expert_id))


# ============ 统计看板 ============

@router.get("/appraisals/stats")
def get_appraisal_stats(
    year: int | None = None,
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    """评审统计（#32）：会议数/类型分布/通过率/意见分布/平均上会周期。"""
    return ok(appraisal_service.get_appraisal_stats(db, ctx, year))


@router.get("/supplies/stats")
def get_supplies_stats(
    db=Depends(get_db),
    ctx: AuthContext = Depends(require_perm("appraisal:read")),
):
    """补调统计（#33）：未解决清单(含超7天)/平均解决时长/按创建人分布。"""
    return ok(appraisal_service.get_supplies_stats(db, ctx))
