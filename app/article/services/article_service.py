"""项目主 Service：标准模式（§3.7）。

文件顶部标配：_get_or_404 + _disp 两个私有函数。
函数命名：list_articles / get_article / create_article / update_article / delete_article ...
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval.services.engine_service import submit as approval_submit
from app.article.enums import LABELS as ARTICLE_LABELS, ArticleState
from app.article.models import (
    Article,
    ArticleBorrower,
    ArticleFeedback,
    ArticleLendingOrder,
    ArticleMortgageExt,
    ArticleProduct,
    ArticleSingleQuota,
    ArticleSure,
    ArticleSureCustomer,
)
from app.article.schemas import (
    ArticleCreate,
    ArticleUpdate,
    ChangeRequestCreate,
    FeedbackCreate,
    LendingOrderCreate,
    SignRequestCreate,
    SingleQuotaCreate,
    SureCreate,
)
from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.user.models import User


# ============ 文件顶部标配（§3.7.2）============

def _get_or_404(db: Session, article_id: int) -> Article:
    """查项目，不存在抛 404。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    return article


def _disp(label: dict[int, str] | None, value) -> str | None:
    """从 LABELS 字典取中文，value 为 None 返回 None。"""
    if label is None or value is None:
        return None
    return label.get(value)


def _build_name_dicts(db: Session, articles: list[Article]) -> dict:
    """§3.7.3 N+1 消除：批量取 user/product/customer 名称。

    返回 dict 含 users / customers / products 三个子 dict。
    """
    user_ids = set()
    customer_ids = set()
    product_ids = set()

    for a in articles:
        user_ids.add(a.director_id)
        if a.assistant_id:
            user_ids.add(a.assistant_id)
        if a.control_id:
            user_ids.add(a.control_id)
        if a.created_by:
            user_ids.add(a.created_by)
        customer_ids.add(a.customer_id)
        product_ids.add(a.product_id)

    # users: {id: name}
    users = {}
    if user_ids:
        users = dict(
            db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
        )

    # customers: {id: name}
    customers = {}
    if customer_ids:
        customers = dict(
            db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
            ).all()
        )

    # products: {id: name}
    products = {}
    if product_ids:
        products = dict(
            db.execute(
                select(ArticleProduct.id, ArticleProduct.name).where(
                    ArticleProduct.id.in_(product_ids)
                )
            ).all()
        )

    return {"users": users, "customers": customers, "products": products}


def _to_item(article: Article, dicts: dict) -> dict:
    """模型 → 列表项 dict（扁平化）。dicts 由 _build_name_dicts 构建。"""
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
        "repay_method": article.repay_method,
        "repay_method_display": _disp(ARTICLE_LABELS.get("repay_method"), article.repay_method),
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
        "sign_date": str(article.sign_date) if article.sign_date else None,
        "created_at": str(article.created_at) if article.created_at else None,
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
    """项目列表。

    §3.7.3 N+1 消除：批量取 user/product/customer 名称 → dict → 循环取值。
    """
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

    # §3.7.3 N+1 消除
    dicts = _build_name_dicts(db, items)
    return [_to_item(a, dicts) for a in items], total


def get_article(db: Session, article_id: int) -> dict:
    """项目详情聚合（含关联名称填充）。"""
    article = _get_or_404(db, article_id)
    dicts = _build_name_dicts(db, [article])
    item = _to_item(article, dicts)
    item.update({
        "summary_num": article.summary_num,
        "summary": article.summary,
        "opinion": article.opinion,
        "rcd_opinion": article.rcd_opinion,
        "convenor_opinion": article.convenor_opinion,
        "sign_detail": article.sign_detail,
        "sign_type": article.sign_type,
        "review_date": str(article.review_date) if article.review_date else None,
    })
    return item


