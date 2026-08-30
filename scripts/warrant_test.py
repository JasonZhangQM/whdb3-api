"""权证管理模块全面测试（M2 优化后回归）。

用法：python scripts/warrant_test.py（服务需在 127.0.0.1:8100 运行）
覆盖：列表筛选(含新增 auction_state/evaluate_method/owner_id)、8 类权证创建、
详情、更新、出入库状态联动、评估+复核、批量操作、删除 CASCADE 实测、
data_scope 隔离、统计、字典。
"""
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8100/api/v1"
ADMIN_PWD = "Admin@whdb3"
PREFIX = "WTST"

passed, failed = [], []


def check(name: str, cond: bool, detail: str = ""):
    (passed if cond else failed).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail and not cond else ''}")


def login(client, account, password):
    r = client.post(f"{BASE}/auth/login", json={"account": account, "password": password})
    body = r.json()
    if body["code"] != 0:
        return None
    d = body["data"]
    # 兼容不同返回结构：user_id 直接取 / user 嵌套取
    if "user_id" not in d and "user" in d:
        d["user_id"] = d["user"]["id"]
    if "user_id" not in d:
        d["user_id"] = 1  # admin 种子用户兜底
    return d


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def api(client, method, path, token, **kw):
    r = client.request(method, f"{BASE}{path}", headers=bearer(token), **kw)
    body = r.json()
    return body.get("code", -1), body.get("data")


def prepare_fixture() -> dict:
    """ORM 直插测试客户/承兑人/核心企业（幂等），返回 id。"""
    from sqlalchemy import select
    from app.core.db import SessionLocal
    import app.user.models  # noqa: F401 注册 users 表（customers FK 解析需要）
    from app.customer.models import Customer

    names = {
        "owner": "权证测试所有权人有限公司",
        "acceptor": "权证测试承兑人有限公司",
        "core": "权证测试核心企业有限公司",
    }
    ids = {}
    with SessionLocal() as db:
        for key, name in names.items():
            c = db.scalar(select(Customer).where(Customer.name == name))
            if c is None:
                c = Customer(name=name, short_name=name[:8], genre=1,
                             managementor_id=1, controler_id=1)
                db.add(c)
                db.flush()
            ids[key] = c.id
        db.commit()
    return ids


