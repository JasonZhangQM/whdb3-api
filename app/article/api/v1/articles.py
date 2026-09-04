"""项目主管理路由。

路由层职责（§3.1）：只做 参数接收 → 鉴权依赖注入 → 调 service → 返回 R。零业务逻辑。
"""

from fastapi import APIRouter, Depends, Query

from app.article.services import article_service
from app.article.schemas import (
    ArticleCreate,
    ArticleUpdate,
    ChangeRequestCreate,
    FeedbackCreate,
    LendingOrderCreate,
    SingleQuotaCreate,
    SureCreate,
    SignRequestCreate,
)
from app.core.deps import AuthContext, apply_data_scope_filter, get_current_user, require_perm
from app.core.db import get_db
from app.core.response import ok, page as page_result

router = APIRouter(prefix="/articles", tags=["项目管理"])


# ============ 列表/详情 ============

@router.get("", response_model=dict)
def list_articles(
    db=Depends(get_db),
    ctx: AuthContext = Depends(get_current_user),
    _=Depends(require_perm("article:list")),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    article_state: int | None = None,
    customer_id: int | None = None,
    product_id: int | None = None,
    director_id: int | None = None,
    keyword: str | None = None,
):
    items, total = article_service.list_articles(
        db, ctx, page=page, page_size=page_size,
        article_state=article_state, customer_id=customer_id,
        product_id=product_id, director_id=director_id, keyword=keyword,
    )
    return page_result(items, total, page, page_size)


@router.get("/{article_id}")
def get_article(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("article:read")),
):
    return ok(article_service.get_article(db, article_id))


# ============ 创建/修改/删除 ============

@router.post("")
def create_article(
    body: ArticleCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:create")),
):
    aid, num = article_service.create_article(db, body, user.user_id)
    return ok({"id": aid, "article_num": num}, message="项目已创建")


@router.put("/{article_id}")
def update_article(
    article_id: int,
    body: ArticleUpdate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:update")),
):
    article_service.update_article(db, article_id, body, user.user_id)
    return ok(message="项目已更新")


@router.delete("/{article_id}")
def delete_article(
    article_id: int,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:delete")),
):
    article_service.delete_article(db, article_id, user.user_id)
    return ok(message="项目已删除")


# ============ 风控反馈 ============

@router.post("/{article_id}/feedback")
def submit_feedback(
    article_id: int,
    body: FeedbackCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:feedback")),
):
    article_service.submit_feedback(db, article_id, body, user.user_id)
    return ok(message="风控反馈已提交")


# ============ 子资源 ============

@router.post("/{article_id}/single-quotas")
def add_single_quota(
    article_id: int,
    body: SingleQuotaCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:quota")),
):
    article_service.add_single_quota(db, article_id, body, user.user_id)
    return ok(message="单项额度已保存")


@router.post("/{article_id}/lending-orders")
def add_lending_order(
    article_id: int,
    body: LendingOrderCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:lending")),
):
    article_service.add_lending_order(db, article_id, body, user.user_id)
    return ok(message="放款次序已添加")


@router.post("/{article_id}/sures")
def upsert_sure(
    article_id: int,
    body: SureCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:sure")),
):
    article_service.upsert_sure(db, article_id, body, user.user_id)
    return ok(message="反担保措施已保存")


# ============ 审批发起 ============

@router.post("/{article_id}/sign-requests")
def submit_sign_request(
    article_id: int,
    body: SignRequestCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:sign")),
):
    instance_id = article_service.submit_sign_request(db, article_id, body, user.user_id)
    return ok({"instance_id": instance_id}, message="签批申请已发起")


@router.post("/{article_id}/change-requests")
def submit_change_request(
    article_id: int,
    body: ChangeRequestCreate,
    db=Depends(get_db),
    user: AuthContext = Depends(require_perm("article:change")),
):
    instance_id = article_service.submit_change_request(db, article_id, body, user.user_id)
    return ok({"instance_id": instance_id}, message="变更申请已发起")



# ============ 详情关联查询（供前端详情抽屉 Tab 使用）============

@router.get("/{article_id}/comments")
def get_article_comments(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("article:read")),
):
    return ok(article_service.list_article_comments(db, article_id))


@router.get("/{article_id}/supplies")
def get_article_supplies(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("article:read")),
):
    return ok(article_service.list_article_supplies(db, article_id))


@router.get("/{article_id}/approval-instances")
def get_article_approval_instances(
    article_id: int,
    db=Depends(get_db),
    _: AuthContext = Depends(require_perm("article:read")),
):
    return ok(article_service.list_article_approval_instances(db, article_id))
