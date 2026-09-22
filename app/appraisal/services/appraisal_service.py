"""评审主 Service（§3.7 标准模式）。

P5 合并：评审会 + 补调 + 意见 → 一个 appraisal_service.py。
v1.2：list_appraisals 补 created_by_name（AGENTS.md §6.4 列表页硬约束）；
      service 签名加 ctx 为 data_scope 铺路。
v1.4：真正实现 pm 数据范围——自定义 data_scope（非 apply_data_scope_filter），
      OR(created_by, EXISTS(AppraisalArticle→Article→director_id)) 子查询。
      跨模块读 Article（article_supply_service.py 已有先例）。
"""

from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, delete, exists, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app.appraisal.enums import LABELS as APPRAISAL_LABELS, MeetingState
from app.appraisal.models import (
    Appraisal,
    AppraisalArticle,
    AppraisalComment,
    AppraisalSupply,
)
from app.article.models import (
    Article,
    ArticleApproval,
    ArticleFeedback,
    ArticleOrder,
    ArticleSure,
    ArticleSureCustomer,
    ArticleSureWarrant,
)
from app.customer.models import Customer
from app.warrant.models import (
    Warrant,
    WarrantConstruction,
    WarrantGround,
    WarrantHouse,
    WarrantOwnership,
)
from app.appraisal.schemas import (
    AppraisalArrange,
    AppraisalCreate,
    AppraisalFinish,
    CommentBatchCreate,
    CommentItem,
    SupplyCreate,
    SupplyResolve,
    SummaryUpdate,
)
from app.article.enums import ArticleState
from app.article.models import Article, ArticleApproval
from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.user.models import User


# ============ 顶部标配 ============

def _get_or_404(db: Session, appraisal_id: int) -> Appraisal:
    a = db.get(Appraisal, appraisal_id)
    if a is None:
        raise BizError(4041, "评审会不存在")
    return a


def _disp(label: dict[int, str] | None, value: int | None) -> str | None:
    """从模块 LABELS 字典取中文 label（AGENTS.md §3.7.2 标准模式）。"""
    if value is None:
        return None
    if label is None:
        return str(value)
    return label.get(value, str(value))


def _resolve_scope_user_ids(
    db: Session, ctx: AuthContext
) -> list[int] | None:
    """解析 ctx 到归属用户 id 集合（v1.4 data_scope 共享 helper）。

    返回值语义：
    - None → ALL（跳过过滤）
    - []   → 空集（恒假）
    - [ids] → 具体用户
    """
    if ctx.is_super_admin or ctx.data_scope == 40:  # DataScope.ALL
        return None
    if ctx.data_scope == 10:  # DataScope.SELF
        return [ctx.user_id]
    if ctx.dept_scope_ids:
        return db.scalars(
            select(User.id).where(User.dept_id.in_(ctx.dept_scope_ids))
        ).all()
    return [ctx.user_id]  # 兜底：无 dept_scope_ids 按 SELF


def _build_appraisal_visibility_stmt(
    stmt: Select, scope_user_ids: list[int]
) -> Select:
    """追加评审会可见性过滤（OR created_by + EXISTS director 子查询）。

    v1.4 pm data_scope 核心逻辑，list_appraisals 和 get_appraisal 共用。
    """
    return stmt.where(
        or_(
            Appraisal.created_by.in_(scope_user_ids),
            exists(
                select(1).where(
                    and_(
                        AppraisalArticle.appraisal_id == Appraisal.id,
                        Article.id == AppraisalArticle.article_id,
                        Article.director_id.in_(scope_user_ids),
                    )
                )
            ),
        )
    )


# ============ 评审会 ============

def list_appraisals(
    db: Session,
    ctx: AuthContext,
    *,
    page: int = 1,
    page_size: int = 20,
    year: int | None = None,
    review_model: int | None = None,
    meeting_state: int | None = None,
) -> tuple[list[dict], int]:
    """评审会（AGENTS.md §3.7 + §6.4 + v1.4 data_scope）。

    v1.4 实现 pm 数据范围（自定义，不走 apply_data_scope_filter）：
    标准 apply_data_scope_filter 只支持 owner_field 简单列过滤，
    但 pm 需要看到"包含本人在办项目的评审会"——语义是
    OR(created_by == user_id, EXISTS AppraisalArticle→Article→director_id == user_id)。

    三态落地：
    - is_super_admin / data_scope=ALL(40) → 不追加条件
    - data_scope=SELF(10) → user_id 即 ctx.user_id
    - dept_scope_ids 非空 → 先查部门内用户 id，再套同一 OR 模式
    """
    stmt = select(Appraisal).order_by(Appraisal.created_at.desc())
    if year is not None:
        stmt = stmt.where(Appraisal.year == year)
    if review_model is not None:
        stmt = stmt.where(Appraisal.review_model == review_model)
    if meeting_state is not None:
        stmt = stmt.where(Appraisal.meeting_state == meeting_state)

    # ===== v1.4 自定义 data_scope =====
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    if scope_user_ids is not None:  # None = ALL，跳过
        if not scope_user_ids:
            return [], 0  # 部门内无用户：恒假
        stmt = _build_appraisal_visibility_stmt(stmt, scope_user_ids)
    # ===== data_scope 结束 =====

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()

    if not items:
        return [], total

    # §3.7.3 N+1 消除：合并 compere_id + created_by 到一次 User 查询
    compere_ids = {a.compere_id for a in items if a.compere_id}
    created_ids = {a.created_by for a in items if a.created_by}
    all_user_ids = compere_ids | created_ids
    users: dict[int, str] = {}
    if all_user_ids:
        users = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(all_user_ids))
            ).all()
        )

    # 子查询 count：每个 appraisal 的参评项目数（避免 N+1）
    aid_list = [a.id for a in items]
    count_rows = db.execute(
        select(
            AppraisalArticle.appraisal_id,
            func.count(AppraisalArticle.id),
        ).where(
            AppraisalArticle.appraisal_id.in_(aid_list)
        ).group_by(AppraisalArticle.appraisal_id)
    ).all()
    article_counts = {aid: cnt for aid, cnt in count_rows}

    result = []
    for a in items:
        result.append({
            "id": a.id,
            "num": a.num,
            "year": a.year,
            "seq": a.seq,
            "review_model": a.review_model,
            "review_model_display": _disp(APPRAISAL_LABELS.get("review_model"), a.review_model),
            "review_date": str(a.review_date) if a.review_date else None,
            "meeting_state": a.meeting_state,
            "meeting_state_display": _disp(APPRAISAL_LABELS.get("meeting_state"), a.meeting_state),
            "compere_id": a.compere_id,
            "compere_name": users.get(a.compere_id),
            "articles_count": article_counts.get(a.id, 0),
            "created_by": a.created_by,
            "created_by_name": users.get(a.created_by),
        })
    return result, total


