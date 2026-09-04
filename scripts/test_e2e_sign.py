"""端到端测试：发起签批 → 逐步审批 → article_state 自动联动。

审批引擎的 submit() 是"懒创建"——只造首节点任务，act() 推进时才造下一个节点。
关键：每个 step 的 approver_id 由角色解析，需要用真实的 approver_id 来 act。
"""
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.article.enums import ArticleState
from app.article.models import Article
from app.article.schemas import SignRequestCreate
from app.article.services.article_service import submit_sign_request
import app.article.services.executors  # noqa: F401  注册 executor（register_executor）
from app.approval.services import act
from app.approval.services.engine_service import ApproveAction
from app.approval.models import ApprovalTask
from app.core.db import SessionLocal
from app.user.models import User


def log_step(msg: str):
    print(f"\n{'='*60}")
    print(f"> {msg}")
    print(f"{'='*60}")


def check_article(db: Session, article_id: int, expect_state: int, label: str):
    art = db.get(Article, article_id)
    assert art is not None
    ok = art.article_state == expect_state
    tag = "OK" if ok else "FAIL"
    try:
        state_name = ArticleState(art.article_state).name
    except ValueError:
        state_name = f"unknown({art.article_state})"
    print(f"  [{tag}] {label}: article_state={art.article_state} ({state_name})")
    return ok


def main():
    db = SessionLocal()
    try:
        articles = list(db.scalars(select(Article).order_by(Article.id).limit(1)))
        assert articles
        art = articles[0]
        print(f"测试对象: {art.article_num} (id={art.id}, state={art.article_state})")

        submitter = list(db.scalars(select(User).order_by(User.id).limit(1)))[0]

        # ========== Step 1：发起签批 ==========
        log_step("Step 1: 发起签批")
        body = SignRequestCreate(
            sign_type=1, renewal=art.renewal, augment=art.augment,
            credit_amount=art.renewal + art.augment, g_value=Decimal("0"),
            sign_detail="E2E 测试签批", sign_date=date.today(),
        )
        inst_id = submit_sign_request(db, art.id, body, submitter.id)
        print(f"  审批实例 id={inst_id}")
        check_article(db, art.id, ArticleState.REVIEW_DONE.value, "发起签批后 state 仍为 40")

        # ========== 逐步审批（每步用真实 approver_id） ==========
        all_ok = True
        for step_num in [1, 2, 3]:
            log_step(f"Step {step_num+1}: step{step_num} 审批人 通过")
            tasks = list(db.scalars(
                select(ApprovalTask).where(ApprovalTask.instance_id == inst_id, ApprovalTask.step == step_num)
            ))
            if not tasks:
                print(f"  [SKIP] step{step_num} 无任务")
                break
            t = tasks[0]
            print(f"  task#{t.id} node={t.node_name} approver_id={t.approver_id}")
            act(db, t.id, action=ApproveAction.APPROVE.value,
                opinion=f"step{step_num} 通过", operator_id=t.approver_id)
            db.commit()
            db.expire_all()

            # 只有末节点通过后 article_state 才变
            expect = ArticleState.SIGNED.value if step_num == 3 else ArticleState.REVIEW_DONE.value
            ok = check_article(db, art.id, expect,
                               f"step{step_num} 通过 -> state={expect}")
            all_ok = all_ok and ok

        # ========== 最终校验 ==========
        log_step("最终数据校验")
        art_final = db.get(Article, art.id)
        print(f"  article_state = {art_final.article_state} ({ArticleState(art_final.article_state).name})")
        print(f"  sign_type = {art_final.sign_type}")
        print(f"  sign_detail = {art_final.sign_detail}")
        print(f"  renewal = {art_final.renewal}, augment = {art_final.augment}")

        if all_ok and art_final.sign_type == 1 and art_final.sign_detail == "E2E 测试签批":
            print("\n=== ALL PASSED: submit_sign_request -> act x3 -> executor.apply_sign 完整链路 OK ===")
        else:
            print(f"\n=== FAIL: all_ok={all_ok} sign_type={art_final.sign_type} sign_detail={art_final.sign_detail!r} ===")

    except Exception as e:
        print(f"\n[FAIL] 异常: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
