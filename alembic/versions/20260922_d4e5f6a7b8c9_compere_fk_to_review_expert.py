"""Appraisal.compere_id FK: users.id → appraisal_review_experts.id

主持人从系统用户改为评审委员（ReviewExpert）。
迁移策略：
1. 先按 User.name = ReviewExpert.name 尝试 name 匹配（同名人取 id 最小）
2. 匹配不到的 compere_id 置 NULL（user.id 与 review_expert.id 是独立自增序列，
   不能直接沿用旧值，否则 FK 会约束失败）
3. 删旧 FK → 加新 FK（ondelete RESTRICT，与 ReviewExpert 保持一致）

此迁移只涉及 appraisals.compere_id 一列的 FK 目标切换，业务数据量小。
"""

from alembic import op
import sqlalchemy as sa

revision = "20260922_compere_fk"
down_revision = "20260922_comment_rename"
branch_labels = None
depends_on = None


def _get_fk_name(op_obj, table, column):
    """按 introspect 动态找 FK 名（兼容 MySQL / PostgreSQL）。"""
    conn = op_obj.get_bind()
    inspector = sa.inspect(conn)
    for fk in inspector.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []):
            return fk["name"]
    return None


def upgrade():
    # ---- 数据迁移：按姓名匹配 ReviewExpert，匹配不到置 NULL ----
    conn = op.get_bind()

    # 拉取所有 user_id → name（旧 compere_id 指向 users.id）
    users = conn.execute(sa.text("SELECT id, name FROM users WHERE id IS NOT NULL")).fetchall()
    user_map = {row[0]: row[1] for row in users}  # user_id → name

    # 拉取所有 review_expert id → name
    experts = conn.execute(
        sa.text("SELECT id, name FROM appraisal_review_experts WHERE id IS NOT NULL")
    ).fetchall()
    # 同名人取最小 id
    name_to_expert_id: dict[str, int] = {}
    for eid, ename in experts:
        if ename and ename not in name_to_expert_id:
            name_to_expert_id[ename] = eid

    # 遍历 appraisals，更新 compere_id
    appraisals = conn.execute(
        sa.text("SELECT id, compere_id FROM appraisals WHERE compere_id IS NOT NULL")
    ).fetchall()

    updated = 0
    nulled = 0
    for aid, old_cid in appraisals:
        expert_name = user_map.get(old_cid)
        new_cid = name_to_expert_id.get(expert_name) if expert_name else None
        if new_cid is not None:
            conn.execute(
                sa.text("UPDATE appraisals SET compere_id = :cid WHERE id = :aid"),
                {"cid": new_cid, "aid": aid},
            )
            updated += 1
        else:
            conn.execute(
                sa.text("UPDATE appraisals SET compere_id = NULL WHERE id = :aid"),
                {"aid": aid},
            )
            nulled += 1

    conn.commit()
    print(f"\n迁移摘要：{updated} 行按姓名匹配成功，{nulled} 行置 NULL（请在前端重新分配主持人）\n")

    # ---- 删旧 FK ----
    old_fk = _get_fk_name(op, "appraisals", "compere_id")
    if old_fk:
        op.drop_constraint(old_fk, "appraisals", type_="foreignkey")

    # ---- 加新 FK ----
    op.create_foreign_key(
        None,
        "appraisals",
        "appraisal_review_experts",
        ["compere_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    # ---- 删新 FK ----
    new_fk = _get_fk_name(op, "appraisals", "compere_id")
    if new_fk:
        op.drop_constraint(new_fk, "appraisals", type_="foreignkey")

    # ---- 数据回退：按 ReviewExpert.name = User.name 匹配 ----
    conn = op.get_bind()
    experts = conn.execute(
        sa.text("SELECT id, name FROM appraisal_review_experts WHERE compere_id IS NOT NULL OR id IS NOT NULL")
    ).fetchall()
    name_to_expert_id = {}
    for eid, ename in experts:
        if ename and ename not in name_to_expert_id:
            name_to_expert_id[ename] = eid

    # 反向：expert name → user id
    users = conn.execute(sa.text("SELECT id, name FROM users WHERE id IS NOT NULL")).fetchall()
    name_to_user_id = {}
    for uid, uname in users:
        if uname and uname not in name_to_user_id:
            name_to_user_id[uname] = uid

    appraisals = conn.execute(
        sa.text("SELECT id, compere_id FROM appraisals WHERE compere_id IS NOT NULL")
    ).fetchall()
    for aid, old_cid in appraisals:
        expert_row = conn.execute(
            sa.text("SELECT name FROM appraisal_review_experts WHERE id = :id"),
            {"id": old_cid},
        ).fetchone()
        if expert_row:
            user_id = name_to_user_id.get(expert_row[0])
            if user_id:
                conn.execute(
                    sa.text("UPDATE appraisals SET compere_id = :cid WHERE id = :aid"),
                    {"cid": user_id, "aid": aid},
                )

    conn.commit()

    # ---- 加回旧 FK ----
    op.create_foreign_key(
        None,
        "appraisals",
        "users",
        ["compere_id"],
        ["id"],
        ondelete="RESTRICT",
    )