def create_appraisal(
    db: Session, body: AppraisalCreate, user_id: int
) -> int:
    """创建评审会（自动编号）。"""
    year = body.review_date.year
    # 同年份 + 同类型内递增
    max_seq = db.scalar(
        select(Appraisal).where(
            Appraisal.year == year,
            Appraisal.review_model == body.review_model,
        ).order_by(Appraisal.seq.desc()).limit(1)
    )
    seq = (max_seq.seq + 1) if max_seq else 1
    num = f"{year}-{seq:02d}"

    # §3.7.6 前置唯一性预检
    if db.scalar(select(Appraisal).where(Appraisal.num == num)):
        raise BizError(4091, "评审会编号已存在，请重试")

    appraisal = Appraisal(
        num=num,
        year=year,
        seq=seq,
        review_model=body.review_model,
        review_date=body.review_date,
        compere_id=body.compere_id,
        meeting_state=MeetingState.PENDING.value,
        created_by=user_id,
    )
    db.add(appraisal)
    db.flush()

    # 创建时排入项目（可选）
    if body.article_ids:
        _arrange_articles(db, appraisal.id, body.article_ids)

    db.commit()
    return appraisal.id


def arrange_articles(
    db: Session, appraisal_id: int, body: AppraisalArrange, user_id: int
) -> None:
    """安排项目上会（项目状态 → 30 待上会）。"""
    _arrange_articles(db, appraisal_id, body.article_ids)
    db.commit()


def _arrange_articles(db: Session, appraisal_id: int, article_ids: list[int]) -> None:
    """排会核心逻辑（内部调用，不 commit）。"""
    appraisal = _get_or_404(db, appraisal_id)
    if appraisal.meeting_state != MeetingState.PENDING.value:
        raise BizError(4031, "仅待上会会议可排会")

    for aid in article_ids:
        article = db.get(Article, aid)
        if article is None:
            raise BizError(4041, f"项目 {aid} 不存在")
        # 排会门槛：已反馈(20) 或 待变更(61)
        if article.article_state not in (
            ArticleState.FEEDBACK_DONE.value,
            ArticleState.PENDING_CHANGE.value,
        ):
            raise BizError(4031, f"项目 {aid} 状态不符合排会门槛")

        # 不与其他待上会会议重复
        existing = db.scalar(
            select(AppraisalArticle).join(Appraisal).where(
                AppraisalArticle.article_id == aid,
                Appraisal.meeting_state == MeetingState.PENDING.value,
            )
        )
        if existing is not None:
            raise BizError(4031, f"项目 {aid} 已在另一待上会会议中")

        # 插入 M2M
        m2m = db.scalar(
            select(AppraisalArticle).where(
                AppraisalArticle.appraisal_id == appraisal_id,
                AppraisalArticle.article_id == aid,
            )
        )
        if m2m is None:
            db.add(AppraisalArticle(appraisal_id=appraisal_id, article_id=aid))

        # 项目状态 → 30
        article.article_state = ArticleState.PENDING_REVIEW.value


def remove_article(
    db: Session, appraisal_id: int, article_id: int, user_id: int
) -> None:
    """移出项目（状态回退 30 → 20）。"""
    appraisal = _get_or_404(db, appraisal_id)
    if appraisal.meeting_state != MeetingState.PENDING.value:
        raise BizError(4031, "仅待上会会议可移出项目")

    m2m = db.scalar(
        select(AppraisalArticle).where(
            AppraisalArticle.appraisal_id == appraisal_id,
            AppraisalArticle.article_id == article_id,
        )
    )
    if m2m is None:
        raise BizError(4041, "该项目不在本次评审会中")

    db.delete(m2m)
    # 状态回退
    article = db.get(Article, article_id)
    if article and article.article_state == ArticleState.PENDING_REVIEW.value:
        article.article_state = ArticleState.FEEDBACK_DONE.value

    db.commit()


def finish_appraisal(
    db: Session, appraisal_id: int, body: AppraisalFinish | None, user_id: int
) -> None:
    """会议完成（项目 30 → 40；生成纪要编号）。"""
    appraisal = _get_or_404(db, appraisal_id)
    if appraisal.meeting_state != MeetingState.PENDING.value:
        raise BizError(4031, "会议已完成")

    # 获取参评项目
    articles = db.scalars(
        select(Article).join(AppraisalArticle).where(
            AppraisalArticle.appraisal_id == appraisal_id
        )
    ).all()

    # 评审会状态 → 已上会
    appraisal.meeting_state = MeetingState.FINISHED.value
    finish_date = body.finish_date if body and body.finish_date else appraisal.review_date

    # 批量更新项目（跨模块写项目——评审模块是 owner，允许单向轻量写）
    for article in articles:
        article.article_state = ArticleState.REVIEW_DONE.value
        # 评审字段写一对一表 ArticleApproval
        ap = db.scalar(select(ArticleApproval).where(ArticleApproval.article_id == article.id))
        if ap is None:
            ap = ArticleApproval(article_id=article.id)
            db.add(ap)
            db.flush()
        ap.review_date = finish_date
        if ap.summary_num is None:
            ap.summary_num = f"JY{appraisal.year}{appraisal.seq:02d}"

    db.commit()


