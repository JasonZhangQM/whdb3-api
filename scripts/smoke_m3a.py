"""M3a 端到端冒烟测试：登录 → 菜单树 → 字典 → 项目 CRUD → 评审会 CRUD → 专家 CRUD

运行：conda run -n whdb3 python scripts/smoke_m3a.py
"""
from __future__ import annotations

import sys
from typing import Any

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
ADMIN = {"username": "admin", "password": "Admin@whdb3"}
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = PASS if ok else FAIL
    results.append((name, ok, detail))
    print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))


# ============================================================
# 1. 登录，拿 token
# ============================================================
print("\n=== 1. 登录 ===")
try:
    r = httpx.post(f"{BASE}/auth/login", json=ADMIN, timeout=5)
    body = r.json()
    check("登录响应码", r.status_code == 200, str(r.status_code))
    check("返回 code=0", body.get("code") == 0, f"code={body.get('code')}")
    token = body["data"]["tokens"]["access_token"]
    check("拿到 access_token", bool(token), f"len={len(token) if token else 0}")
except Exception as e:
    check("登录", False, str(e))
    print("\n后端可能未启动，退出。")
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"}


# ============================================================
# 2. 菜单树（前端路由匹配关键）
# ============================================================
print("\n=== 2. 菜单树 /users/me/menus ===")
r = httpx.get(f"{BASE}/users/me/menus", headers=headers, timeout=5)
body = r.json()
check("200 OK", r.status_code == 200, str(r.status_code))

def find_path(nodes: list[dict], path: str) -> dict | None:
    for n in nodes:
        if n.get("path") == path:
            return n
        ch = find_path(n.get("children") or [], path)
        if ch:
            return ch
    return None

tree = body.get("data") or body.get("data", {}).get("menus") or []
# 尝试多种响应结构
if isinstance(body.get("data"), list):
    tree = body["data"]
else:
    # data 可能是 dict 有 menus 字段
    tree = body.get("data", {}).get("menus", [])

article_menu = find_path(tree, "/article")
check("项目管理 /article 存在", article_menu is not None)
if article_menu:
    children = [c["path"] for c in article_menu.get("children", [])]
    check("项目列表 /article/list 子菜单", "/article/list" in children, str(children))

appraisal_menu = find_path(tree, "/appraisal")
check("评审管理 /appraisal 存在", appraisal_menu is not None)
if appraisal_menu:
    children = [c["path"] for c in appraisal_menu.get("children", [])]
    check("评审会列表 /appraisal/list 子菜单", "/appraisal/list" in children, str(children))
    check("专家库 /appraisal/experts 子菜单", "/appraisal/experts" in children, str(children))

# 验证 component 字段（前端 glob 匹配关键）
if article_menu:
    for child in article_menu.get("children", []):
        if child["path"] == "/article/list":
            comp = child.get("component", "")
            check("article/list component = /article/index", comp == "/article/index", comp)

if appraisal_menu:
    for child in appraisal_menu.get("children", []):
        if child["path"] == "/appraisal/list":
            comp = child.get("component", "")
            check("appraisal/list component = /appraisal/index", comp == "/appraisal/index", comp)
        if child["path"] == "/appraisal/experts":
            comp = child.get("component", "")
            check("appraisal/experts component = /appraisal/experts", comp == "/appraisal/experts", comp)


