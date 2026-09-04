"""端到端 seed：项目 + 子资源 + 审批实例（幂等）。

运行前确保已执行过 scripts/seed.py（创建流程定义、用户、产品、客户）。
幂等：重复执行时会先清理旧的 article 审批实例、子资源、评审数据。

数据覆盖的 3 个场景：
  AR2026-001 已上会 REVIEW_DONE  → 无审批实例（可从前端发起签批）
  AR2026-002 已签批 SIGNED       → 审批 Timeline 已通过
  AR2026-003 已取消 CANCELLED    → 审批 Timeline 已驳回
"""
import os
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete

from app.article.models import (
    Article, ArticleSingleQuota, ArticleLendingOrder,
)
from app.article.enums import ArticleState
from app.approval.models import ApprovalFlowDef, ApprovalFlowNode, ApprovalInstance, ApprovalTask
from app.appraisal.models import AppraisalComment, AppraisalSupply, ReviewExpert, ExpertCategory
from app.core.db import SessionLocal
from app.customer.models import Customer
from app.user.models import User


def cleanup_children(db):
    """清理与 article 关联的所有子资源（幂等）。"""
    from app.approval.models import ApprovalInstance, ApprovalTask
    # 审批任务 + 实例
    inst_ids = [r for (r,) in db.execute(
        select(ApprovalInstance.id).where(ApprovalInstance.biz_type == "article")
    )]
    if inst_ids:
        db.execute(delete(ApprovalTask).where(ApprovalTask.instance_id.in_(inst_ids)))
        db.execute(delete(ApprovalInstance).where(ApprovalInstance.id.in_(inst_ids)))
    # 子资源
    db.execute(delete(ArticleSingleQuota))
    db.execute(delete(ArticleLendingOrder))
    db.execute(delete(AppraisalComment))
    db.execute(delete(AppraisalSupply))
    print(f"  清理完成：审批实例 {len(inst_ids)} / 配额 / 放款 / 评审 / 补调")


def ensure_article_state(db):
    """确保 3 个 article 存在且 article_state 到正确阶段。"""
    articles = list(db.scalars(select(Article).order_by(Article.id).limit(3)))
    if len(articles) < 3:
        print(f"[skip] 只有 {len(articles)} 个项目，请先跑 seed.py 造客户/产品/用户")
        return None

    # 场景映射（article 按 id 顺序）
    scenarios = [
        {"article_state": ArticleState.REVIEW_DONE.value,  "label": "已上会(可发起签批)", "has_approval": False},
        {"article_state": ArticleState.SIGNED.value,        "label": "已签批(审批通过)",   "has_approval": True},
        {"article_state": ArticleState.CANCELLED.value,     "label": "已取消(审批驳回)",   "has_approval": True},
    ]
    for art, sc in zip(articles, scenarios):
        art.article_state = sc["article_state"]
        print(f"  {art.article_num} → {sc['label']}")
    db.commit()
    return articles


def ensure_quotas_and_orders(db, articles):
    """为每个 article 造配额 + 放款（金额 = renewal + augment，让金额三方校验通过）。"""
    for art in articles:
        total = art.renewal + art.augment  # 例如 1000 + 500 = 1500
        # 单项额度（1 条足够通过校验；credit_model 取 1=流动资金）
        db.add(ArticleSingleQuota(
            article_id=art.id, credit_model=1, credit_amount=total,
            flow_rate="年化 5.6%", remark="综合授信额度",
        ))
        # 放款次序（2 笔，合计 = total）
        half = (total / Decimal("2")).quantize(Decimal("0.01"))
        for seq, amt in [(1, half), (2, total - half)]:
            db.add(ArticleLendingOrder(
                article_id=art.id, seq=seq, order_amount=amt,
                remark=f"第 {seq} 笔拟放",
            ))
    db.commit()
    print(f"  配额 + 放款 OK（合计 {articles[0].renewal + articles[0].augment} / article）")


def ensure_experts_and_categories(db):
    """确保评审专家 + 专家类别存在（幂等：名字匹配即复用）。"""
    cat = db.scalar(select(ExpertCategory).where(ExpertCategory.name == "通用评委"))
    if cat is None:
        cat = ExpertCategory(name="通用评委", sort=1, status=1)
        db.add(cat); db.flush()

    expert_names = ["张评审", "李风控", "王业务"]
    experts = []
    for name in expert_names:
        e = db.scalar(select(ReviewExpert).where(ReviewExpert.name == name))
        if e is None:
            e = ReviewExpert(
                name=name, title="高级评审", org_name="外部评审机构",
                expert_type=20, category_id=cat.id, status=1, sort=1,
            )
            db.add(e); db.flush()
        experts.append(e)
    db.commit()
    return experts