def create_article(
    db: Session, body: ArticleCreate, user_id: int
) -> tuple[int, str]:
    """创建项目。

    设计决策 A3：不联动写客户（删除旧方案的 managementor/controler/custom_state 写入）。
    设计决策 A4：不联动写权证 meeting_date（删除）。
    """
    # 校验客户/产品存在（Customer 已上移到顶部 import）
    if db.get(Customer, body.customer_id) is None:
        raise BizError(4041, "客户不存在")
    if db.get(ArticleProduct, body.product_id) is None:
        raise BizError(4041, "产品不存在")

    # 生成项目编号：XDB{year}{seq:04d}
    year = date.today().year
    max_seq = db.scalar(
        select(Article).where(
            Article.article_num.like(f"XDB{year}%")
        ).order_by(Article.article_num.desc()).limit(1)
    )
    seq = (int(max_seq.article_num[-4:]) + 1) if max_seq else 1
    article_num = f"XDB{year}{seq:04d}"

    # §3.7.6 前置唯一性预检
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
        director_id=body.director_id,
        assistant_id=body.assistant_id,
        control_id=body.control_id,
        repay_method=body.repay_method,
    )
    db.add(article)
    db.flush()

    # 共借人批量写入
    for cid in body.borrower_ids:
        db.add(ArticleBorrower(article_id=article.id, customer_id=cid))

    db.commit()
    return article.id, article_num


def update_article(
    db: Session, article_id: int, body: ArticleUpdate, user_id: int
) -> None:
    """修改项目（自由字段 + flush 自动计算 amount）。

    仅允许 article_state ∈ {10,20,30,40,61}；存在 pending 审批实例时拒绝。
    """
    article = _get_or_404(db, article_id)
    if article.article_state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "当前状态不允许修改")

    data = body.model_dump(exclude_unset=True)
    if data:
        for k, v in data.items():
            setattr(article, k, v)

    # 共借人全量替换
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


def submit_feedback(
    db: Session, article_id: int, body: FeedbackCreate, user_id: int
) -> None:
    """提交风控反馈（upsert，提交后状态 → 20 已反馈）。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (10, 20):
        raise BizError(4031, "当前状态不允许提交反馈")

    feedback = db.scalar(
        select(ArticleFeedback).where(ArticleFeedback.article_id == article_id)
    )
    if feedback is None:
        feedback = ArticleFeedback(article_id=article_id)
        db.add(feedback)

    feedback.propose = body.propose
    feedback.analysis = body.analysis
    feedback.suggestion = body.suggestion
    feedback.submitted_by = user_id
    feedback.submitted_at = date.today()

    article.article_state = ArticleState.FEEDBACK_DONE.value
    db.commit()


def add_single_quota(
    db: Session, article_id: int, body: SingleQuotaCreate, user_id: int
) -> None:
    """添加/更新单项额度（upsert）。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可设置额度")

    # §3.7.6 前置唯一性预检
    quota = db.scalar(
        select(ArticleSingleQuota).where(
            ArticleSingleQuota.article_id == article_id,
            ArticleSingleQuota.credit_model == body.credit_model,
        )
    )
    if quota is None:
        quota = ArticleSingleQuota(
            article_id=article_id, credit_model=body.credit_model
        )
        db.add(quota)

    quota.credit_amount = body.credit_amount
    quota.flow_rate = body.flow_rate
    quota.remark = body.remark
    db.commit()


