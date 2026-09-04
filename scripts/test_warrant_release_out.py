"""权证解保出库审批 e2e 测试。

流程：submit_release_out_request → 3 次 act(step1/step2/step3) → executor apply_release_out
验证：warrant_state → 310 RELEASED + WarrantStorage 记录 + 拦截直接操作。

运行前确保已执行 scripts/seed.py 造流程定义 + 用户。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.approval.enums import ApproveAction, InstanceStatus
from app.approval.models import ApprovalInstance, ApprovalTask
from app.approval.services import act as approval_act
from app.core.db import SessionLocal
from app.core.exceptions import BizError
from app.user.models import User
from app.warrant.enums import StorageType, WarrantState
from app.warrant.models import Warrant, WarrantStorage
from app.warrant.services import warrant_service
from app.warrant.schemas import StorageCreate

# 注册 executor（必须显式 import，否则末节点抛 5001 整单回滚）
import app.warrant.services.executors  # noqa: F401  register_executor(warrant_release_out)


def main() -> None:
    db = SessionLocal()
    try:
        # 1) 准备：找第一个 warrant，如果状态是 NOT_STORED 先入库（解保需要 STORED/GUARDED）
        warrant = db.scalar(select(Warrant).order_by(Warrant.id))
        if warrant is None:
            print("[FAIL] 无 warrant，请先造数据")
            return

        users = list(db.scalars(select(User).order_by(User.id).limit(4)))
        submitter = users[0]   # 超管（发起审批）
        step1_user = users[1]  # dept_manager
        step2_user = users[2]  # controler
        step3_user = users[0]  # super_admin（与 submitter 同）

        print(f"测试对象: {warrant.warrant_num} (id={warrant.id}, state={warrant.warrant_state})")

        # 2) 确保 warrant_state = STORED（已入库）—— 解保前置条件
        if warrant.warrant_state != WarrantState.STORED.value:
            print(f"  warrant 当前 state={warrant.warrant_state}，先重置为 STORED...")
            # 清理可能已有的 STORE_IN 记录（幂等）
            from sqlalchemy import delete
            db.execute(delete(WarrantStorage).where(WarrantStorage.warrant_id == warrant.id))
            warrant.warrant_state = WarrantState.NOT_STORED.value
            db.flush()
            db.add(
                WarrantStorage(
                    warrant_id=warrant.id, storage_type=StorageType.STORE_IN.value,
                    conservator_id=submitter.id, storage_date="2026-09-01",
                )
            )
            warrant.warrant_state = WarrantState.STORED.value
            db.commit()
            db.refresh(warrant)
            print(f"  state → STORED ({WarrantState.STORED.value})")

        # 3) 清理该 warrant 可能残留的解保审批实例（幂等）
        old_inst_ids = [
            r
            for (r,) in db.execute(
                select(ApprovalInstance.id).where(
                    ApprovalInstance.flow_code == "warrant_release_out",
                    ApprovalInstance.biz_type == "warrant",
                    ApprovalInstance.biz_id == warrant.id,
                )
            )
        ]
        if old_inst_ids:
            db.execute(
                ApprovalTask.__table__.delete().where(ApprovalTask.instance_id.in_(old_inst_ids))
            )
            db.execute(
                ApprovalInstance.__table__.delete().where(ApprovalInstance.id.in_(old_inst_ids))
            )
            db.commit()
            print(f"  清理旧审批实例 {len(old_inst_ids)}")

        print(f"\n============================================================")
        print(f"> Step 1: 拦截直接 add_storage(storage_type=310)")
        print(f"============================================================")
        try:
            body = StorageCreate(storage_type=310, storage_date="2026-09-04")
            warrant_service.add_storage(db, warrant.id, body, submitter.id, None)
            print("[FAIL] 应该被拦截但未被拦截!")
            return
        except BizError as e:
            assert e.code == 4091, f"预期 4091，实际 {e.code}"
            print(f"[OK] 拦截成功: {e.message}")

        print(f"\n============================================================")
        print(f"> Step 2: 发起解保出库审批")
        print(f"============================================================")
        from app.warrant.schemas import ReleaseOutRequestCreate
        from app.core.deps import AuthContext
        body = ReleaseOutRequestCreate(storage_date="2026-09-04", storage_explain="测试解保")
        # AuthContext 构造（submitter 是超管，data_scope=40 ALL 跳过 scope 过滤）
        ctx = AuthContext(
            user_id=submitter.id, username=submitter.username,
            data_scope=40, is_super_admin=True,
            role_codes=set(), permission_codes=set(),
            dept_scope_ids=None,
        )
        inst_id = warrant_service.submit_release_out_request(db, warrant.id, body, submitter.id, ctx)
        print(f"  instance_id = {inst_id}")

        # 校验状态不变
        inst = db.get(ApprovalInstance, inst_id)
        print(f"  instance.status = {inst.status} (预期 10 PENDING)")
        print(f"  warrant.warrant_state = {warrant.warrant_state} (预期 {WarrantState.STORED.value})")
        assert inst.status == InstanceStatus.PENDING
        assert warrant.warrant_state == WarrantState.STORED.value

        print(f"[OK] 审批已发起，warrant_state 不变")

        print(f"\n============================================================")
        print(f"> Step 3: step1 通过")
        print(f"============================================================")
        task1 = db.scalar(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == inst_id,
                ApprovalTask.step == 1, ApprovalTask.status == 10,
            )
        )
        print(f"  task1.approver_id = {task1.approver_id} (step1_user={step1_user.id})")
        approval_act(db, task1.id, ApproveAction.APPROVE.value, None, task1.approver_id)
        db.commit()
        inst = db.get(ApprovalInstance, inst_id)
        print(f"  instance.current_step = {inst.current_step} (预期 2)")
        print(f"  warrant_state 仍 = {warrant.warrant_state}")
        assert inst.current_step == 2

        print(f"\n============================================================")
        print(f"> Step 4: step2 通过")
        print(f"============================================================")
        task2 = db.scalar(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == inst_id,
                ApprovalTask.step == 2, ApprovalTask.status == 10,
            )
        )
        print(f"  task2.approver_id = {task2.approver_id}")
        approval_act(db, task2.id, ApproveAction.APPROVE.value, None, task2.approver_id)
        db.commit()
        inst = db.get(ApprovalInstance, inst_id)
        print(f"  instance.current_step = {inst.current_step} (预期 3)")
        assert inst.current_step == 3

        print(f"\n============================================================")
        print(f"> Step 5: step3 通过 → executor 执行解保")
        print(f"============================================================")
        task3 = db.scalar(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == inst_id,
                ApprovalTask.step == 3, ApprovalTask.status == 10,
            )
        )
        print(f"  task3.approver_id = {task3.approver_id}")
        approval_act(db, task3.id, ApproveAction.APPROVE.value, None, task3.approver_id)
        db.commit()

        # 校验：executor 已生效
        db.refresh(warrant)
        inst = db.get(ApprovalInstance, inst_id)
        print(f"  instance.status = {inst.status} (预期 20 APPROVED)")
        print(f"  warrant.warrant_state = {warrant.warrant_state} (预期 310 RELEASED)")

        latest = db.scalar(
            select(WarrantStorage).where(
                WarrantStorage.warrant_id == warrant.id,
                WarrantStorage.storage_type == StorageType.RELEASE_OUT.value,
            ).order_by(WarrantStorage.id.desc())
        )
        print(f"  WarrantStorage(RELEASE_OUT) 记录: id={latest.id if latest else None}")
        if latest:
            print(f"    storage_explain = {latest.storage_explain}")
            print(f"    storage_date = {latest.storage_date}")

        assert inst.status == InstanceStatus.APPROVED
        assert warrant.warrant_state == WarrantState.RELEASED.value, \
            f"warrant_state 应该是 310 RELEASED，实际 {warrant.warrant_state}"
        assert latest is not None, "应该写出 WarrantStorage RELEASE_OUT 记录"
        assert latest.storage_explain == "测试解保"

        print(f"\n=== ALL PASSED: warrant_release_out submit → 3 act → executor.apply_release_out 完整链路 OK ===")

    except Exception as exc:
        print(f"\n[FAIL] 异常: {exc}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