def ensure_comments_and_supplies(db, articles, experts, supplyor_id):
    """为每个 article 造评审意见 + 补调记录。"""
    for art in articles:
        # 每条专家一个评审意见（AppraisalComment 无 score 字段，前端 service 层自定义）
        for idx, exp in enumerate(experts):
            db.add(AppraisalComment(
                article_id=art.id, expert_id=exp.id,
                comment_type=10 if idx == 0 else 20,
                concrete=f"项目{art.article_num}整体质量较好，建议重点关注{'风控指标' if idx == 0 else '还款来源'}。",
            ))
        # 2 条补调记录（1 已解决 + 1 待解决，最后一条 article 全部已解决）
        is_art3 = (art.article_num == "AR2026-003")
        db.add(AppraisalSupply(
            article_id=art.id, supply_detail=f"请补充{art.article_num}抵押物评估报告原件",
            is_resolved=True, resolve_reply="已上传扫描件",
            supplyor_id=supplyor_id,
        ))
        db.add(AppraisalSupply(
            article_id=art.id,
            supply_detail=f"请核实{art.article_num}保证人征信最新报告",
            is_resolved=is_art3,
            resolve_reply="征信已更新" if is_art3 else None,
            supplyor_id=supplyor_id,
        ))
    db.commit()
    print(f"  评审意见 {len(articles) * len(experts)} / 补调记录 {len(articles) * 2}")


def ensure_approvals(db, articles, users):
    """造审批实例（仅给已通过/已驳回的两条造）。"""
    flow = db.scalar(select(ApprovalFlowDef).where(ApprovalFlowDef.code == "article_sign"))
    nodes = list(db.scalars(
        select(ApprovalFlowNode).where(ApprovalFlowNode.flow_def_id == flow.id)
        .order_by(ApprovalFlowNode.step)
    ))
    if not nodes:
        print("[skip] article_sign 流程无节点")
        return

    # 角色用户映射（seed.py 默认造 3 个用户，第 2 个是部门负责人、第 3 个风控、第 1 个超管）
    role_user = {"dept_manager": users[1], "controler": users[2], "super_admin": users[0]}
    opinions = ["信息齐全，同意", "风控意见良好，同意", "总经理最终审批通过"]
    reject_opinion = "授信额超出权限范围，请重新评估"

    scenarios = [
        {"label": "已上会(无实例)", "create": False},
        {"label": "已签批(已通过)", "create": True, "status": 20, "node_statuses": [20, 20, 20]},
        {"label": "已取消(已驳回)", "create": True, "status": 30, "node_statuses": [20, 20, 30]},
    ]

    now = datetime.now()
    created = 0
    for art, sc in zip(articles, scenarios):
        if not sc["create"]:
            continue
        inst = ApprovalInstance(
            flow_code=flow.code, biz_type="article", biz_id=art.id,
            payload={
                "renewal": float(art.renewal), "augment": float(art.augment),
                "credit_amount": float(art.renewal + art.augment),
                "sign_type": 1, "rcd_opinion": None, "convenor_opinion": None,
                "sign_detail": f"项目 {art.article_num} 完整签批流程演示",
                "sign_date": str(now.date()),
            },
            summary=f"项目 {art.article_num} 签批申请",
            status=sc["status"],
            current_step=len(nodes) if sc["status"] == 20 else len(nodes) + 1,
            submitted_by=users[0].id,
            submitted_at=now - timedelta(hours=6),
        )
        db.add(inst); db.flush()
        created += 1

        for step_idx, node in enumerate(nodes):
            ns = sc["node_statuses"][step_idx]
            approver = role_user.get(node.approver_role_code, users[0])
            acted_at = now - timedelta(hours=5 - step_idx)
            opinion = opinions[step_idx] if ns == 20 else (reject_opinion if ns == 30 else None)

            db.add(ApprovalTask(
                instance_id=inst.id, step=node.step, node_name=node.name,
                approver_id=approver.id, status=ns, opinion=opinion,
                acted_at=acted_at if ns != 10 else None,
            ))
        print(f"  {art.article_num} → [{sc['label']}] inst#{inst.id}")

    db.commit()
    print(f"  审批实例 {created} / 任务 {created * len(nodes)}")


def main() -> None:
    db = SessionLocal()
    try:
        users = list(db.scalars(select(User).order_by(User.id).limit(3)))
        if len(users) < 3:
            print("[skip] 用户不足 3 人")
            return

        # 1) 清理旧数据
        cleanup_children(db)

        # 2) 确保 article 状态到正确阶段
        articles = ensure_article_state(db)
        if articles is None:
            return

        # 3) 配额 + 放款（金额三方校验通过）
        ensure_quotas_and_orders(db, articles)

        # 4) 评审专家 + 评审意见 + 补调记录
        experts = ensure_experts_and_categories(db)
        ensure_comments_and_supplies(db, articles, experts, supplyor_id=users[2].id)

        # 5) 审批实例（仅给已通过/已驳回造）
        ensure_approvals(db, articles, users)

        print("\nseed 完成：3 个项目 x 完整子资源 + 审批 Timeline 演示")
        print("   其中 AR2026-001 article_state=40 无审批实例，可前端点『发起签批』")

    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