def get_appraisal(db: Session, ctx: AuthContext, appraisal_id: int) -> dict:
    """评审会完整详情（#2a，聚合视图）。

    聚合已有子接口：基础信息 + 参评项目清单（带补调/意见指标）。
    完整意见矩阵见 #12（独立接口），此处做适度收敛。

    N+1 消除：
    - User 批量合并 compere_id + created_by
    - 补调指标：子查询按 appraisal_id 下的所有 article_id 聚合
    - 意见指标：同上
    """
    appraisal = _get_or_404(db, appraisal_id)

    # ===== v1.4 单记录可见性检查（防止 ID 撞库绕过 list data_scope）=====
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    if scope_user_ids is not None:  # None = ALL，跳过
        visible_stmt = _build_appraisal_visibility_stmt(
            select(Appraisal.id).where(Appraisal.id == appraisal_id),
            scope_user_ids,
        )
        if db.scalar(visible_stmt) is None:
            raise BizError(4041, "评审会不存在")  # 4041 避免暴露 ID 是否有效
    # ===== 可见性检查结束 =====

    # N+1：合并 compere_id + created_by
    all_user_ids = {uid for uid in [appraisal.compere_id, appraisal.created_by] if uid}
    users: dict[int, str] = {}
    if all_user_ids:
        users = dict(
            db.execute(select(User.id, User.name).where(User.id.in_(all_user_ids))).all()
        )

    # 参评项目清单（复用 list_appraisal_articles 的查询逻辑）
    articles = list_appraisal_articles(db, appraisal_id)
    article_ids = [a["article_id"] for a in articles]

    # 补调指标：每个 project 的总数 + 待解决数
    supply_counts: dict[int, dict] = {}
    if article_ids:
        supply_rows = db.execute(
            select(
                AppraisalSupply.article_id,
                func.count().label("total"),
                func.sum(case((AppraisalSupply.is_resolved == False, 1), else_=0)).label("pending"),
            ).where(
                AppraisalSupply.article_id.in_(article_ids)
            ).group_by(AppraisalSupply.article_id)
        ).all()
        supply_counts = {
            aid: {"total": int(t or 0), "pending": int(p or 0)}
            for aid, t, p in supply_rows
        }

    # 意见指标：每个 project 的已发表意见数
    comment_counts: dict[int, int] = {}
    if article_ids:
        comment_rows = db.execute(
            select(
                AppraisalComment.article_id,
                func.count(),
            ).where(
                AppraisalComment.article_id.in_(article_ids)
            ).group_by(AppraisalComment.article_id)
        ).all()
        comment_counts = {aid: cnt for aid, cnt in comment_rows}

    articles_out = []
    for a in articles:
        a["supplies"] = supply_counts.get(a["article_id"], {"total": 0, "pending": 0})
        a["comments_count"] = comment_counts.get(a["article_id"], 0)
        articles_out.append(a)

    return {
        "id": appraisal.id,
        "num": appraisal.num,
        "year": appraisal.year,
        "seq": appraisal.seq,
        "review_model": appraisal.review_model,
        "review_model_display": _disp(APPRAISAL_LABELS.get("review_model"), appraisal.review_model),
        "review_date": str(appraisal.review_date) if appraisal.review_date else None,
        "compere_id": appraisal.compere_id,
        "compere_name": users.get(appraisal.compere_id),
        "meeting_state": appraisal.meeting_state,
        "meeting_state_display": _disp(APPRAISAL_LABELS.get("meeting_state"), appraisal.meeting_state),
        "created_by": appraisal.created_by,
        "created_by_name": users.get(appraisal.created_by),
        "created_at": str(appraisal.created_at) if appraisal.created_at else None,
        "updated_at": str(appraisal.updated_at) if appraisal.updated_at else None,
        "articles": articles_out,
        "articles_count": len(articles_out),
    }


def list_appraisal_articles(db: Session, appraisal_id: int) -> list[dict]:
    """评审会详情：参评项目清单（§3.2 详情接口的 articles 子块）。

    路由引用此函数（appraisals.py 58-60 行），原来缺失。
    """
    appraisal = _get_or_404(db, appraisal_id)

    rows = db.execute(
        select(
            Article.id,
            Article.article_num,
            (func.coalesce(Article.renewal, 0) + func.coalesce(Article.augment, 0)).label("amount"),
            Article.article_state,
            Article.director_id,
            Customer.name.label("customer_name"),
        ).join(
            AppraisalArticle, AppraisalArticle.article_id == Article.id
        ).outerjoin(
            Customer, Customer.id == Article.customer_id
        ).where(AppraisalArticle.appraisal_id == appraisal_id)
    ).all()

    # 批量查 director 名称（避免 N+1）
    director_ids = {r.director_id for r in rows if r.director_id}
    directors = {}
    if director_ids:
        directors = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(director_ids))
            ).all()
        )

    return [
        {
            "article_id": r.id,
            "article_num": r.article_num,
            "customer_name": r.customer_name,
            "amount": r.amount,
            "article_state": r.article_state,
            "article_state_display": _disp(
                APPRAISAL_LABELS.get("article_state"), r.article_state
            ) or _article_state_label(r.article_state),
            "director_id": r.director_id,
            "director_name": directors.get(r.director_id),
        }
        for r in rows
    ]


def _article_state_label(value: int | None) -> str | None:
    """跨模块枚举取中文（ArticleState 在 article.enums 中，非 appraisal.enums）。"""
    if value is None:
        return None
    try:
        return ArticleState(value).label
    except ValueError:
        return str(value)


def delete_appraisal(db: Session, appraisal_id: int, user_id: int) -> None:
    """删除评审会（仅未完成的可删）。"""
    appraisal = _get_or_404(db, appraisal_id)
    if appraisal.meeting_state == MeetingState.FINISHED.value:
        raise BizError(4031, "已完成的评审会不能删除")
    # 清理关联的 AppraisalArticle（FK CASCADE 自动清子，但这里显式删中间表也对）
    db.execute(
        delete(AppraisalArticle).where(AppraisalArticle.appraisal_id == appraisal_id)
    )
    db.delete(appraisal)
    db.commit()


# ============ 评委意见 ============