def main():
    ids = prepare_fixture()
    print(f"fixture 客户 id: {ids}")

    with httpx.Client(timeout=15) as client:
        me = login(client, "admin", ADMIN_PWD)
        check("管理员登录", me is not None)
        token = me["tokens"]["access_token"]

        # ========== A. 列表与筛选 ==========
        print("\n-- A. 列表与筛选 --")
        code, data = api(client, "GET", "/warrants?page=1&page_size=5", token)
        check("列表基础（分页）", code == 0 and "items" in data and "total" in data)
        if code == 0 and data["items"]:
            check("列表出参含 created_by_name",
                  "created_by_name" in data["items"][0],
                  str(data["items"][0].keys()))
        code, _ = api(client, "GET", f"/warrants?owner_id={ids['owner']}", token)
        check("筛选 owner_id（本轮新增）", code == 0)
        code, _ = api(client, "GET", "/warrants?auction_state=10", token)
        check("筛选 auction_state（本轮新增）", code == 0)
        code, _ = api(client, "GET", "/warrants?evaluate_method=20", token)
        check("筛选 evaluate_method（本轮新增）", code == 0)
        code, data = api(client, "GET", "/warrants?warrant_type=1&warrant_state=10", token)
        check("筛选 type+state 组合", code == 0)
        code, _ = api(client, "GET", "/warrants?q=WTST", token)
        check("关键词 q 筛选", code == 0)

        # ========== B. 创建（8 类） ==========
        print("\n-- B. 创建权证（8 类型） --")
        today = date.today().isoformat()

        def create(payload, name):
            # 幂等：已存在先复位状态再删（已流转的直接删会被 4091 拒）
            code, data = api(client, "GET", f"/warrants?q={payload['warrant_num']}", token)
            if code == 0:
                for it in data["items"]:
                    if api(client, "DELETE", f"/warrants/{it['id']}", token)[0] != 0:
                        api(client, "PATCH", f"/warrants/{it['id']}", token,
                            json={"warrant_state": 10})
                        api(client, "DELETE", f"/warrants/{it['id']}", token)
            code, data = api(client, "POST", "/warrants", token, json=payload)
            check(f"创建{name}", code == 0, str(data)[:150])
            return data["id"] if code == 0 else None

        wid_house = create({
            "warrant_num": f"{PREFIX}-H-0001", "warrant_type": 1,
            "houses": [
                {"house_locate": f"{PREFIX}花园1栋101", "house_app": 101, "house_area": 88.5,
                 "house_name": "1栋101", "house_build_year": 2018, "house_usage": 10},
                {"house_locate": f"{PREFIX}花园2栋202", "house_app": 201, "house_area": 120.0,
                 "house_usage": 20},
            ],
            "owners": [{"ownership_num": f"{PREFIX}产权001", "owner_id": ids["owner"]}],
        }, "房产（1:N 两套）")

        wid_ground = create({
            "warrant_num": f"{PREFIX}-G-0001", "warrant_type": 5,
            "ground": {"ground_locate": f"{PREFIX}宗地A", "ground_app": "WTST-2018-001", "ground_area": 666.6},
            "owners": [{"ownership_num": f"{PREFIX}产权002", "owner_id": ids["owner"]}],
        }, "土地")

        wid_stock = create({
            "warrant_num": f"{PREFIX}-S-0001", "warrant_type": 21,
            "stock": {"stock_type": 10, "target": f"{PREFIX}标的公司", "ratio": 51.0,
                      "registered_capital": 1000, "paid_capital": 500},
            "owners": [{"ownership_num": f"{PREFIX}产权003", "owner_id": ids["owner"]}],
        }, "股权")

        wid_draft = create({
            "warrant_num": f"{PREFIX}-D-0001", "warrant_type": 31,
            "draft": {"draft_type": 20, "denomination": 500000, "draft_detail": f"{PREFIX}银行承兑汇总"},
            "owners": [{"ownership_num": f"{PREFIX}产权004", "owner_id": ids["owner"]}],
        }, "票据")

        wid_vehicle = create({
            "warrant_num": f"{PREFIX}-V-0001", "warrant_type": 41,
            "vehicle": {"frame_num": f"{PREFIX}FRAME001", "plate_num": "测A00001",
                        "vehicle_brand": "测试牌"},
            "owners": [{"ownership_num": f"{PREFIX}产权005", "owner_id": ids["owner"]}],
        }, "车辆")

        wid_chattel = create({
            "warrant_num": f"{PREFIX}-C-0001", "warrant_type": 51,
            "chattel": {"chattel_type": 20, "chattel_detail": f"{PREFIX}生产线设备"},
            "owners": [{"ownership_num": f"{PREFIX}产权006", "owner_id": ids["owner"]}],
        }, "动产")

        wid_other = create({
            "warrant_num": f"{PREFIX}-O-0001", "warrant_type": 55,
            "other": {"other_type": 501, "cost": 30000, "other_detail": f"{PREFIX}管理系统",
                      "software": {"software_name": f"{PREFIX}软著V1.0", "reg_num": f"{PREFIX}SR001"}},
            "owners": [{"ownership_num": f"{PREFIX}产权007", "owner_id": ids["owner"]}],
        }, "其他+软著")

        wid_recv = create({
            "warrant_num": f"{PREFIX}-R-0001", "warrant_type": 11,
            "receivable": {"receivable_detail": f"{PREFIX}应收账款", "receive_units": [f"{PREFIX}应收单位1", f"{PREFIX}应收单位2"]},
            "owners": [{"ownership_num": f"{PREFIX}产权008", "owner_id": ids["owner"]}],
        }, "应收（含明细）")

        # ========== C. 详情 ==========
        print("\n-- C. 详情 --")
        code, d = api(client, "GET", f"/warrants/{wid_house}", token)
        check("房产详情", code == 0 and len(d.get("houses", [])) == 2, str(d)[:150])
        check("详情含 owners", len(d.get("owners", [])) == 1)
        code, d = api(client, "GET", f"/warrants/{wid_other}", token)
        check("其他详情含软著", code == 0 and (d.get("other") or {}).get("software") is not None,
              str(d)[:150])
        code, d = api(client, "GET", f"/warrants/{wid_recv}", token)
        check("应收详情含明细", code == 0 and len((d.get("receivable") or {}).get("receive_units", [])) == 2)
        code, d = api(client, "GET", f"/warrants/{wid_ground}", token)
        check("土地详情", code == 0 and d.get("ground", {}).get("ground_app") == "WTST-2018-001")
        code, _ = api(client, "GET", "/warrants/99999999", token)
        check("不存在详情 4041", code == 4041, str(code))

        # ========== D. 更新 ==========
        print("\n-- D. 更新 --")
        code, _ = api(client, "PATCH", f"/warrants/{wid_house}", token,
                      json={"evaluate_method": 20, "evaluate_value": 2000000,
                            "evaluate_date": today, "evaluate_company": "测试评估所"})
        check("PATCH 主表（评估信息）", code == 0)
        code, d = api(client, "GET", f"/warrants/{wid_house}", token)
        check("评估值已更新", d.get("evaluate_value") == 2000000, str(d.get("evaluate_value")))

        code, _ = api(client, "PUT", f"/warrants/{wid_house}/type-detail", token,
                      json={"houses": [
                          {"house_locate": f"{PREFIX}花园1栋101", "house_app": 101,
                           "house_area": 90.0, "house_usage": 30},
                          {"house_locate": f"{PREFIX}花园3栋303", "house_app": 301,
                           "house_area": 150.0, "house_usage": 10},
                      ]})
        check("PUT 房产全量替换", code == 0)
        code, d = api(client, "GET", f"/warrants/{wid_house}", token)
        check("房产替换后 2 套（删旧增新）", len(d.get("houses", [])) == 2)

        # ========== E. 出入库 + 状态联动 ==========
        print("\n-- E. 出入库状态联动 --")
        code, _ = api(client, "POST", f"/warrants/{wid_ground}/storages", token,
                      json={"storage_type": 10, "storage_date": today, "storage_explain": "首次入库"})
        check("入库", code == 0)
        code, d = api(client, "GET", f"/warrants/{wid_ground}", token)
        check("状态联动 → 20 已入库", d["warrant_state"] == 20, str(d.get("warrant_state")))
        code, d = api(client, "GET", f"/warrants/{wid_ground}/storages", token)
        check("出入库历史", code == 0 and len(d.get("items", [])) == 1)

        code, _ = api(client, "POST", f"/warrants/{wid_ground}/storages", token,
                      json={"storage_type": 310, "storage_date": today, "storage_explain": "解保出库"})
        check("解保出库", code == 0)
        code, d = api(client, "GET", f"/warrants/{wid_ground}", token)
        check("状态联动 → 310 解保出库", d["warrant_state"] == 310, str(d.get("warrant_state")))

        code, _ = api(client, "DELETE", f"/warrants/{wid_ground}", token)
        check("已流转权证删除被拒（4091）", code == 4091, str(code))

        # ========== F. 评估 + 复核 ==========
        print("\n-- F. 评估 + 复核 --")
        code, _ = api(client, "POST", f"/warrants/{wid_house}/evaluates", token,
                      json={"evaluate_method": 20, "evaluate_value": 2500000,
                            "evaluate_date": today, "evaluate_company": "测试评估所"})
        check("新增评估", code == 0)
        code, d = api(client, "GET", f"/warrants/{wid_house}", token)
        check("主表评估值同步", d["evaluate_value"] == 2500000, str(d.get("evaluate_value")))
        code, d = api(client, "GET", f"/warrants/{wid_house}/evaluates", token)
        check("评估历史", code == 0 and len(d.get("items", [])) >= 1)
        if code == 0 and d.get("items"):
            ev_id = d["items"][0]["id"]
            code, _ = api(client, "POST", f"/warrants/{wid_house}/evaluates/{ev_id}/recheck", token,
                          json={"check_value": 2400000, "recheck_value": 2450000,
                                "recheck_channel": "市场询价"})
            check("评估复核", code == 0)

        # ========== G. 批量操作 ==========
        print("\n-- G. 批量操作 --")
        batch_ids = [w for w in (wid_stock, wid_vehicle, wid_chattel) if w]
        code, d = api(client, "POST", "/warrants/batch/storage", token,
                      json={"warrant_ids": batch_ids, "storage_type": 10, "storage_date": today})
        check(f"批量入库（{len(batch_ids)} 个）", code == 0 and d["count"] == len(batch_ids))
        code, d = api(client, "GET", f"/warrants/{wid_stock}", token)
        check("批量入库后状态 20", d["warrant_state"] == 20, str(d.get("warrant_state")))

        code, d = api(client, "POST", "/warrants/batch/transfer", token,
                      json={"warrant_ids": batch_ids[:1], "to_conservator_id": me["user_id"],
                            "reason": "测试移交"})
        check("批量移交", code == 0 and d["count"] == 1)

        code, d = api(client, "POST", "/warrants/batch/cancel", token,
                      json={"warrant_ids": batch_ids[1:2], "reason": "测试注销"})
        check("批量注销", code == 0 and d["count"] == 1)
        code, d = api(client, "GET", f"/warrants/{batch_ids[1]}", token)
        check("注销后状态 990", d["warrant_state"] == 990, str(d.get("warrant_state")))

        # ========== H. 删除 + CASCADE 实测 ==========
        print("\n-- H. 删除 CASCADE 实测（ORM 查子表） --")
        from sqlalchemy import func, select
        from app.warrant.models import (WarrantEvaluate, WarrantHouse,
                                        WarrantOwnership, WarrantStorage)
        from app.core.db import SessionLocal

        code, _ = api(client, "DELETE", f"/warrants/{wid_house}", token)
        check("删除未入库权证", code == 0)
        with SessionLocal() as db:
            for model, label in ((WarrantHouse, "warrant_houses"),
                                 (WarrantOwnership, "warrant_ownerships"),
                                 (WarrantEvaluate, "warrant_evaluates")):
                n = db.scalar(select(func.count()).select_from(model).where(model.warrant_id == wid_house))
                check(f"CASCADE 清理 {label}（0 行）", n == 0, f"残留 {n} 行")

        code, _ = api(client, "DELETE", f"/warrants/{wid_draft}", token)
        check("删除票据权证", code == 0)

        # ========== I. data_scope 隔离 ==========
        print("\n-- I. data_scope 隔离 --")
        # 建 data_scope=10（本人）测试用户
        code, perms = api(client, "GET", "/permissions", token)
        perm_ids = {p["code"]: p["id"] for p in perms}
        scope_perms = [perm_ids[c] for c in ("warrant:list", "warrant:detail", "warrant:create")]
        code, d = api(client, "POST", "/roles", token,
                      json={"code": "wtst_pm", "name": "权证测试本人", "data_scope": 10})
        role_id = d["id"] if code == 0 else next(
            x["id"] for x in api(client, "GET", "/roles", token)[1] if x["code"] == "wtst_pm")
        api(client, "PUT", f"/roles/{role_id}/permissions", token,
            json={"permission_ids": scope_perms})
        code, d = api(client, "POST", "/users", token,
                      json={"username": "wtstpm", "name": "权证测试PM",
                            "email": "wtstpm@whdb-test.com", "dept_id": 1,
                            "role_ids": [role_id]})
        if code == 0:
            pm_pwd = d["initial_password"]
        else:
            _, us = api(client, "GET", "/users?q=wtstpm", token)
            uid = next(u["id"] for u in us["items"] if u["username"] == "wtstpm")
            _, d2 = api(client, "POST", f"/users/{uid}/password", token, json={})
            pm_pwd = d2["initial_password"]

        pm = login(client, "wtstpm", pm_pwd)
        check("pm 用户登录", pm is not None)
        if pm:
            pm_token = pm["tokens"]["access_token"]
            # 幂等：上轮 pm 创建的可能残留（pm 无删除权限），用 admin 清
            code, data = api(client, "GET", "/warrants?q=WTST-PM-0001", token)
            for it in (data["items"] if code == 0 else []):
                if api(client, "DELETE", f"/warrants/{it['id']}", token)[0] != 0:
                    api(client, "PATCH", f"/warrants/{it['id']}", token,
                        json={"warrant_state": 10})
                    api(client, "DELETE", f"/warrants/{it['id']}", token)
            # pm 创建一个
            code, d = api(client, "POST", "/warrants", pm_token, json={
                "warrant_num": f"{PREFIX}-PM-0001", "warrant_type": 5,
                "ground": {"ground_locate": f"{PREFIX}pm宗地", "ground_app": "WTST-PM", "ground_area": 100},
                "owners": [{"ownership_num": f"{PREFIX}产权PM", "owner_id": ids["owner"]}],
            })
            check("pm 创建权证", code == 0)
            pm_wid = d["id"] if code == 0 else None
            code, d = api(client, "GET", "/warrants?page_size=100", pm_token)
            nums = {it["warrant_num"] for it in d["items"]}
            check("pm 仅见本人（无 admin 的 WTST）",
                  f"{PREFIX}-PM-0001" in nums and f"{PREFIX}-O-0001" not in nums,
                  str(nums))
            # pm 访问 admin 的权证 → 4041（不泄露存在性）
            code, _ = api(client, "GET", f"/warrants/{wid_other}", pm_token)
            check("pm 访问他人权证 4041", code == 4041, str(code))
            if pm_wid:
                api(client, "DELETE", f"/warrants/{pm_wid}", pm_token)

        # ========== J. 统计 + 字典 ==========
        print("\n-- J. 统计 + 字典 --")
        code, d = api(client, "GET", "/warrants/stats/overview", token)
        check("统计概览", code == 0 and "total_count" in d and "by_type" in d, str(d)[:120])
        code, d = api(client, "GET", f"/warrants/stats/by-customer/{ids['owner']}", token)
        check("按客户统计", code == 0)
        code, d = api(client, "GET", "/dicts", token)
        warrant_dicts = [k for k in (d or {}) if k.startswith("warrant")] if isinstance(d, dict) else []
        check(f"字典含 warrant 分组（{len(warrant_dicts)} 个）", len(warrant_dicts) > 0,
              str(warrant_dicts)[:200])

        # ========== 清理 ==========
        print("\n-- 清理 --")
        for w in (wid_recv, wid_vehicle, wid_chattel, wid_other, wid_stock):
            if w:
                api(client, "DELETE", f"/warrants/{w}", token)

    print(f"\n{'=' * 50}\n总计 {len(passed) + len(failed)} 项：PASS {len(passed)} / FAIL {len(failed)}")
    if failed:
        print("失败项：", *[f"  - {n}" for n in failed], sep="\n")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