def add_lending_order(
    db: Session, article_id: int, body: LendingOrderCreate, user_id: int
) -> None:
    """添加放款次序。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可添加放款次序")

    if db.scalar(
        select(ArticleLendingOrder).where(
            ArticleLendingOrder.article_id == article_id,
            ArticleLendingOrder.seq == body.seq,
        )
    ):
        raise BizError(4091, f"次序 {body.seq} 已存在")

    db.add(ArticleLendingOrder(
        article_id=article_id,
        seq=body.seq,
        order_amount=body.order_amount,
        remark=body.remark,
        state=article.article_state,
    ))
    db.commit()


def upsert_sure(
    db: Session, article_id: int, body: SureCreate, user_id: int
) -> None:
    """添加/更新反担保措施（upsert by sure_type）。"""
    article = _get_or_404(db, article_id)
    if article.article_state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "当前状态不允许设置反担保措施")

    # §3.7.6 前置唯一性预检
    sure = db.scalar(
        select(ArticleSure).where(
            ArticleSure.article_id == article_id,
            ArticleSure.sure_type == body.sure_type,
        )
    )
    if sure is None:
        sure = ArticleSure(article_id=article_id, sure_type=body.sure_type)
        db.add(sure)

    sure.remark = body.remark
    db.flush()

    # 保证类：反担保人 M2M
    if body.sure_type in (1, 2):
        db.execute(
            ArticleSureCustomer.__table__.delete().where(
                ArticleSureCustomer.sure_id == sure.id
            )
        )
        for cid in body.customer_ids:
            db.add(ArticleSureCustomer(sure_id=sure.id, customer_id=cid))

    db.commit()


# ============ 审批对接 ============

def submit_sign_request(
    db: Session, article_id: int, body: SignRequestCreate, user_id: int
) -> int:
    """发起签批审批。

    前置校验：
    1. 项目状态 ∈ {40 已上会, 61 待变更}
    2. 金额三方校验：Σ额度 = Σ放款次序 = 签批总额（允许 ±0.01 误差）
    3. 审批引擎内置互斥（_check_pending_mutex）
    """
    article = _get_or_404(db, article_id)
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会/待变更状态可发起签批")

    # 金额三方校验
    total_from_body = body.renewal + body.augment
    total_from_quotas = db.scalar(
        select(func.coalesce(func.sum(ArticleSingleQuota.credit_amount), 0)).where(
            ArticleSingleQuota.article_id == article_id
        )
    ) or Decimal("0")
    total_from_orders = db.scalar(
        select(func.coalesce(func.sum(ArticleLendingOrder.order_amount), 0)).where(
            ArticleLendingOrder.article_id == article_id
        )
    ) or Decimal("0")

    # 允许 0.01 误差（浮点/Decimal 精度问题）
    tolerance = Decimal("0.01")
    if (abs(total_from_body - total_from_quotas) > tolerance
            or abs(total_from_body - total_from_orders) > tolerance):
        raise BizError(
            4031,
            f"金额三方校验不通过：签批总额 {total_from_body} ≠ "
            f"Σ额度 {total_from_quotas} ≠ Σ放款 {total_from_orders}",
        )

    # 提交审批（审批引擎内置互斥校验）
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


# ============ 详情关联查询（供前端详情抽屉 Tab 使用）============

def list_article_comments(db: Session, article_id: int) -> list[dict]:
    """项目的评委意见列表（含专家姓名）。

    注：AppraisalComment model 无 score 字段，这里返回 None 占位——
    原项目评审分制已迁移为 comment_type + concrete 的定性评价。
    """
    from app.appraisal.models import AppraisalComment, ReviewExpert
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
            "comment_type": c.comment_type,
            "comment_type_display": {10: "同意上会", 20: "复议", 30: "不同意"}.get(c.comment_type, "未发表"),
            "score": None,
            "concrete": c.concrete,
            "created_at": str(c.created_at) if c.created_at else None,
        }
        for c, expert_name in rows
    ]


def list_article_supplies(db: Session, article_id: int) -> list[dict]:
    """项目的补调记录列表。

    注：AppraisalSupply model 已废弃 resolved_at 字段（原审计用），
    这里返回 None 占位，保持前端表格渲染契约不变。
    """
    from app.appraisal.models import AppraisalSupply
    from app.user.models import User
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


def list_article_approval_instances(db: Session, article_id: int) -> list[dict]:
    """项目的审批实例列表（含 tasks，供 Timeline 展示）。"""
    from app.approval.models import ApprovalInstance, ApprovalTask, ApprovalFlowDef
    from app.user.models import User

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
        # 审批动作枚举：20=通过 / 30=驳回 / 40=跳过 / 其余=待处理
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
