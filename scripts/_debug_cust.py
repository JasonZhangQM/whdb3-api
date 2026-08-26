"""临时调试：客户创建审批提交响应。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8102/api/v1"

client = httpx.Client(timeout=15)
r = client.post(f"{BASE}/auth/login", json={"account": "admin", "password": "Admin@whdb3"})
token = r.json()["data"]["tokens"]["access_token"]

# 取基础数据 id
r = client.get(f"{BASE}/dicts/regions/search", headers={"Authorization": f"Bearer {token}"},
               params={"q": "拱墅"})
region_id = r.json()["data"][0]["id"]
r = client.get(f"{BASE}/dicts/industries/tree", headers={"Authorization": f"Bearer {token}"})
industry_id = r.json()["data"][0]["children"][0]["id"]

# pm/dm 用户 id
r = client.get(f"{BASE}/users", headers={"Authorization": f"Bearer {token}"}, params={"q": "test"})
users = {u["username"]: u["id"] for u in r.json()["data"]["items"]}
pm_id, dm_id = users["testpm"], users["testdm"]

body = {
    "name": "调试客户", "short_name": "调试", "genre": 1,
    "contact_addr": "杭州市", "linkman": "王五", "contact_num": "13800000000",
    "region_id": region_id, "industry_id": industry_id,
    "managementor_id": pm_id, "controler_id": dm_id,
    "company": {
        "credit_code": "91330100MA2DEBUG0001", "decisionor": 12, "custom_nature": 61,
        "industry_c": industry_id, "capital": 10000000, "paid_capital": 8000000,
        "registered_addr": "杭州市", "representative": "赵六",
    },
}
r = client.post(f"{BASE}/customers", headers={"Authorization": f"Bearer {token}"}, json=body)
print("by admin:", r.status_code, r.text[:300])