# ============================================================
# 3. M3a 字典接口
# ============================================================
print("\n=== 3. 字典接口 ===")
for name, path, key in [
    ("项目字典", "/dicts/article", "article_state"),
    ("评审字典", "/dicts/appraisal", "meeting_state"),
    ("评审字典 review_model", "/dicts/appraisal", "review_model"),
    ("专家类别字典", "/dicts/expert-categories", None),
]:
    r = httpx.get(f"{BASE}{path}", headers=headers, timeout=5)
    check(f"{name} 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200 and key:
        data = r.json().get("data", {})
        check(f"{name} 含 {key}", key in data, str(list(data.keys()) if isinstance(data, dict) else type(data).__name__))


# ============================================================
# 4. 项目模块：CRUD 全链路
# ============================================================
print("\n=== 4. 项目 CRUD ===")
# 4a. 列表（空库）
r = httpx.get(f"{BASE}/articles", headers=headers, timeout=5)
check("GET /articles 200", r.status_code == 200, str(r.status_code))

# 4b. 先拿一个有效 customer_id 和 product_id（从已有字典/列表）
customer_id: int | None = None
product_id: int | None = None
emp_id: int | None = None

rc = httpx.get(f"{BASE}/dicts/customers?page=1&page_size=1", headers=headers, timeout=5)
if rc.status_code == 200:
    items = rc.json().get("data", {}).get("items", [])
    if items:
        customer_id = items[0]["id"]
        check("拿到 customer_id", True, f"id={customer_id}")
    else:
        check("拿到 customer_id", False, "客户列表为空")

rp = httpx.get(f"{BASE}/dicts/article-products", headers=headers, timeout=5)
if rp.status_code == 200:
    data = rp.json().get("data") or []
    if isinstance(data, list) and data:
        product_id = data[0]["id"]
        check("拿到 product_id", True, f"id={product_id}")
    else:
        check("拿到 product_id", False, str(data)[:80]); print("  SKIP 项目 seed 数据缺失")

re_ = httpx.get(f"{BASE}/dicts/users", headers=headers, timeout=5)
if re_.status_code == 200:
    data = re_.json().get("data") or []
    if isinstance(data, list) and data:
        emp_id = data[0]["id"]

if customer_id and product_id:
    # 4c. 创建项目
    article_payload = {
        "customer_id": customer_id,
        "product_id": product_id,
        "article_state": 10,
        "renewal": 100.0,
        "augment": 20.0,
        "credit_term": 12,
    }
    if emp_id:
        article_payload["director_id"] = emp_id
    r = httpx.post(f"{BASE}/articles", json=article_payload, headers=headers, timeout=5)
    check("POST /articles 创建项目", r.status_code in (200, 201), f"status={r.status_code}")
    article_id: int | None = None
    if r.status_code in (200, 201):
        body = r.json()
        # 兼容 {data:{id}} 和直接 id
        article_id = (body.get("data") or {}).get("id") if isinstance(body.get("data"), dict) else body.get("id")
        if article_id:
            check("返回项目 id", True, f"id={article_id}")

            # 4d. 详情
            r = httpx.get(f"{BASE}/articles/{article_id}", headers=headers, timeout=5)
            check(f"GET /articles/{article_id} 详情", r.status_code == 200, str(r.status_code))
            if r.status_code == 200:
                body = r.json()
                data = body.get("data", body)
                check("详情含 article_num", bool(data.get("article_num")))
                check("详情含 article_state_display", bool(data.get("article_state_display")))

            # 4e. 修改
            r = httpx.put(
                f"{BASE}/articles/{article_id}",
                json={"credit_term": 24, "remark": "冒烟测试修改"},
                headers=headers,
                timeout=5,
            )
            check(f"PUT /articles/{article_id} 修改", r.status_code in (200, 204), f"status={r.status_code}")

            # 4f. 列表含新数据
            r = httpx.get(f"{BASE}/articles?page=1&page_size=5", headers=headers, timeout=5)
            check("GET /articles 列表有数据", r.status_code == 200 and len(r.json().get("data", {}).get("items", [])) >= 1)

            # 4g. 删除（cleanup）
            r = httpx.delete(f"{BASE}/articles/{article_id}", headers=headers, timeout=5)
            check(f"DELETE /articles/{article_id}", r.status_code in (200, 204), f"status={r.status_code}")
        else:
            check("拿到 article_id", False, str(r.json())[:100])
    else:
        check("创建项目响应码非 200", False, r.text[:200])
else:
    print("  SKIP 项目 CRUD 缺少 product_id")


# ============================================================
# 5. 评审会模块：CRUD
# ============================================================
print("\n=== 5. 评审会 CRUD ===")
# 5a. 列表
r = httpx.get(f"{BASE}/appraisals", headers=headers, timeout=5)
check("GET /appraisals 200", r.status_code == 200, str(r.status_code))

if emp_id:
    # 5b. 创建评审会
    from datetime import date
    review_date = date.today().isoformat()
    r = httpx.post(
        f"{BASE}/appraisals",
        json={
            "review_model": 1,
            "review_date": review_date,
            "compere_id": emp_id,
        },
        headers=headers,
        timeout=5,
    )
    check("POST /appraisals 创建", r.status_code in (200, 201), f"status={r.status_code}")
    appraisal_id: int | None = None
    if r.status_code in (200, 201):
        body = r.json()
        appraisal_id = (body.get("data") or {}).get("id") if isinstance(body.get("data"), dict) else body.get("id")
        if appraisal_id:
            check("返回评审会 id", True, f"id={appraisal_id}")

            # 5c. 删除未完成的评审会（finish 后不可删）
            r = httpx.delete(f"{BASE}/appraisals/{appraisal_id}", headers=headers, timeout=5)
            check(f"DELETE /appraisals/{appraisal_id}（未完成）", r.status_code in (200, 204), f"status={r.status_code}")

            # 5d. 再创建一个测试 finish
            r2 = httpx.post(
                f"{BASE}/appraisals",
                json={
                    "review_model": 1,
                    "review_date": review_date,
                    "compere_id": emp_id,
                },
                headers=headers,
                timeout=5,
            )
            aid2 = ((r2.json().get("data") or {}).get("id"))
            if aid2:
                r = httpx.post(f"{BASE}/appraisals/{aid2}/finish", headers=headers, timeout=5)
                check(f"POST /appraisals/{aid2}/finish 完成", r.status_code in (200, 204), f"status={r.status_code}")
        else:
            check("拿到 appraisal_id", False, str(r.json())[:100])
    else:
        check("创建评审会响应码非 200", False, r.text[:200])
else:
    check("跳过评审会 CRUD", False, "缺少 emp_id")


# ============================================================
# 6. 专家库 CRUD
# ============================================================
print("\n=== 6. 专家 CRUD ===")
r = httpx.get(f"{BASE}/review-experts", headers=headers, timeout=5)
check("GET /review-experts 200", r.status_code == 200, str(r.status_code))

# 6b. 拿一个 category_id
cat_id: int | None = None
rc = httpx.get(f"{BASE}/dicts/expert-categories", headers=headers, timeout=5)
if rc.status_code == 200:
    data = rc.json().get("data") or []
    if isinstance(data, list) and data:
        cat_id = data[0]["id"]

# 6c. 创建专家
r = httpx.post(
    f"{BASE}/review-experts",
    json={
        "name": "冒烟测试专家", "expert_type": 20,
        "category_id": cat_id,
        "unit": "测试单位",
        "title": "高级工程师",
        "phone": "13800138000",
    },
    headers=headers,
    timeout=5,
)
check("POST /review-experts 创建", r.status_code in (200, 201), f"status={r.status_code}")
expert_id: int | None = None
if r.status_code in (200, 201):
    body = r.json()
    expert_id = (body.get("data") or {}).get("id") if isinstance(body.get("data"), dict) else body.get("id")
    if expert_id:
        check("返回专家 id", True, f"id={expert_id}")

        # 6d. 修改
        r = httpx.put(
            f"{BASE}/review-experts/{expert_id}",
            json={"title": "教授"},
            headers=headers,
            timeout=5,
        )
        check(f"PUT /review-experts/{expert_id}", r.status_code in (200, 204), f"status={r.status_code}")

        # 6e. 删除
        r = httpx.delete(f"{BASE}/review-experts/{expert_id}", headers=headers, timeout=5)
        check(f"DELETE /review-experts/{expert_id}", r.status_code in (200, 204), f"status={r.status_code}")
    else:
        check("拿到 expert_id", False, str(r.json())[:100])
else:
    check("创建专家响应码非 200", False, r.text[:200])


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 50)
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed
print(f" 总计: {total}  通过: {passed}  失败: \033[91m{failed}\033[0m")
if failed == 0:
    print("  🎉 全部通过！")
else:
    print("\n  失败详情：")
    for name, ok, detail in results:
        if not ok:
            print(f"    - {name}: {detail}")
print("=" * 50)

sys.exit(0 if failed == 0 else 1)

