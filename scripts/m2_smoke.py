"""M2 验收冒烟：机构 / 客户（审批三场景）/ 权证 / 审批引擎 / 附件 / data_scope 隔离。

用法：python scripts/m2_smoke.py（服务需在 127.0.0.1:8100 运行，seed 已执行）
可重复执行：区域/行业走 ORM 幂等插入；客户/权证按名称查回复用；临时申请走撤回/驳回终结。

场景总览：
  1. 准备：基础数据（ORM）+ 测试部门/角色/用户（admin）
  2. 机构：CRUD + 协议 + 统计 + 参数校验
  3. 客户创建审批：提交 → 互斥 4091 → 部门负责人审批 → 落库；驳回不落库
  4. 敏感字段变更审批（diff 应用）+ 自由字段直改
  5. 客户子资源：快照/分类/股东/董事/核心额度/集团/授信区域/标签/统计
  6. 权证：房产 1:N 创建 + 评估复核 + 出入库状态联动 + 批量移交 + 票据明细
  7. data_scope：pm 本人隔离 vs 部门角色可见本部门
  8. 附件：上传/列表/下载/删除
"""

import sys
import time
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8100/api/v1"
ADMIN_PWD = "Admin@whdb3"

# 固定测试数据（幂等复用）
DEPT_NAME = "测试二部"
C1_NAME, C1_SHORT = "冒烟制造有限公司", "冒烟制造"       # 企业客户（集团母公司）
C3_NAME, C3_SHORT = "冒烟核心企业有限公司", "冒烟核心"    # is_core
C4_NAME, C4_SHORT = "冒烟承兑人有限公司", "冒烟承兑"      # is_acceptor
GROUP_CODE, REGION_CODE = "SMOKE-G01", "SMOKE-CR01"
W1_NUM, WD_NUM, DRAFT_NUM = "SMOKE-W-0001", "SMOKE-WD-0001", "SMOKE-DRAFT-0001"

passed, failed = [], []


def check(name: str, cond: bool, detail: str = ""):
    (passed if cond else failed).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail and not cond else ''}")


def login(client: httpx.Client, account: str, password: str):
    r = client.post(f"{BASE}/auth/login", json={"account": account, "password": password})
    body = r.json()
    return body["data"] if body["code"] == 0 else None


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api(client: httpx.Client, method: str, path: str, token: str, **kw):
    """统一请求并解包 R 响应体，返回 (code, data)。"""
    r = client.request(method, f"{BASE}{path}", headers=bearer(token), **kw)
    body = r.json()
    return body.get("code", -1), body.get("data")


def approve_current(client: httpx.Client, dm_token: str, instance_id: int,
                    action: int = 10, opinion: str = ""):
    """用部门负责人身份处理指定实例的当前任务（同意=10 / 驳回=20）。"""
    code, items = api(client, "GET", "/approvals/my-tasks?page_size=100", dm_token)
    for it in items["items"] if code == 0 else []:
        if it["id"] == instance_id:
            return api(client, "POST", f"/approvals/tasks/{it['current_task_id']}/act",
                       dm_token, json={"action": action, "opinion": opinion})
    return 4041, None


# ---------- 基础数据（ORM 幂等）：行政区域 + 行业 ----------

def prepare_base_data() -> dict:
    """区域/行业无管理接口，ORM 直插测试数据（幂等），返回 id 映射。"""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.customer.models import Industry
    from app.user.models import Region

    ids: dict[str, int] = {}
    with SessionLocal() as db, db.begin():
        def upsert_region(code: str, name: str, level: int, parent_id: int) -> int:
            r = db.scalar(select(Region).where(Region.code == code))
            if r is None:
                r = Region(code=code, name=name, level=level, parent_id=parent_id)
                db.add(r)
                db.flush()
            return r.id

        province = upsert_region("330000", "浙江省", 10, 0)
        city = upsert_region("330100", "杭州市", 20, province)
        district = upsert_region("330105", "拱墅区", 30, city)
        ids["region_id"] = district

        def upsert_industry(code: str, name: str, ind_typ: int, parent_id: int) -> int:
            i = db.scalar(select(Industry).where(Industry.code == code))
            if i is None:
                i = Industry(code=code, name=name, ind_typ=ind_typ, parent_id=parent_id)
                db.add(i)
                db.flush()
            return i.id

        cat = upsert_industry("B", "制造业", 20, 0)
        ids["industry_id"] = upsert_industry("36", "汽车制造业", 20, cat)
    return ids