def list_article_comments(db: Session, article_id: int) -> list[dict]:
    """项目的评委意见列表（#11，N+1 消除）。

    联表取 ReviewExpert.name（评委姓名），一条批量查询。
    """
    rows = db.execute(
        select(
            AppraisalComment.id,
            AppraisalComment.expert_id,
            AppraisalComment.comment,
            AppraisalComment.detail,
            AppraisalComment.created_at,
            ReviewExpert.name.label("expert_name"),
        ).outerjoin(
            ReviewExpert, ReviewExpert.id == AppraisalComment.expert_id
        ).where(
            AppraisalComment.article_id == article_id
        ).order_by(AppraisalComment.id.desc())
    ).all()

    return [
        {
            "id": r.id,
            "expert_id": r.expert_id,
            "expert_name": r.expert_name or f"#{r.expert_id}",
            "comment": r.comment,
            "comment_display": _disp(APPRAISAL_LABELS.get("comment_type"), r.comment),
            "detail": r.detail,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]


def batch_upsert_comments(
    db: Session, article_id: int, body: CommentBatchCreate, user_id: int
) -> int:
    """批量录入评委意见（upsert）。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    # 状态门槛：待上会(30)/已上会(40)/待变更(61)
    allowed = {
        ArticleState.PENDING_REVIEW.value,
        ArticleState.REVIEW_DONE.value,
        ArticleState.PENDING_CHANGE.value,
    }
    if article.article_state not in allowed:
        raise BizError(4031, "当前状态不允许录入意见")

    count = 0
    for item in body.items:
        comment = db.scalar(
            select(AppraisalComment).where(
                AppraisalComment.article_id == article_id,
                AppraisalComment.expert_id == item.expert_id,
            )
        )
        if comment is None:
            comment = AppraisalComment(
                article_id=article_id, expert_id=item.expert_id
            )
            db.add(comment)

        comment.comment = item.comment
        comment.detail = item.detail
        count += 1

    db.commit()
    return count


# ============ 补调问题 ============

def add_supply(
    db: Session, article_id: int, body: SupplyCreate, user_id: int
) -> None:
    """添加补调问题（状态门槛：待反馈/已反馈/待上会/已上会/待变更）。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    allowed = {
        ArticleState.PENDING_FEEDBACK.value,
        ArticleState.FEEDBACK_DONE.value,
        ArticleState.PENDING_REVIEW.value,
        ArticleState.REVIEW_DONE.value,
        ArticleState.PENDING_CHANGE.value,
    }
    if article.article_state not in allowed:
        raise BizError(4031, "当前状态不允许添加补调")

    db.add(AppraisalSupply(
        article_id=article_id,
        supply_detail=body.supply_detail,
        supplier_id=user_id,
        is_resolved=False,
    ))
    db.commit()


def resolve_supply(
    db: Session, supply_id: int, body: SupplyResolve, user_id: int
) -> None:
    """补调完成登记。"""
    supply = db.get(AppraisalSupply, supply_id)
    if supply is None:
        raise BizError(4041, "补调问题不存在")

    supply.is_resolved = True
    supply.resolve_reply = body.resolve_reply
    supply.resolved_by = user_id
    supply.resolved_at = datetime.now()
    db.commit()


def update_supply(
    db: Session, supply_id: int, supply_detail: str | None,
    reopen: bool | None, user_id: int, ctx: AuthContext | None = None,
) -> None:
    """修改补调（#26 PATCH）。

    两种操作：
    1) supply_detail 变更：同 add_supply 状态门槛，任何有 appraisal:update 权限的用户
    2) reopen=True：补调重开（is_resolved→false）——**仅 dept_manager 及以上角色**（§3.28 设计约束）
       审计留痕：只重置 is_resolved + resolve_reply，resolved_by/resolved_at 保留
    """
    supply = db.get(AppraisalSupply, supply_id)
    if supply is None:
        raise BizError(4041, "补调问题不存在")

    # 取所属项目校验状态门槛
    article = db.get(Article, supply.article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    allowed = {
        ArticleState.PENDING_FEEDBACK.value,
        ArticleState.FEEDBACK_DONE.value,
        ArticleState.PENDING_REVIEW.value,
        ArticleState.REVIEW_DONE.value,
        ArticleState.PENDING_CHANGE.value,
    }
    if article.article_state not in allowed:
        raise BizError(4031, "当前项目状态不允许修改补调")

    if supply_detail is not None:
        supply.supply_detail = supply_detail

    if reopen:
        # §3.28 设计约束：仅 dept_manager / risk_leader / super_admin 可 reopen
        if ctx is None or not (
            ctx.is_super_admin
            or ctx.data_scope == 40
            or "dept_manager" in ctx.role_codes
            or "risk_leader" in ctx.role_codes
            or "committee_secretary" in ctx.role_codes
        ):
            raise BizError(4031, "仅部门负责人及以上角色可重开已解决补调")
        supply.is_resolved = False
        supply.resolve_reply = None
        # resolved_by/resolved_at 保留为审计痕迹（§3.28 留痕要求）

    db.commit()


def delete_supply(db: Session, supply_id: int, user_id: int) -> None:
    """删除补调问题（#27 DELETE，同状态门槛）。"""
    supply = db.get(AppraisalSupply, supply_id)
    if supply is None:
        raise BizError(4041, "补调问题不存在")

    article = db.get(Article, supply.article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    allowed = {
        ArticleState.PENDING_FEEDBACK.value,
        ArticleState.FEEDBACK_DONE.value,
        ArticleState.PENDING_REVIEW.value,
        ArticleState.REVIEW_DONE.value,
        ArticleState.PENDING_CHANGE.value,
    }
    if article.article_state not in allowed:
        raise BizError(4031, "当前项目状态不允许删除补调")

    db.delete(supply)
    db.commit()


# ============ 会议意见汇总矩阵 ============

def list_appraisal_comment_matrix(
    db: Session, ctx: AuthContext, appraisal_id: int
) -> dict:
    """会议意见汇总矩阵（#12，核心视图）。

    设计文档 §3.12：experts 列表 + article×expert 矩阵 + 未解决补调。
    评委来源：该评审会所有参评项目中发表过意见的专家（无专门排会-专家关联表）。
    """
    appraisal = _get_or_404(db, appraisal_id)

    # v1.4 可见性检查
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    if scope_user_ids is not None:
        visible_stmt = _build_appraisal_visibility_stmt(
            select(Appraisal.id).where(Appraisal.id == appraisal_id),
            scope_user_ids,
        )
        if db.scalar(visible_stmt) is None:
            raise BizError(4041, "评审会不存在")

    # 1) 参评项目
    article_rows = db.execute(
        select(
            Article.id, Article.article_num,
            Customer.name.label("customer_name"),
        ).join(
            AppraisalArticle, AppraisalArticle.article_id == Article.id
        ).outerjoin(
            Customer, Customer.id == Article.customer_id
        ).where(
            AppraisalArticle.appraisal_id == appraisal_id
        ).order_by(Article.id)
    ).all()
    if not article_rows:
        return {"experts": [], "matrix": [], "unresolved_supplies": []}

    article_ids = [r.id for r in article_rows]

    # 2) 所有意见 + 关联专家姓名
    comment_rows = db.execute(
        select(
            AppraisalComment.article_id,
            AppraisalComment.expert_id,
            AppraisalComment.comment,
            AppraisalComment.detail,
            ReviewExpert.name.label("expert_name"),
        ).outerjoin(
            ReviewExpert, ReviewExpert.id == AppraisalComment.expert_id
        ).where(
            AppraisalComment.article_id.in_(article_ids)
        )
    ).all()

    # 3) 构建 experts 列表（去重，按 expert_id）
    expert_order: dict[int, int] = {}
    experts: list[dict] = []
    for row in comment_rows:
        if row.expert_id not in expert_order:
            expert_order[row.expert_id] = len(experts)
            experts.append({
                "id": row.expert_id,
                "name": row.expert_name or f"#{row.expert_id}",
            })

    # 4) 按 article_id 分组意见
    opinions_by_article: dict[int, dict[int, dict]] = {}
    for row in comment_rows:
        opinions_by_article.setdefault(row.article_id, {})[row.expert_id] = {
            "expert_id": row.expert_id,
            "comment": row.comment,
            "comment_display": _disp(
                APPRAISAL_LABELS.get("comment_type"), row.comment
            ),
            "detail": row.detail,
        }

    # 5) 构建矩阵：每个 article 一行，opinions 与 experts 对齐
    matrix = []
    for aid, anum, cname in article_rows:
        row_opinions = opinions_by_article.get(aid, {})
        opinions_cell = [
            row_opinions.get(
                e["id"],
                {"expert_id": e["id"], "comment": None, "detail": None},
            )
            for e in experts
        ]
        # summary_opinion：按 comment 统计
        ctype_counts: dict[int, int] = {}
        has_opinion = 0
        for op in row_opinions.values():
            has_opinion += 1
            ct = op.get("comment")
            if ct is not None:
                ctype_counts[ct] = ctype_counts.get(ct, 0) + 1
        total_experts = len(experts)
        summary = f"{has_opinion}/{total_experts} 已发表"
        if ctype_counts:
            parts = [
                f"{_disp(APPRAISAL_LABELS.get('comment_type'), ct) or ct}:{cnt}"
                for ct, cnt in ctype_counts.items()
            ]
            summary += "（" + "、".join(parts) + "）"

        matrix.append({
            "article_id": aid,
            "article_num": anum,
            "customer_name": cname,
            "opinions": opinions_cell,
            "summary_opinion": summary,
        })

    # 6) 未解决补调清单
    supply_rows = db.execute(
        select(
            AppraisalSupply.id,
            AppraisalSupply.article_id,
            AppraisalSupply.supply_detail,
            AppraisalSupply.created_at,
        ).where(
            AppraisalSupply.article_id.in_(article_ids),
            AppraisalSupply.is_resolved == False,  # noqa: E712
        ).order_by(AppraisalSupply.id)
    ).all()
    article_num_map = {r.id: r.article_num for r in article_rows}
    unresolved_supplies = [
        {
            "id": s.id,
            "article_id": s.article_id,
            "article_num": article_num_map.get(s.article_id),
            "supply_detail": s.supply_detail,
            "created_at": str(s.created_at) if s.created_at else None,
        }
        for s in supply_rows
    ]

    return {
        "experts": experts,
        "matrix": matrix,
        "unresolved_supplies": unresolved_supplies,
    }


# ============ 待上会项目池 ============

def list_pending_projects(db: Session, ctx: AuthContext) -> list[dict]:
    """待上会项目池（#31，排会弹窗选择）。

    项目状态=FEEDBACK_DONE(20) 或 PENDING_CHANGE(61)，
    且不在任何 meeting_state=PENDING 的评审会中。

    data_scope：按 Article.director_id 过滤（AGENTS.md §3.7.1 owner_field 模式）。
    """
    # 排除：已排入未完成评审会的 article_id
    excluded = db.scalars(
        select(AppraisalArticle.article_id).join(
            Appraisal, Appraisal.id == AppraisalArticle.appraisal_id
        ).where(
            Appraisal.meeting_state == MeetingState.PENDING.value,
        )
    ).all()

    stmt = select(Article).where(
        Article.article_state.in_([
            ArticleState.FEEDBACK_DONE.value,
            ArticleState.PENDING_CHANGE.value,
        ]),
    ).order_by(Article.updated_at.desc())
    if excluded:
        stmt = stmt.where(Article.id.notin_(excluded))

    # data_scope：按 director_id（项目归属人）过滤
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    if scope_user_ids is not None:  # None = ALL，跳过
        if not scope_user_ids:
            return []
        stmt = stmt.where(Article.director_id.in_(scope_user_ids))

    items = db.scalars(stmt).all()

    # 批量查 customer + director（避免 N+1）
    customer_ids = {a.customer_id for a in items if a.customer_id}
    customers: dict[int, str] = {}
    if customer_ids:
        customers = dict(
            db.execute(
                select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids))
            ).all()
        )

    director_ids = {a.director_id for a in items if a.director_id}
    directors: dict[int, str] = {}
    if director_ids:
        directors = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(director_ids))
            ).all()
        )

    return [
        {
            "article_id": a.id,
            "article_num": a.article_num,
            "customer_name": customers.get(a.customer_id),
            "amount": float((a.renewal or 0) + (a.augment or 0)),
            "article_state": a.article_state,
            "article_state_display": _article_state_label(a.article_state),
            "director_id": a.director_id,
            "director_name": directors.get(a.director_id),
            "updated_at": str(a.updated_at) if a.updated_at else None,
        }
        for a in items
    ]


