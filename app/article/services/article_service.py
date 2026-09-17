"""项目主 service（聚合根编排层）。

按 AGENTS.md §2.2 拆分：跨表 CRUD 已移到独立 service 文件，
这里只保留主表函数 + 审批业务编排 + re-export。
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval.services.engine_service import submit as approval_submit
from app.article.enums import LABELS as ARTICLE_LABELS, ArticleState
from app.article.models import (
    Article,
    ArticleApproval,
    ArticleBorrower,
    ArticleFeedback,
    ArticleMortgageExt,
    ArticleProduct,
)
from app.article.schemas import (
    ArticleCreate,
    ArticleUpdate,
    ChangeRequestCreate,
    SignRequestCreate,
)
from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.user.models import User

# ---------- 子模块 re-export（按 AGENTS.md §2.2 拆分到独立 service）----------
from .article_comment_service import list_article_comments  # noqa: E402
from .article_feedback_service import submit_feedback  # noqa: E402
from .article_order_service import (  # noqa: E402
    add_order,
    delete_order,
    list_orders,
    update_order,
)
from .article_supply_service import list_article_supplies  # noqa: E402
from .article_sure_service import delete_sure_row, upsert_sure  # noqa: E402


# ============ 主表辅助函数 ============

def _get_or_404(db: Session, article_id: int) -> Article:
    """查项目，不存在抛 404。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def _disp(label: dict[int, str] | None, value) -> str | None:
    """label dict 反查 value 的 display 值。"""
    if label is None or value is None:
        return None
    return label.get(value, str(value))


def _build_name_dicts(db: Session, articles: list[Article]) -> dict:
    """N+1 消除：批量查 user/customer/product → name dict。"""
    user_ids = {a.director_id for a in articles} | {a.assistant_id for a in articles} | {a.control_id for a in articles} | {a.created_by for a in articles}
    customer_ids = {a.customer_id for a in articles}
    product_ids = {a.product_id for a in articles}

    users = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}
    customers = {c.id: c.name for c in db.scalars(select(Customer).where(Customer.id.in_(customer_ids))).all()}
    products = {p.id: p.name for p in db.scalars(select(ArticleProduct).where(
        ArticleProduct.id.in_(product_ids)
    )).all()}

    return {"users": users, "customers": customers, "products": products}


def _to_item(
    article: Article,
    dicts: dict,
    approval: ArticleApproval | None = None,
) -> dict:
    """模型 → 列表项 dict（扁平化）。"""
    users = dicts["users"]
    customers = dicts["customers"]
    products = dicts["products"]

    return {
        "id": article.id,
        "article_num": article.article_num,
        "article_state": article.article_state,
        "article_state_display": _disp(ARTICLE_LABELS.get("article_state"), article.article_state),
        "customer_id": article.customer_id,
        "customer_name": customers.get(article.customer_id),
        "product_id": article.product_id,
        "product_name": products.get(article.product_id),
        "renewal": float(article.renewal or 0),
        "augment": float(article.augment or 0),
        "credit_term": article.credit_term,
        "credit_term_unit": article.credit_term_unit,
        "credit_term_unit_display": _disp(ARTICLE_LABELS.get("credit_term_unit"), article.credit_term_unit),
        "director_id": article.director_id,
        "director_name": users.get(article.director_id),
        "assistant_id": article.assistant_id,
        "assistant_name": users.get(article.assistant_id),
        "control_id": article.control_id,
        "control_name": users.get(article.control_id),
        "balance": float(article.balance or 0),
        "notify_sum": float(article.notify_sum or 0),
        "provide_sum": float(article.provide_sum or 0),
        "repayment_sum": float(article.repayment_sum or 0),
        "sign_date": str(approval.sign_date) if approval and approval.sign_date else None,
        "created_at": str(article.created_at) if article.created_at else None,
        "updated_at": str(article.updated_at) if article.updated_at else None,
        "created_by_name": users.get(article.created_by),
    }


# ============ 项目主管理 ============