def main() -> None:
    base = prepare_base_data()
    client = httpx.Client(timeout=30)

    # ========== 1. 准备：admin 登录 + 部门/角色/用户 ==========
    me = login(client, "admin", ADMIN_PWD)
    check("管理员登录", me is not None)
    token = me["tokens"]["access_token"]

    code, data = api(client, "GET", "/departments/tree", token)
    dept_id = next((n["id"] for n in data if n["name"] == DEPT_NAME), None)
    if dept_id is None:
        code, data = api(client, "POST", "/departments", token,
                         json={"parent_id": 0, "name": DEPT_NAME, "ordery": 880})
        check("创建测试部门", code == 0, str(data)[:120])
        dept_id = data["id"]
    else:
        check("测试部门（幂等复用）", True)

    code, data = api(client, "GET", "/permissions", token)
    perm_ids = {p["code"]: p["id"] for p in data}
    # m2_pm=本人(data_scope=10) 挂 M2 全业务权限；m2_dept=本部门(30) 挂只读权限
    pm_perms = [perm_ids[c] for c in (
        "customer:list", "customer:create", "customer:update", "customer:detail",
        "customer:delete", "customer:transfer", "warrant:list", "warrant:create",
        "warrant:update", "warrant:detail", "warrant:storage", "warrant:delete",
    )]
    dept_perms = [perm_ids[c] for c in ("customer:list", "customer:detail",
                                        "warrant:list", "warrant:detail")]

    def ensure_role(code_: str, name: str, scope: int, perms: list[int]) -> int:
        r, d = api(client, "POST", "/roles", token,
                   json={"code": code_, "name": name, "data_scope": scope})
        if r == 0:
            return d["id"]
        _, roles = api(client, "GET", "/roles", token)
        return next(x["id"] for x in roles if x["code"] == code_)

    role_pm = ensure_role("m2_pm", "M2冒烟项目经理", 10, pm_perms)
    role_dept = ensure_role("m2_dept", "M2冒烟部门查看", 30, dept_perms)
    check("测试角色创建（幂等）", True)
    check("m2_pm 分配 M2 权限",
          api(client, "PUT", f"/roles/{role_pm}/permissions", token,
              json={"permission_ids": pm_perms})[0] == 0)
    check("m2_dept 分配只读权限",
          api(client, "PUT", f"/roles/{role_dept}/permissions", token,
              json={"permission_ids": dept_perms})[0] == 0)

    def ensure_user(username: str, name: str, role_ids: list[int], dept: int) -> tuple[int, str]:
        r, d = api(client, "POST", "/users", token, json={
            "username": username, "name": name, "email": f"{username}@whdb-test.com",
            "dept_id": dept, "role_ids": role_ids,
        })
        if r == 0:
            return d["id"], d["initial_password"]
        # 已存在：重置密码 + 归位部门（审批人按提交人部门解析）+ 重置角色（幂等）
        _, users = api(client, "GET", f"/users?q={username}", token)
        uid = next(u["id"] for u in users["items"] if u["username"] == username)
        _, d2 = api(client, "POST", f"/users/{uid}/password", token, json={})
        api(client, "PATCH", f"/users/{uid}", token,
            json={"name": name, "dept_id": dept})
        api(client, "PUT", f"/users/{uid}/roles", token, json={"role_ids": role_ids})
        return uid, d2["initial_password"]

    # testpm=提交人(m2_pm)；testdm=审批人(dept_manager + m2_dept 多角色权限并集)
    _, roles = api(client, "GET", "/roles", token)
    role_map = {x["code"]: x["id"] for x in roles}
    pm_id, pm_pwd = ensure_user("testpm", "M2测试项目经理", [role_pm], dept_id)
    dm_id, dm_pwd = ensure_user("testdm", "M2测试部门负责人",
                                [role_map["dept_manager"], role_dept], dept_id)
    check("测试用户创建（testpm/testdm，幂等）", pm_id > 0 and dm_id > 0)

    pm = login(client, "testpm", pm_pwd)
    dm = login(client, "testdm", dm_pwd)
    check("testpm/testdm 登录", pm is not None and dm is not None)
    pm_token, dm_token = pm["tokens"]["access_token"], dm["tokens"]["access_token"]

    # ========== 2. 机构模块 ==========
    print("\n-- 机构模块 --")
    code, data = api(client, "GET", "/dicts/institution-types", token)
    check("机构类型字典", code == 0 and {"value": 10, "label": "银行"} in data["institution_type"])

    code, data = api(client, "POST", "/institutions", token, json={
        "name": "冒烟测试银行", "short_name": "冒烟银行", "institution_type": 10,
        "institution_subtype": 30, "legal_representative": "张三",
        "contacts": [{"name": "李四", "phone": "0571-88000000", "is_primary": True}],
    })
    if code != 0:  # 幂等：按名称查回
        _, lst = api(client, "GET", "/institutions?q=冒烟银行", token)
        inst_id = lst["items"][0]["id"]
    else:
        inst_id = data["id"]
    check("创建银行机构（含联系人）", inst_id > 0)

    code, _ = api(client, "POST", "/institutions", token, json={
        "name": "无子类银行", "short_name": "无子类", "institution_type": 10})
    check("银行类缺子类型被拒（4001）", code == 4001)

    _, detail = api(client, "GET", f"/institutions/{inst_id}", token)
    if not any(b["name"] == "冒烟银行拱墅支行" for b in detail["branches"]):
        code, _ = api(client, "POST", f"/institutions/{inst_id}/branches", token, json={
            "name": "冒烟银行拱墅支行", "short_name": "拱墅支行", "branch_addr": "测试路1号"})
        check("添加分支机构", code == 0)
    else:
        check("分支机构（幂等复用）", True)

    code, _ = api(client, "POST", f"/institutions/{inst_id}/agreements", token, json={
        "agreement_type": 10, "flow_credit": 50000000, "back_credit": 10000000,
        "valid_begin_date": "2026-01-01", "valid_end_date": "2028-12-31"})
    check("添加授信协议", code == 0)

    code, data = api(client, "GET", f"/institutions/{inst_id}", token)
    check("机构详情聚合（联系人/分支/协议）",
          code == 0 and len(data["contacts"]) >= 1
          and len(data["branches"]) >= 1 and len(data["agreements"]) >= 1)
    check("机构详情协议额度透出",
          any(a["flow_credit"] == 50000000 for a in data["agreements"]))

    code, data = api(client, "GET", "/institutions/stats/overview", token)
    check("机构统计概览", code == 0 and data["total_count"] >= 1
          and data["active_agreement_count"] >= 1)
    code, data = api(client, "GET", "/institutions/stats/balance-summary", token)
    check("机构余额汇总", code == 0 and any(i["institution_id"] == inst_id for i in data))
    code, data = api(client, "GET", "/institutions?institution_type=10", token)
    check("机构列表筛选（银行类）", code == 0 and any(i["id"] == inst_id for i in data["items"]))

    # ========== 3. 客户创建审批流 ==========
    print("\n-- 客户创建审批（customer_create）--")

    def customer_payload(name: str, short: str, genre: int, **extra) -> dict:
        p = {
            "name": name, "short_name": short, "genre": genre,
            "contact_addr": "杭州市拱墅区测试路1号", "linkman": "王五",
            "contact_num": "13800000000", "region_id": base["region_id"],
            "industry_id": base["industry_id"], "managementor_id": pm_id,
            "controler_id": dm_id, **extra,
        }
        if genre == 1:
            p["company"] = {
                "credit_code": f"91330100MA2SMOKE{abs(hash(name)) % 10000:04d}",
                "decisionor": 12, "custom_nature": 61, "industry_c": base["industry_id"],
                "capital": 10000000, "paid_capital": 8000000,
                "registered_addr": "杭州市拱墅区", "representative": "赵六",
            }
        else:
            p["personal"] = {
                "license_num": f"3301051990010{abs(hash(name)) % 100000:05d}",
                "license_addr": "杭州市拱墅区", "marital_status": 20, "household_nature": 10,
            }
        return p

    # 客户1：企业客户（幂等：已存在则复用，跳过创建审批）
    code, data = api(client, "GET", f"/customers?q={C1_NAME}", token)
    if data["total"] == 0:
        code, data = api(client, "POST", "/customers", pm_token,
                         json=customer_payload(C1_NAME, C1_SHORT, 1))
        check("testpm 提交客户创建审批", code == 0 and "instance_id" in data, str(data)[:150])
        inst1 = data["instance_id"]

        # 互斥：pending 期间重复提交 → 4091
        code, _ = api(client, "POST", "/customers", pm_token,
                      json=customer_payload(f"互斥检查{int(time.time())}", "互斥", 1))
        check("审批互斥拦截（4091）", code == 4091)

        code, data = api(client, "GET", "/approvals/my-submitted?page_size=5", pm_token)
        check("我的申请列表", code == 0 and any(i["id"] == inst1 for i in data["items"]))

        # 审批人视角：待办 → 详情 → 同意
        code, data = api(client, "GET", "/approvals/my-tasks?page_size=50", dm_token)
        check("部门负责人待办列表（含提交人姓名）", code == 0
              and any(i["id"] == inst1 and i["submitted_by_name"] == "M2测试项目经理"
                      for i in data["items"]))
        code, data = api(client, "GET", f"/approvals/instances/{inst1}", dm_token)
        check("审批实例详情（payload 草稿）",
              code == 0 and data["payload"]["name"] == C1_NAME and data["status"] == 10)

        check("审批同意", approve_current(client, dm_token, inst1, 10, "同意")[0] == 0)
        _, data = api(client, "GET", f"/customers?q={C1_NAME}", pm_token)
        check("审批通过后客户落库", data["total"] == 1)
        c1 = data["items"][0]["id"]
        _, data = api(client, "GET", f"/customers/{c1}", pm_token)
        check("客户详情含企业扩展", data["company"] is not None
              and data["company"]["credit_code"].startswith("91330100MA2"))
        _, data = api(client, "GET", f"/approvals/instances/{inst1}", pm_token)
        check("实例状态置已通过（20）", data["status"] == 20)
    else:
        c1 = data["items"][0]["id"]
        check("客户1（幂等复用）", c1 > 0)

    # 驳回场景：临时客户 → 驳回 → 不落库
    rej_name = f"驳回客户{int(time.time())}"
    code, data = api(client, "POST", "/customers", pm_token,
                     json=customer_payload(rej_name, "驳回", 2))
    check("提交个人客户（驳回场景）", code == 0)
    check("审批驳回", approve_current(client, dm_token, data["instance_id"], 20, "资料不全")[0] == 0)
    _, data = api(client, "GET", f"/customers?q={rej_name}", pm_token)
    check("驳回后客户不落库", data["total"] == 0)
    _, data = api(client, "GET", "/approvals/my-submitted?page_size=10", pm_token)
    check("我的申请含已驳回实例", any(i["status"] == 30 for i in data["items"]))

    # 客户3（核心企业）/ 客户4（承兑人）：幂等创建
    def ensure_customer(name: str, short: str, **extra) -> int:
        _, d = api(client, "GET", f"/customers?q={name}", token)
        if d["total"] > 0:
            return d["items"][0]["id"]
        _, d = api(client, "POST", "/customers", pm_token,
                   json=customer_payload(name, short, 1, **extra))
        approve_current(client, dm_token, d["instance_id"], 10, "同意")
        _, d = api(client, "GET", f"/customers?q={name}", token)
        return d["items"][0]["id"]

    c3 = ensure_customer(C3_NAME, C3_SHORT, is_core=True, core_rate=80)
    c4 = ensure_customer(C4_NAME, C4_SHORT, is_acceptor=True)
    _, data = api(client, "GET", f"/customers/{c3}", token)
    check("核心企业标记落库（is_core）", data["is_core"] is True)

    # ========== 4. 敏感字段变更审批 + 自由字段 ==========
    print("\n-- 客户修改审批（customer_update）--")
    _, data = api(client, "GET", f"/customers/{c1}", pm_token)
    new_short = "冒烟制造B" if data["short_name"] == "冒烟制造" else "冒烟制造"
    code, data = api(client, "POST", f"/customers/{c1}/change-requests", pm_token,
                     json={"values": {"short_name": new_short}})
    check("提交敏感字段变更（diff 生成）", code == 0, str(data)[:150])
    if code == 0:
        inst = data["instance_id"]
        _, data = api(client, "GET", f"/approvals/instances/{inst}", dm_token)
        check("diff payload 含 before/after",
              data["payload"].get("short_name", {}).get("after") == new_short)
        approve_current(client, dm_token, inst, 10, "同意")
        _, data = api(client, "GET", f"/customers/{c1}", pm_token)
        check("审批通过后 diff 应用", data["short_name"] == new_short)

    code, _ = api(client, "PATCH", f"/customers/{c1}", pm_token,
                  json={"contact_addr": "杭州市拱墅区测试路88号"})
    check("自由字段直改（免审批）", code == 0)
    # 敏感字段不在 CustomerUpdate schema 中，Pydantic 忽略 → 名称不被篡改
    api(client, "PATCH", f"/customers/{c1}", pm_token, json={"name": "越权改名"})
    _, data = api(client, "GET", f"/customers/{c1}", pm_token)
    check("敏感字段不可经自由修改接口篡改", data["name"] == C1_NAME)

    # ========== 5. 客户子资源 ==========
    print("\n-- 客户子资源 --")
    code, _ = api(client, "POST", f"/customers/{c1}/extends", pm_token, json={
        "sales_revenue": 80000000, "total_assets": 120000000,
        "people_engaged": 150, "data_date": str(date.today())})
    check("经营快照保存（同日覆盖）", code == 0)
    _, data = api(client, "GET", f"/customers/{c1}", pm_token)
    check("详情含最新快照", data["latest_extend"] is not None
          and data["latest_extend"]["sales_revenue"] == 80000000)

    _, data = api(client, "GET", f"/customers/{c1}", pm_token)
    target_cls = 20 if data["classification"] == 10 else 10
    code, _ = api(client, "POST", f"/customers/{c1}/classification", pm_token,
                  json={"classification": target_cls, "reason": "冒烟测试调整"})
    check("五级分类调整", code == 0)
    _, data = api(client, "GET", f"/customers/{c1}", pm_token)
    check("分类调整生效", data["classification"] == target_cls)

    _, data = api(client, "GET", f"/customers/{c1}/shareholders", pm_token)
    if not any(s["shareholder_name"] == "冒烟股东甲" for s in data):
        code, _ = api(client, "POST", f"/customers/{c1}/shareholders", pm_token, json={
            "shareholder_name": "冒烟股东甲", "invested_amount": 5000000,
            "shareholding_ratio": 60})
        check("添加股东", code == 0)
    else:
        check("股东（幂等复用）", True)
    code, _ = api(client, "POST", f"/customers/{c1}/shareholders", pm_token, json={
        "shareholder_name": "超额股东", "invested_amount": 1, "shareholding_ratio": 99})
    check("股东比例超限被拒（4091）", code == 4091)

    _, data = api(client, "GET", f"/customers/{c1}/directors", pm_token)
    if not any(d["director_name"] == "冒烟董事甲" for d in data):
        api(client, "POST", f"/customers/{c1}/directors", pm_token,
            json={"director_name": "冒烟董事甲"})
        code, _ = api(client, "POST", f"/customers/{c1}/directors", pm_token,
                      json={"director_name": "冒烟董事乙"})
        check("添加董事", code == 0)
    else:
        check("董事（幂等复用）", True)

    # 核心企业额度（客户3）：同起始日唯一约束（uq_core_limit_date），幂等跳过
    _, data = api(client, "GET", f"/customers/{c3}/core-limits", pm_token)
    if not any(x["valid_begin_date"] == "2026-01-01" for x in data):
        code, data = api(client, "POST", f"/customers/{c3}/core-limits", pm_token, json={
            "credit_amount": 20000000, "valid_begin_date": "2026-01-01",
            "valid_end_date": "2027-12-31", "remark": "冒烟额度"})
        check("新增核心企业额度", code == 0)
    else:
        check("核心企业额度（幂等复用）", True)
    _, data = api(client, "GET", f"/customers/{c3}/core-limits", pm_token)
    check("额度列表（旧额度自动失效）",
          len(data) >= 1 and sum(1 for x in data if x["status"] == 10) == 1)
    _, data = api(client, "GET", f"/customers/{c3}/core-history", pm_token)
    check("额度变更历史落库", len(data) >= 1)

    # 集团（母公司=客户1，成员=客户3）
    _, data = api(client, "GET", "/customer-groups", token)
    if not any(g["code"] == GROUP_CODE for g in data):
        code, data = api(client, "POST", "/customer-groups", token, json={
            "code": GROUP_CODE, "name": "冒烟集团", "parent_customer_id": c1,
            "credit_amount": 30000000})
        check("创建集团（母公司自动加入）", code == 0, str(data)[:150])
        gid = data["id"]
    else:
        gid = next(g["id"] for g in data if g["code"] == GROUP_CODE)
        check("集团（幂等复用）", True)
    _, data = api(client, "GET", f"/customer-groups/{gid}", token)
    check("集团详情（母公司为成员）", any(m["id"] == c1 for m in data["members"]))
    code, _ = api(client, "POST", f"/customer-groups/{gid}/members", token,
                  json={"customer_ids": [c3]})
    check("成员企业加入集团", code == 0)
    _, data = api(client, "GET", f"/customers/stats/group-summary/{gid}", token)
    check("集团汇总统计（成员数≥2）", data["member_count"] >= 2)

    # 授信区域
    _, data = api(client, "GET", "/credit-regions", token)
    if not any(r["code"] == REGION_CODE for r in data):
        code, data = api(client, "POST", "/credit-regions", token, json={
            "code": REGION_CODE, "name": "冒烟授信区域", "credit_amount": 50000000,
            "platform_name": "拱墅城投"})
        check("创建授信区域", code == 0, str(data)[:150])
        crid = data["id"]
    else:
        crid = next(r["id"] for r in data if r["code"] == REGION_CODE)
        check("授信区域（幂等复用）", True)
    _, data = api(client, "GET", f"/credit-regions/{crid}", token)
    check("授信区域详情（额度透出）", data["credit_amount"] == 50000000)

    # 标签
    code, data = api(client, "POST", "/dicts/tags", token,
                     json={"name": "冒烟标签", "type": 20})
    tag_id = data["id"] if code == 0 else None
    _, data = api(client, "GET", "/dicts/tags", token)
    tag_id = tag_id or next((t["id"] for t in data if t["name"] == "冒烟标签"), None)
    if tag_id:
        code, _ = api(client, "PATCH", f"/customers/{c1}/tags", pm_token,
                      json={"tags": [tag_id]})
        check("客户打标", code == 0)
        _, data = api(client, "GET", "/dicts/tags", token)
        check("标签 in_use 引用标记", next(t["in_use"] for t in data if t["id"] == tag_id))

    _, data = api(client, "GET", "/customers/stats/overview", token)
    check("客户统计概览", data["total_count"] >= 3)
    code, data = api(client, "GET", "/customers/stats/industry-chart", token)
    check("行业分布统计", code == 0 and len(data) >= 1)
    code, data = api(client, "GET", "/dicts/regions/tree", pm_token)
    check("区域树（ORM 准备数据）", code == 0 and data[0]["name"] == "浙江省")
    code, data = api(client, "GET", "/dicts/regions/search?q=拱墅", pm_token)
    check("区域搜索", code == 0 and len(data) >= 1)
    code, data = api(client, "GET", "/dicts/industries/tree", pm_token)
    check("行业树", code == 0 and data[0]["name"] == "制造业")
    code, data = api(client, "GET", "/dicts/customers?is_core=true", pm_token)
    check("客户下拉字典（核心筛选）", any(c["id"] == c3 for c in data))

    # ========== 6. 权证模块 ==========
    print("\n-- 权证模块 --")
    _, data = api(client, "GET", "/warrants?q=" + W1_NUM, token)
    if data["total"] == 0:
        code, data = api(client, "POST", "/warrants", pm_token, json={
            "warrant_num": W1_NUM, "warrant_type": 1,
            "houses": [
                {"house_locate": "拱墅区测试路1号", "house_app": 10, "house_area": 120.5,
                 "house_name": "1幢101", "house_build_year": 2015, "house_usage": 10},
                {"house_locate": "拱墅区测试路1号", "house_app": 10, "house_area": 89.3,
                 "house_name": "1幢102"},
            ],
            "owners": [{"ownership_num": "浙(2015)杭州市不动产权第0001号",
                        "owner_id": c1, "share_ratio": 100}]})
        check("创建房产权证（1:N + 所有权人）", code == 0, str(data)[:150])
        w1 = data["id"]
    else:
        w1 = data["items"][0]["id"]
        check("房产权证（幂等复用）", True)

    _, data = api(client, "GET", f"/warrants/{w1}", pm_token)
    check("权证详情聚合（2 套房产 + 1 所有权人）",
          len(data["houses"]) == 2 and len(data["owners"]) == 1
          and data["owners"][0]["owner_name"] == C1_NAME)

    code, _ = api(client, "POST", f"/warrants/{w1}/evaluates", pm_token, json={
        "evaluate_method": 20, "evaluate_value": 3000000,
        "evaluate_date": "2026-08-01", "evaluate_company": "冒烟评估公司"})
    check("新增评估记录", code == 0)
    _, data = api(client, "GET", f"/warrants/{w1}/evaluates", pm_token)
    eval_id = data["items"][0]["id"]
    code, _ = api(client, "POST", f"/warrants/{w1}/evaluates/{eval_id}/recheck", pm_token, json={
        "check_value": 3000000, "recheck_value": 2950000, "recheck_channel": "市场询价"})
    check("评估复核", code == 0)
    _, data = api(client, "GET", f"/warrants/{w1}", pm_token)
    check("主表评估字段联动", data["evaluate_value"] == 3000000
          and data["evaluate_method"] == 20)

    code, _ = api(client, "POST", f"/warrants/{w1}/storages", pm_token, json={
        "storage_type": 10, "storage_date": str(date.today())})
    check("权证入库", code == 0)
    _, data = api(client, "GET", f"/warrants/{w1}", pm_token)
    check("入库联动状态（20 已入库）", data["warrant_state"] == 20)

    code, _ = api(client, "POST", "/warrants/batch/transfer", pm_token, json={
        "warrant_ids": [w1], "to_conservator_id": dm_id, "reason": "冒烟移交"})
    check("批量移交", code == 0)
    _, data = api(client, "GET", f"/warrants/{w1}", pm_token)
    check("移交联动状态（410 已移交）", data["warrant_state"] == 410)

    # 票据权证 + 明细（承兑人 c4 / 核心 c3）
    _, data = api(client, "GET", "/warrants?q=" + WD_NUM, token)
    if data["total"] == 0:
        code, data = api(client, "POST", "/warrants", pm_token, json={
            "warrant_num": WD_NUM, "warrant_type": 31,
            "draft": {"draft_type": 20, "denomination": 1000000,
                      "draft_detail": "银行承兑汇票"}})
        wd = data["id"]
    else:
        wd = data["items"][0]["id"]
    check("创建票据权证", wd > 0)
    _, data = api(client, "GET", f"/warrants/{wd}/draft-extends", pm_token)
    if not any(d["draft_num"] == DRAFT_NUM for d in data["items"]):
        code, _ = api(client, "POST", f"/warrants/{wd}/draft-extends", pm_token, json={
            "draft_type": 20, "draft_num": DRAFT_NUM, "acceptor_id": c4, "core_id": c3,
            "draft_amount": 500000, "issue_date": "2026-01-01",
            "due_date": "2026-12-31"})
        check("添加票据明细（关联承兑人/核心）", code == 0)
    else:
        check("票据明细（幂等复用）", True)
    _, data = api(client, "GET", f"/warrants/{wd}/draft-extends", pm_token)
    check("票据明细含关联名称", data["items"][0]["acceptor_name"] == C4_NAME
          and data["items"][0]["core_name"] == C3_NAME)

    code, _ = api(client, "POST", "/warrants", pm_token, json={
        "warrant_num": W1_NUM, "warrant_type": 1,
        "houses": [{"house_locate": "x", "house_app": 10, "house_area": 1}]})
    check("权证编号重复被拒（4091）", code == 4091)

    _, data = api(client, "GET", "/warrants/stats/overview", token)
    check("权证统计概览", data["total_count"] >= 2)

    # ========== 7. data_scope 隔离 ==========
    print("\n-- data_scope 隔离 --")
    _, pm_view = api(client, "GET", "/customers?page_size=100", pm_token)
    _, dm_view = api(client, "GET", "/customers?page_size=100", dm_token)
    _, ad_view = api(client, "GET", "/customers?page_size=100", token)
    pm_names = {i["name"] for i in pm_view["items"]}
    check("pm(data_scope=10) 仅见本人管护客户",
          all(i["managementor_name"] == "M2测试项目经理" for i in pm_view["items"])
          and C1_NAME in pm_names)
    check("dept(data_scope=30) 可见本部门（≥pm 可见数）",
          dm_view["total"] >= pm_view["total"] and C1_NAME in
          {i["name"] for i in dm_view["items"]})
    check("super_admin 可见全部", ad_view["total"] >= dm_view["total"])

    _, pm_w = api(client, "GET", "/warrants?page_size=100", pm_token)
    _, dm_w = api(client, "GET", "/warrants?page_size=100", dm_token)
    check("权证 created_by 部门级可见",
          dm_w["total"] >= pm_w["total"]
          and any(w["warrant_num"] == W1_NUM for w in dm_w["items"]))

    # 权限矩阵：m2_dept 无创建权限 → 4030
    code, _ = api(client, "POST", "/customers", dm_token,
                  json=customer_payload("越权客户", "越权", 1))
    check("权限矩阵：m2_dept 创建客户被拒（4030）", code == 4030)

    # ========== 8. 附件 ==========
    print("\n-- 附件服务 --")
    fname = f"smoke_{int(time.time())}.txt"
    r = client.post(f"{BASE}/attachments", headers=bearer(pm_token),
                    data={"resource_type": "customer", "resource_id": str(c1),
                          "remark": "冒烟附件"},
                    files={"file": (fname, b"m2 smoke attachment", "text/plain")})
    body = r.json()
    check("上传附件（挂客户）", body["code"] == 0, str(body)[:150])
    att_id = body["data"]["id"] if body["code"] == 0 else None

    if att_id:
        code, data = api(client, "GET", f"/attachments?resource_type=customer&resource_id={c1}", pm_token)
        check("按资源查询附件列表",
              code == 0 and any(a["id"] == att_id for a in data))
        r = client.get(f"{BASE}/attachments/{att_id}/download", headers=bearer(pm_token))
        check("附件下载（内容一致）", r.status_code == 200 and r.content == b"m2 smoke attachment")
        code, _ = api(client, "DELETE", f"/attachments/{att_id}", pm_token)
        check("删除附件", code == 0)

    print(f"\n结果：{len(passed)} 通过 / {len(failed)} 失败")
    if failed:
        print("失败项：", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
