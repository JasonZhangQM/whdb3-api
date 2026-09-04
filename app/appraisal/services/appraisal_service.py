"""评审主 Service（§3.7 标准模式）。

P5 合并：评审会 + 补调 + 意见 → 一个 appraisal_service.py。
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appraisal.enums import LABELS as APPRAISAL_LABELS, MeetingState
from app.appraisal.models import (
    Appraisal,
    AppraisalArticle,
    AppraisalComment,
    AppraisalSupply,
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
from app.article.models import Article
from app.core.exceptions import BizError
from app.user.models import User


# ============ 顶部标配 ============

def _get_or_404(db: Session, appraisal_id: int) -> Appraisal:
    a = db.get(Appraisal, appraisal_id)
    if a is None:
        raise BizError(4041, "评审会不存在")
    return a


def _disp(label: dict[int, str] | None, value) -> str | None:
    """从 LABELS 字典取中文，value 为 None 返回 None。"""
    if label is None or value is None:
        return None
    return label.get(value)


# ============ 评审会 ============

def list_appraisals(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    year: int | None = None,
    review_model: int | None = None,
    meeting_state: int | None = None,
) -> tuple[list[dict], int]:
    """评审会列表。

    §3.7.3 N+1 消除：
    - 批量取 compere 用户名称 → dict → 循环取值
    - 子查询 count articles_count（参评项目数）
    """
    stmt = select(Appraisal).order_by(Appraisal.created_at.desc())
    if year is not None:
        stmt = stmt.where(Appraisal.year == year)
    if review_model is not None:
        stmt = stmt.where(Appraisal.review_model == review_model)
    if meeting_state is not None:
        stmt = stmt.where(Appraisal.meeting_state == meeting_state)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.offset((page - 1) * page_size).limit(page_size)
    ).all()

    if not items:
        return [], total

    # §3.7.3 N+1 消除：批量取 compere 名称
    compere_ids = {a.compere_id for a in items if a.compere_id}
    users = {}
    if compere_ids:
        users = dict(
            db.execute(
                select(User.id, User.name).where(User.id.in_(compere_ids))
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

    # 子查询 count：每个 appraisal 的参会评委数（后续可加）
    # ...

    result = []
    for a in items:
        result.append({
            "id": a.id,
            "num": a.num,
            "year": a.year,
            "seq": a.seq,
            "review_model": a.review_model,
            "review_date": str(a.review_date) if a.review_date else None,
            "meeting_state": a.meeting_state,
            "meeting_state_display": _disp(APPRAISAL_LABELS.get("meeting_state"), a.meeting_state),
            "compere_id": a.compere_id,
            "compere_name": users.get(a.compere_id),
            "articles_count": article_counts.get(a.id, 0),
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
        article.review_date = finish_date
        # 纪要编号：JY{year}{seq}，同项目多次上会追加序号
        if article.summary_num is None:
            article.summary_num = f"JY{appraisal.year}{appraisal.seq:02d}"

    db.commit()


def delete_appraisal(db: Session, appraisal_id: int, user_id: int) -> None:
    """删除评审会（仅未完成的可删）。"""
    appraisal = _get_or_404(db, appraisal_id)
    if appraisal.meeting_state == MeetingState.FINISHED.value:
        raise BizError(4031, "已完成的评审会不能删除")
    # 清理关联的 AppraisalArticle
    db.query(AppraisalArticle).where(AppraisalArticle.appraisal_id == appraisal_id).delete()
    db.delete(appraisal)
    db.commit()


# ============ 评委意见 ============

def batch_upsert_comments(
    db: Session, article_id: int, body: CommentBatchCreate, user_id: int
) -> int:
    """批量录入评委意见（upsert）。Article 已上移到顶部 import。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (30, 40, 61):
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

        comment.comment_type = item.comment_type
        comment.concrete = item.concrete
        count += 1

    db.commit()
    return count


# ============ 补调问题 ============

def add_supply(
    db: Session, article_id: int, body: SupplyCreate, user_id: int
) -> None:
    """添加补调问题（状态门槛 10/20/30/40/61）。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (10, 20, 30, 40, 61):
        raise BizError(4031, "当前状态不允许添加补调")

    db.add(AppraisalSupply(
        article_id=article_id,
        supply_detail=body.supply_detail,
        supplyor_id=user_id,
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
    db.commit()


def update_summary(
    db: Session, article_id: int, body: SummaryUpdate, user_id: int
) -> None:
    """纪要编辑（项目状态 40/61）。Article 已上移到顶部 import。"""
    article = db.get(Article, article_id)
    if article is None:
        raise BizError(4041, "项目不存在")
    if article.article_state not in (40, 61):
        raise BizError(4031, "已上会后可编辑纪要")

    if body.summary is not None:
        article.summary = body.summary
    if body.opinion is not None:
        article.opinion = body.opinion

    db.commit()