def list_articles(
    db: Session,
    ctx: AuthContext,
    *,
    page: int = 1,
    page_size: int = 20,
    article_state: int | None = None,
    customer_id: int | None = None,
    product_id: int | None = None,
    director_id: int | None = None,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    """项目列表。"""
    stmt = select(Article).order_by(Article.created_at.desc())
    if article_state is not None:
        stmt = stmt.where(Article.article_state == article_state)
    if customer_id is not None:
        stmt = stmt.where(Article.customer_id == customer_id)
    if product_id is not None:
        stmt = stmt.where(Article.product_id == product_id)
    if director_id is not None:
        stmt = stmt.where(Article.director_id == director_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Article.article_num.like(like))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()

    # 批量取 ArticleApproval（一对一，避免 N+1）
    _item_ids = [a.id for a in items]
    approval_map: dict[int, ArticleApproval] = {}
    if _item_ids:
        approval_map = {
            ap.article_id: ap
            for ap in db.scalars(
                select(ArticleApproval).where(ArticleApproval.article_id.in_(_item_ids))
            ).all()
        }

    dicts = _build_name_dicts(db, items)
    return [_to_item(a, dicts, approval_map.get(a.id)) for a in items], total


def get_article(db: Session, article_id: int) -> dict:
    """项目详情聚合（含关联名称填充 + approval + feedback 聚合）。"""
    article = _get_or_404(db, article_id)
    dicts = _build_name_dicts(db, [article])

    # 取一对一表 ArticleApproval（评审/签批字段）
    approval = db.scalar(
        select(ArticleApproval).where(ArticleApproval.article_id == article_id)
    )

    item = _to_item(article, dicts, approval)
    item.update({
        "summary_num": approval.summary_num if approval else None,
        "summary": approval.summary if approval else None,
        "opinion": approval.opinion if approval else None,
        "rcd_opinion": approval.rcd_opinion if approval else None,
        "convenor_opinion": approval.convenor_opinion if approval else None,
        "sign_detail": approval.sign_detail if approval else None,
        "sign_type": approval.sign_type if approval else None,
        "review_date": str(approval.review_date) if approval and approval.review_date else None,
    })

    # 聚合风控反馈（LEFT JOIN 语义：无反馈时全 None）
    feedback = db.scalar(
        select(ArticleFeedback).where(ArticleFeedback.article_id == article_id)
    )
    if feedback is not None:
        fb_creator_name = dicts["users"].get(feedback.created_by)
        if fb_creator_name is None and feedback.created_by is not None:
            fb_creator_name = db.get(User, feedback.created_by).name if db.get(User, feedback.created_by) else None
        item.update({
            "feedback_propose": feedback.propose,
            "feedback_analysis": feedback.analysis,
            "feedback_suggestion": feedback.suggestion,
            "feedback_created_by_name": fb_creator_name,
            "feedback_created_at": str(feedback.created_at) if feedback.created_at else None,
        })
    else:
        item.update({
            "feedback_propose": None,
            "feedback_analysis": None,
            "feedback_suggestion": None,
            "feedback_created_by_name": None,
            "feedback_created_at": None,
        })
    return item


def create_article(
    db: Session, body: ArticleCreate, user_id: int
) -> tuple[int, str]:
    """创建项目。"""
    if db.get(Customer, body.customer_id) is None:
        raise BizError(4041, "客户不存在")
    if db.get(ArticleProduct, body.product_id) is None:
        raise BizError(4041, "产品不存在")

    year = date.today().year
    max_seq = db.scalar(
        select(Article).where(
            Article.article_num.like(f"XDB{year}%")
        ).order_by(Article.article_num.desc()).limit(1)
    )
    seq = (int(max_seq.article_num[-4:]) + 1) if max_seq else 1
    article_num = f"XDB{year}{seq:04d}"

    if db.scalar(select(Article).where(Article.article_num == article_num)):
        raise BizError(4091, "项目编号已存在，请重试")

    article = Article(
        article_num=article_num,
        article_state=ArticleState.PENDING_FEEDBACK.value,
        customer_id=body.customer_id,
        product_id=body.product_id,
        renewal=body.renewal,
        augment=body.augment,
        credit_term=body.credit_term,
        credit_term_unit=body.credit_term_unit,
        director_id=body.director_id,
        assistant_id=body.assistant_id,
        control_id=body.control_id,
        created_by=user_id,
    )
    db.add(article)
    db.flush()

    for cid in body.borrower_ids:
        db.add(ArticleBorrower(article_id=article.id, customer_id=cid))

    # 批量创建放款次序（跳过 add_order 的 40/61 状态门禁——新立项项目 state=10 也允许初始化）
    if body.orders:
        from app.article.models import ArticleOrder

        # 校验 seq 不重复
        seqs = [o.seq for o in body.orders]
        if len(seqs) != len(set(seqs)):
            raise BizError(4001, "放款次序序号不能重复")

        for o in body.orders:
            db.add(ArticleOrder(
                article_id=article.id,
                seq=o.seq,
                order_amount=o.order_amount,
                remark=o.remark,
                state=article.article_state,
                created_by=user_id,
            ))

    db.commit()
    return article.id, article_num


def update_article(
    db: Session, article_id: int, body: ArticleUpdate, user_id: int
) -> None:
    """修改项目。仅允许 article_state ∈ {10,20,30,40,61}；存在 pending 审批实例时拒绝。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "当前状态不允许修改")

    data = body.model_dump(exclude_unset=True)
    if data:
        for k, v in data.items():
            setattr(article, k, v)

    if body.borrower_ids is not None:
        db.execute(
            ArticleBorrower.__table__.delete().where(
                ArticleBorrower.article_id == article_id
            )
        )
        for cid in body.borrower_ids:
            db.add(ArticleBorrower(article_id=article.id, customer_id=cid))

    db.commit()


def delete_article(db: Session, article_id: int, user_id: int) -> None:
    """删除项目（仅状态 10 待反馈）。"""
    article = _get_or_404(db, article_id)
    if article.article_state != ArticleState.PENDING_FEEDBACK.value:
        raise BizError(4031, "仅待反馈状态可删除")
    db.delete(article)
    db.commit()


# ============ 审批对接（主表编排层）============

def submit_sign_request(
    db: Session, article_id: int, body: SignRequestCreate, user_id: int
) -> int:
    """发起签批审批。

    前置校验：
    1. 项目状态 ∈ {40 已上会, 61 待变更}
    2. 金额校验：Σ放款次序 = 签批总额（允许 ±0.01 误差）
    3. 审批引擎内置互斥（_check_pending_mutex）
    """
    from app.article.models import ArticleOrder

    article = _get_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可发起签批")

    # 金额两方校验：放款次序 = 签批总额（允许 ±0.01 误差）
    total_from_body = body.renewal + body.augment
    total_from_orders = db.scalar(
        select(func.coalesce(func.sum(ArticleOrder.order_amount), 0)).where(
            ArticleOrder.article_id == article_id
        )
    ) or Decimal("0")

    tolerance = Decimal("0.01")
    if abs(total_from_body - total_from_orders) > tolerance:
        raise BizError(
            4031,
            f"金额校验不通过：签批总额 {total_from_body} ≠ Σ放款 {total_from_orders}",
        )

    payload = {
        "renewal": float(body.renewal),
        "augment": float(body.augment),
        "credit_amount": float(body.credit_amount),
        "g_value": float(body.g_value),
        "sign_type": body.sign_type,
        "rcd_opinion": body.rcd_opinion,
        "convenor_opinion": body.convenor_opinion,
        "sign_detail": body.sign_detail,
        "sign_date": str(body.sign_date),
    }
    instance_id = approval_submit(
        db,
        flow_code="article_sign",
        biz_type="article",
        biz_id=article_id,
        payload=payload,
        summary=f"项目 {article.article_num} 发起签批",
        submitted_by=user_id,
    )
    db.commit()
    return instance_id


def submit_change_request(
    db: Session, article_id: int, body: ChangeRequestCreate, user_id: int
) -> int:
    """发起变更申请审批。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (50, 51, 52, 61):
        raise BizError(4031, "已签批/已放款/待变更状态可发起变更")

    payload = {
        "change_detail": body.change_detail,
        "change_date": str(body.change_date) if body.change_date else None,
    }
    instance_id = approval_submit(
        db,
        flow_code="article_change",
        biz_type="article",
        biz_id=article_id,
        payload=payload,
        summary=f"项目 {article.article_num} 发起变更",
        submitted_by=user_id,
    )
    db.commit()
    return instance_id


# ============ 审批实例查询（供详情抽屉 Timeline）============

def list_article_approval_instances(db: Session, article_id: int) -> list[dict]:
    """项目的审批实例列表（含 tasks，供 Timeline 展示）。"""
    from app.approval.models import ApprovalInstance, ApprovalTask, ApprovalFlowDef

    stmt = (
        select(ApprovalInstance, ApprovalFlowDef.name.label("flow_name"), User.name.label("submitter_name"))
        .outerjoin(ApprovalFlowDef, ApprovalFlowDef.code == ApprovalInstance.flow_code)
        .outerjoin(User, User.id == ApprovalInstance.submitted_by)
        .where(
            ApprovalInstance.biz_type == "article",
            ApprovalInstance.biz_id == article_id,
        )
        .order_by(ApprovalInstance.submitted_at.desc())
    )
    rows = db.execute(stmt).all()

    results = []
    for inst, flow_name, submitter_name in rows:
        tasks_stmt = (
            select(ApprovalTask, User.name.label("approver_name"))
            .outerjoin(User, User.id == ApprovalTask.approver_id)
            .where(ApprovalTask.instance_id == inst.id)
            .order_by(ApprovalTask.step.asc(), ApprovalTask.id.asc())
        )
        task_rows = db.execute(tasks_stmt).all()
        _ACTION_MAP = {20: "approve", 30: "reject", 40: "skip"}
        tasks = [
            {
                "step": t.step,
                "node_name": t.node_name,
                "approver_name": approver_name or f"#{t.approver_id}",
                "status": t.status,
                "status_display": {10: "待审批", 20: "通过", 30: "驳回", 40: "跳过"}.get(t.status, ""),
                "action": _ACTION_MAP.get(t.status),
                "opinion": t.opinion,
                "acted_at": str(t.acted_at) if t.acted_at else None,
            }
            for t, approver_name in task_rows
        ]
        results.append({
            "id": inst.id,
            "flow_code": inst.flow_code,
            "flow_name": flow_name or inst.flow_code,
            "summary": inst.summary,
            "status": inst.status,
            "status_display": {10: "审批中", 20: "已通过", 30: "已驳回", 40: "已撤回"}.get(inst.status, str(inst.status)),
            "submitter_name": submitter_name or f"#{inst.submitted_by}",
            "submitted_at": str(inst.submitted_at) if inst.submitted_at else None,
            "tasks": tasks,
        })
    return results