def update_summary(
    db: Session, article_id: int, body: SummaryUpdate, user_id: int
) -> None:
    """纪要编辑（已上会/待变更状态）。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (
        ArticleState.REVIEW_DONE.value,
        ArticleState.PENDING_CHANGE.value,
    ):
        raise BizError(4031, "已上会后可编辑纪要")

    ap = db.scalar(select(ArticleApproval).where(ArticleApproval.article_id == article.id))
    if ap is None:
        ap = ArticleApproval(article_id=article.id)
        db.add(ap)
        db.flush()
    if body.summary is not None:
        ap.summary = body.summary
    if body.opinion is not None:
        ap.opinion = body.opinion

    db.commit()


# ============ 评审材料包聚合（v1.6 #30 / #9）============

def _check_article_visibility(db: Session, article_id: int, ctx: AuthContext | None) -> None:
    """单项目可见性校验（#30 数据范围）。

    策略：非管理员时 Article.director_id 必须在 scope_user_ids 内。
    与 list_pending_projects 保持一致（owner_field 模式）。
    """
    if ctx is None or ctx.is_super_admin or ctx.data_scope == 40:
        return  # 全量可见

    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    if scope_user_ids is None:
        return  # None = ALL

    art = db.get(Article, article_id)
    if art is None:
        raise BizError(4041, "项目不存在")

    if art.director_id not in scope_user_ids:
        # 还要检查是否在本人评审过的评审会中（AppraisalArticle → Appraisal → created_by）
        in_my_appraisal = db.execute(
            select(Appraisal).join(
                AppraisalArticle, AppraisalArticle.appraisal_id == Appraisal.id
            ).where(
                AppraisalArticle.article_id == article_id,
                Appraisal.created_by == ctx.user_id,
            )
        ).scalar_one_or_none()
        if in_my_appraisal is None:
            raise BizError(4041, "项目不存在或无权限查看")


def get_article_appraisal_report(
    db: Session, ctx: AuthContext, article_id: int
) -> dict:
    """单项目评审材料包（#30）。

    跨模块只读聚合：article + customer + summary + sures(反担保+权证) +
    lending_orders(放款次序) + comments(评委意见) + supplies(补调)。
    survey / single_quotas 因无 DB 表返回 null/空数组（设计文档 aspirational）。
    """
    _check_article_visibility(db, article_id, ctx)

    # ---- 1. Article + ArticleApproval + Customer（一次 JOIN 到位） ----
    row = db.execute(
        select(
            Article.id,
            Article.article_num,
            Article.article_state,
            Article.customer_id,
            Article.product_id,
            Article.renewal,
            Article.augment,
            Article.credit_term,
            Article.credit_term_unit,
            Article.director_id,
            Article.assistant_id,
            Article.control_id,
            ArticleApproval.summary_num,
            ArticleApproval.summary,
            ArticleApproval.opinion,
            ArticleApproval.sign_type,
            ArticleApproval.sign_date,
            Customer.name.label("customer_name"),
        ).outerjoin(
            ArticleApproval, ArticleApproval.article_id == Article.id
        ).outerjoin(
            Customer, Customer.id == Article.customer_id
        ).where(Article.id == article_id)
    ).first()
    if row is None:
        raise BizError(4041, "项目不存在")

    # ---- 2. 经理 / 助理 / 风控 批量查 ----
    staff_ids = {row.director_id, row.assistant_id, row.control_id} - {None}
    staff_names: dict[int, str] = {}
    if staff_ids:
        staff_names = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(staff_ids))
            ).all()
        )

    article_payload = {
        "id": row.id,
        "article_num": row.article_num,
        "article_state": row.article_state,
        "article_state_display": _article_state_label(row.article_state),
        "customer_id": row.customer_id,
        "customer_name": row.customer_name,
        "product_id": row.product_id,
        "amount": float((row.renewal or 0) + (row.augment or 0)),
        "renewal": float(row.renewal or 0),
        "augment": float(row.augment or 0),
        "credit_term": row.credit_term,
        "director_id": row.director_id,
        "director_name": staff_names.get(row.director_id),
        "assistant_name": staff_names.get(row.assistant_id),
        "control_name": staff_names.get(row.control_id),
    }
    summary_payload = {
        "summary_num": row.summary_num,
        "summary": row.summary,
        "opinion": row.opinion,
        "sign_type": row.sign_type,
        "sign_type_display": {1: "同意", 2: "不同意"}.get(row.sign_type),
        "sign_date": str(row.sign_date) if row.sign_date else None,
    }

    # ---- 3. 放款次序 ArticleOrder ----
    order_rows = db.execute(
        select(ArticleOrder).where(ArticleOrder.article_id == article_id)
        .order_by(ArticleOrder.seq)
    ).scalars().all()
    lending_orders = [
        {
            "seq": o.seq,
            "order_amount": float(o.order_amount or 0),
            "state": o.state,
            "remark": o.remark,
        }
        for o in order_rows
    ]

    # ---- 4. 反担保措施 ArticleSure + ArticleSureWarrant → Warrant → WarrantHouse/Ground ----
    sures = _load_sures(db, article_id)

    # ---- 5. 评委意见 + 补调 ----
    try:
        comments = list_article_comments(db, article_id)
    except Exception:
        comments = []

    supplies = _load_supplies(db, article_id)

    return {
        "article": article_payload,
        "customer": {
            "id": row.customer_id,
            "name": row.customer_name,
        },
        "survey": None,            # 无 DB 表
        "sures": sures,
        "single_quotas": [],       # 无 DB 表
        "lending_orders": lending_orders,
        "comments": comments,
        "supplies": supplies,
        "summary": summary_payload,
    }


def _load_sures(db: Session, article_id: int) -> list[dict]:
    """反担保措施清单（带权证详情）。

    链路：ArticleSure(article_id) → ArticleSureWarrant(sure_id) →
    Warrant(warrant_id) → WarrantHouse / WarrantGround / WarrantConstruction。
    另外 ArticleSureCustomer（保证类）。
    """
    sure_rows = db.execute(
        select(ArticleSure).where(ArticleSure.article_id == article_id)
        .order_by(ArticleSure.order_id, ArticleSure.id)
    ).scalars().all()
    if not sure_rows:
        return []

    sure_ids = {s.id for s in sure_rows}

    # ArticleSure → Warrant 批量查
    sw_rows = db.execute(
        select(
            ArticleSureWarrant.sure_id,
            ArticleSureWarrant.warrant_id,
        ).where(ArticleSureWarrant.sure_id.in_(sure_ids))
    ).all()
    warrant_ids = {w.warrant_id for w in sw_rows}

    # Warrant + 房产/土地/在建 批量查
    warrants: dict[int, dict] = {}
    if warrant_ids:
        for w in db.execute(
            select(Warrant.id, Warrant.warrant_num, Warrant.warrant_type,
                   Warrant.warrant_state)
            .where(Warrant.id.in_(warrant_ids))
        ).all():
            warrants[w.id] = {
                "warrant_id": w.id,
                "warrant_num": w.warrant_num,
                "warrant_type": w.warrant_type,
                "warrant_type_display": {11: "房产", 14: "土地", 16: "在建",
                    21: "应收", 31: "票据", 41: "股权", 51: "车辆",
                    61: "动产", 91: "其他", 99: "他权"}.get(w.warrant_type),
                "houses": [], "grounds": [], "constructions": [],
            }

        # 房产
        for wh in db.execute(
            select(WarrantHouse.warrant_id, WarrantHouse.house_locate,
                   WarrantHouse.house_area)
            .where(WarrantHouse.warrant_id.in_(warrant_ids))
        ).all():
            if wh.warrant_id in warrants:
                warrants[wh.warrant_id]["houses"].append({
                    "house_locate": wh.house_locate,
                    "house_area": float(wh.house_area),
                })
        # 土地
        for g in db.execute(
            select(WarrantGround.warrant_id, WarrantGround.ground_locate,
                   WarrantGround.ground_area)
            .where(WarrantGround.warrant_id.in_(warrant_ids))
        ).all():
            if g.warrant_id in warrants:
                warrants[g.warrant_id]["grounds"].append({
                    "ground_locate": g.ground_locate,
                    "ground_area": float(g.ground_area),
                })
        # 在建
        for c in db.execute(
            select(WarrantConstruction.warrant_id, WarrantConstruction.construct_locate,
                   WarrantConstruction.construct_area)
            .where(WarrantConstruction.warrant_id.in_(warrant_ids))
        ).all():
            if c.warrant_id in warrants:
                warrants[c.warrant_id]["constructions"].append({
                    "construct_locate": c.construct_locate,
                    "construct_area": float(c.construct_area),
                })

        # 所有权人（WarrantOwnership → Customer）
        ow_rows = db.execute(
            select(WarrantOwnership.warrant_id, Customer.name)
            .join(Customer, Customer.id == WarrantOwnership.owner_id)
            .where(WarrantOwnership.warrant_id.in_(warrant_ids))
        ).all()
        for ow in ow_rows:
            if ow.warrant_id in warrants:
                warrants[ow.warrant_id].setdefault("owners", []).append(ow.name)

    # ArticleSureCustomer（保证类）
    sc_rows = db.execute(
        select(ArticleSureCustomer.sure_id, ArticleSureCustomer.customer_id,
               Customer.name)
        .join(Customer, Customer.id == ArticleSureCustomer.customer_id)
        .where(ArticleSureCustomer.sure_id.in_(sure_ids))
    ).all()
    sure_customers: dict[int, list[str]] = {}
    for sc in sc_rows:
        sure_customers.setdefault(sc.sure_id, []).append(sc.name)

    # 组装 sure list
    sw_map: dict[int, list[int]] = {}  # sure_id → [warrant_id, ...]
    for sw in sw_rows:
        sw_map.setdefault(sw.sure_id, []).append(sw.warrant_id)

    sure_type_display = {10: "信用", 20: "保证", 30: "抵押",
                         40: "质押", 50: "留置", 60: "定金"}
    ware_cat_display = {10: "人保", 20: "物保", 30: "金钱保"}

    result = []
    for s in sure_rows:
        warrant_ids_for_sure = sw_map.get(s.id, [])
        warrant_list = [warrants[wid] for wid in warrant_ids_for_sure if wid in warrants]
        result.append({
            "sure_id": s.id,
            "order_id": s.order_id,
            "ware_category": s.ware_category,
            "ware_category_display": ware_cat_display.get(s.ware_category),
            "method_category": s.method_category,
            "method_category_display": sure_type_display.get(s.method_category),
            "remark": s.remark,
            "warrants": warrant_list,
            "guarantors": sure_customers.get(s.id, []),
        })
    return result


def _load_supplies(db: Session, article_id: int) -> list[dict]:
    """补调问题清单（带创建人 / 解决人名称）。"""
    rows = db.execute(
        select(AppraisalSupply).where(AppraisalSupply.article_id == article_id)
        .order_by(AppraisalSupply.is_resolved, AppraisalSupply.created_at.desc())
    ).scalars().all()

    # 批量查所有涉及的 user（supplier + resolver）
    user_ids = set()
    for supply in rows:
        if supply.supplier_id:
            user_ids.add(supply.supplier_id)
        if supply.resolved_by:
            user_ids.add(supply.resolved_by)
    names = {}
    if user_ids:
        names = dict(
            db.execute(select(User.id, User.name).where(User.id.in_(user_ids))).all()
        )

    return [
        {
            "id": s.id,
            "supply_detail": s.supply_detail,
            "is_resolved": s.is_resolved,
            "resolve_reply": s.resolve_reply,
            "resolved_at": str(s.resolved_at) if s.resolved_at else None,
            "supplier_id": s.supplier_id,
            "supplier_name": names.get(s.supplier_id),
            "resolved_by": s.resolved_by,
            "resolver_name": names.get(s.resolved_by),
            "created_at": str(s.created_at) if s.created_at else None,
        }
        for s in rows
    ]


def get_appraisal_material_report(
    db: Session, ctx: AuthContext, appraisal_id: int
) -> dict:
    """会议材料包（#9）= 会议封面 + 循环调用 #30 单项目材料包。

    纯组合层：先查会议基本信息 + 参评项目清单，再循环 `get_article_appraisal_report`。
    """
    appraisal = _get_or_404(db, appraisal_id)
    # 复用 get_appraisal 的可见性检查（三态 data_scope）
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    # None = ALL（超管或 data_scope=40），跳过 visibility_stmt，直接可见
    if scope_user_ids is not None:
        visibility_stmt = _build_appraisal_visibility_stmt(
            select(Appraisal.id).where(Appraisal.id == appraisal_id),
            scope_user_ids,
        )
        visible = db.execute(visibility_stmt).scalar_one_or_none()
        if visible is None:
            raise BizError(4041, "评审会不存在或无权限查看")

    # ---- 会议封面 ----
    compere_name = None
    if appraisal.compere_id:
        compere_name = db.execute(
            select(User.name).where(User.id == appraisal.compere_id)
        ).scalar_one_or_none()

    meeting_cover = {
        "appraisal_id": appraisal.id,
        "num": appraisal.num,
        "year": appraisal.year,
        "seq": appraisal.seq,
        "review_model": appraisal.review_model,
        "review_model_display": _disp(APPRAISAL_LABELS.get("review_model"),
                                      appraisal.review_model),
        "review_date": str(appraisal.review_date) if appraisal.review_date else None,
        "compere_id": appraisal.compere_id,
        "compere_name": compere_name,
    }

    # ---- 参评项目清单 ----
    art_ids = [
        r[0] for r in db.execute(
            select(AppraisalArticle.article_id)
            .where(AppraisalArticle.appraisal_id == appraisal_id)
        ).all()
    ]

    articles_report = []
    for aid in art_ids:
        try:
            articles_report.append(
                get_article_appraisal_report(db, ctx, aid)
            )
        except BizError:
            # 某些项目可能不在当前用户可见范围（跨部门项目），跳过
            continue

    return {
        "meeting": meeting_cover,
        "articles": articles_report,
        "total_articles": len(art_ids),
        "visible_articles": len(articles_report),
    }


# ============ 统计看板（v1.7 #32 / #33）============

def get_appraisal_stats(
    db: Session, ctx: AuthContext, year: int | None = None
) -> dict:
    """评审统计（#32）。

    - by_model: 按 review_model 分组的会议数 + 项目数
    - through_rate: sign_type=1 数 / 已签批总数
    - opinion_distribution: 按 comment_type 分组的意见数
    - avg_cycle_days: 反馈→上会平均天数（ArticleFeedback.created_at → Appraisal.review_date）

    data_scope: 先过滤 Appraisal 可见性（三态复用），再基于过滤后的
    appraisal_id 做所有子聚合（会议/通过率/意见/周期）。
    """
    if year is None:
        year = date.today().year

    # ---- data_scope：先过滤出可见 appraisal_id ----
    scope_user_ids = _resolve_scope_user_ids(db, ctx)
    filtered_appraisals = select(Appraisal).where(Appraisal.year == year)
    if scope_user_ids is not None:
        filtered_appraisals = _build_appraisal_visibility_stmt(
            filtered_appraisals, scope_user_ids,
        )
    visible_appraisals = db.execute(filtered_appraisals).scalars().all()
    visible_ids = [a.id for a in visible_appraisals]
    is_unfiltered = scope_user_ids is None

    # ---- 1. 按 review_model 分组 ----
    base_q = select(
        Appraisal.review_model,
        func.count().label("meetings_count"),
        func.count(AppraisalArticle.id).label("articles_count"),
    ).outerjoin(
        AppraisalArticle, AppraisalArticle.appraisal_id == Appraisal.id
    ).where(
        Appraisal.year == year,
    )
    if not is_unfiltered:
        base_q = base_q.where(Appraisal.id.in_(visible_ids))
    base_q = base_q.group_by(Appraisal.review_model)

    model_rows = db.execute(base_q).all()
    by_model = []
    total_meetings = 0
    total_articles_in_meetings = 0
    for m, m_cnt, a_cnt in model_rows:
        label = _disp(APPRAISAL_LABELS.get("review_model"), m)
        by_model.append({
            "review_model": m,
            "review_model_display": label or str(m),
            "meetings_count": int(m_cnt),
            "articles_count": int(a_cnt or 0),
        })
        total_meetings += int(m_cnt)
        total_articles_in_meetings += int(a_cnt or 0)

    # ---- 2. 通过率 + 意见分布：先拿 article_id 子查询 ----
    art_base = select(AppraisalArticle.article_id).join(
        Appraisal, Appraisal.id == AppraisalArticle.appraisal_id
    ).where(Appraisal.year == year)
    if not is_unfiltered:
        art_base = art_base.where(Appraisal.id.in_(visible_ids))
    art_ids_subq = art_base.distinct().subquery()

    # 通过率
    sign_rows = db.execute(
        select(ArticleApproval.sign_type).where(
            ArticleApproval.sign_date.isnot(None),
            ArticleApproval.article_id.in_(select(art_ids_subq.c.article_id)),
        )
    ).all()
    signed_total = len(sign_rows)
    signed_agree = sum(1 for (st,) in sign_rows if st == 1)
    through_rate = round(signed_agree / signed_total * 100, 2) if signed_total else 0.0

    # 意见分布（排除 comment_type=0 未发表）
    opinion_rows = db.execute(
        select(
            AppraisalComment.comment,
            func.count().label("cnt"),
        ).where(
            AppraisalComment.article_id.in_(select(art_ids_subq.c.article_id)),
            AppraisalComment.comment != 0,
        ).group_by(AppraisalComment.comment)
    ).all()
    opinion_distribution = {}
    for ct, cnt in opinion_rows:
        opinion_distribution[str(ct)] = {
            "count": int(cnt),
            "label": _disp(APPRAISAL_LABELS.get("comment_type"), ct) or str(ct),
        }

    # ---- 3. 平均上会周期 ----
    cycle_q = select(
        func.datediff(Appraisal.review_date, ArticleFeedback.created_at).label("days"),
    ).join(
        AppraisalArticle, AppraisalArticle.appraisal_id == Appraisal.id
    ).join(
        ArticleFeedback, ArticleFeedback.article_id == AppraisalArticle.article_id
    ).where(
        Appraisal.year == year,
        Appraisal.review_date.isnot(None),
        ArticleFeedback.created_at.isnot(None),
    )
    if not is_unfiltered:
        cycle_q = cycle_q.where(Appraisal.id.in_(visible_ids))
    cycle_rows = db.execute(cycle_q).all()

    valid_cycles = [r.days for r in cycle_rows if r.days is not None]
    avg_cycle_days = (
        round(sum(valid_cycles) / len(valid_cycles), 1) if valid_cycles else 0.0
    )

    return {
        "year": year,
        "by_model": by_model,
        "total_meetings": total_meetings,
        "total_articles_in_meetings": total_articles_in_meetings,
        "through_rate": through_rate,
        "signed_total": signed_total,
        "signed_agree": signed_agree,
        "opinion_distribution": opinion_distribution,
        "avg_cycle_days": avg_cycle_days,
        "cycle_samples": len(valid_cycles),
    }


def get_supplies_stats(db: Session, ctx: AuthContext) -> dict:
    """补调统计（#33）。

    - unresolved_list：is_resolved=false + is_overdue（>7天）
    - avg_resolve_hours：TIMESTAMPDIFF 平均
    - by_creator：GROUP BY supplier_id
    """
    # ---- 1. 未解决清单 ----
    unresolved_rows = db.execute(
        select(
            AppraisalSupply.id,
            AppraisalSupply.supply_detail,
            AppraisalSupply.created_at,
            Article.article_num,
            Customer.name.label("customer_name"),
            User.name.label("supplier_name"),
        ).join(
            Article, Article.id == AppraisalSupply.article_id
        ).outerjoin(
            Customer, Customer.id == Article.customer_id
        ).outerjoin(
            User, User.id == AppraisalSupply.supplier_id
        ).where(
            AppraisalSupply.is_resolved.is_(False),
        ).order_by(
            AppraisalSupply.created_at.asc()
        ).limit(200)  # 保护：最多 200 条
    ).all()

    unresolved_list = []
    now = datetime.now()
    for row in unresolved_rows:
        created = row.created_at
        overdue = False
        days_open = 0
        if created:
            delta = now - created
            days_open = delta.days
            overdue = days_open > 7
        unresolved_list.append({
            "supply_id": row.id,
            "article_num": row.article_num,
            "customer_name": row.customer_name,
            "supply_detail": row.supply_detail,
            "supplier_name": row.supplier_name,
            "created_at": str(created) if created else None,
            "days_open": days_open,
            "is_overdue": overdue,
        })

    # ---- 2. 平均解决时长（已解决的） ----
    resolved_rows = db.execute(
        select(
            AppraisalSupply.created_at,
            AppraisalSupply.resolved_at,
        ).where(
            AppraisalSupply.is_resolved.is_(True),
            AppraisalSupply.resolved_at.isnot(None),
            AppraisalSupply.created_at.isnot(None),
        )
    ).all()
    total_hours = 0.0
    for created, resolved in resolved_rows:
        delta = resolved - created
        total_hours += delta.total_seconds() / 3600
    avg_resolve_hours = round(total_hours / len(resolved_rows), 1) if resolved_rows else 0.0

    # ---- 3. 按创建人分布 ----
    creator_rows = db.execute(
        select(
            AppraisalSupply.supplier_id,
            func.count().label("cnt"),
        ).where(
            AppraisalSupply.supplier_id.isnot(None),
        ).group_by(AppraisalSupply.supplier_id)
        .order_by(func.count().desc())
    ).all()
    creator_ids = [sid for sid, _ in creator_rows]
    creator_names: dict[int, str] = {}
    if creator_ids:
        creator_names = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(creator_ids))
            ).all()
        )
    by_creator = [
        {
            "supplier_id": sid,
            "supplier_name": creator_names.get(sid),
            "count": int(cnt),
        }
        for sid, cnt in creator_rows
    ]

    # ---- 4. 汇总计数 ----
    total_supplies = db.execute(
        select(func.count()).select_from(AppraisalSupply)
    ).scalar() or 0
    resolved_count = db.execute(
        select(func.count()).select_from(AppraisalSupply).where(
            AppraisalSupply.is_resolved.is_(True)
        )
    ).scalar() or 0
    unresolved_count = total_supplies - resolved_count
    overdue_count = sum(1 for u in unresolved_list if u["is_overdue"])
    # 注意：unresolved_list 被 limit(200) 限制，overdue_count 仅代表清单内
    # 补一个全量 overdue 计数
    full_overdue = db.execute(
        select(func.count()).select_from(AppraisalSupply).where(
            AppraisalSupply.is_resolved.is_(False),
            AppraisalSupply.created_at < (datetime.now() - timedelta(days=7)),
        )
    ).scalar() or 0

    return {
        "unresolved_list": unresolved_list,
        "unresolved_count": unresolved_count,
        "overdue_count": full_overdue,
        "avg_resolve_hours": avg_resolve_hours,
        "resolved_count": resolved_count,
        "total_supplies": total_supplies,
        "by_creator": by_creator,
    }
