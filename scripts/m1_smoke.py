"""M1 验收冒烟：登录/双token/改密踢出/权限矩阵/data_scope 隔离/审计日志。

用法：python scripts/m1_smoke.py（服务需在 127.0.0.1:8101 运行）
可重复执行：账号/部门按存在性容错。
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://127.0.0.1:8102/api/v1"
ADMIN_PWD = "Admin@whdb3"
ALT_PWD = "Test@Pass123"

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


def main() -> None:
    client = httpx.Client(timeout=15)

    # ---------- 1. 登录 + /users/me ----------
    me = login(client, "admin", ADMIN_PWD) or login(client, "admin", ALT_PWD)
    check("管理员登录（双 token）", me is not None and "access_token" in me["tokens"])
    token = me["tokens"]["access_token"]
    refresh = me["tokens"]["refresh_token"]

    r = client.get(f"{BASE}/users/me", headers=bearer(token)).json()
    check("/users/me 权限上下文", r["code"] == 0 and r["data"]["is_super_admin"] is True
          and len(r["data"]["menus"]) > 0, str(r)[:200])
    check("must_change_password 标志透出", "must_change_password" in r["data"])

    r = client.get(f"{BASE}/users/me/menus", headers=bearer(token)).json()
    # M2 后菜单含 Dashboard 等多入口，不依赖首节点顺序，只校验 /system 节点存在
    ok_tree = (r["code"] == 0 and isinstance(r["data"], list) and r["data"]
               and any(n.get("path") == "/system" for n in r["data"]))
    check("/users/me/menus vben 路由树", ok_tree, str(r)[:200])

    # ---------- 2. refresh 旋转 ----------
    r = client.post(f"{BASE}/auth/refresh", json={"refresh_token": refresh}).json()
    check("refresh 旋转式刷新", r["code"] == 0 and "access_token" in r["data"])
    if r["code"] == 0:
        token = r["data"]["access_token"]
        # 旧 refresh 应已作废（单设备语义）
        r2 = client.post(f"{BASE}/auth/refresh", json={"refresh_token": refresh}).json()
        check("旧 refresh 已作废", r2["code"] != 0)
        refresh = r["data"]["refresh_token"]

    # ---------- 3. 未认证拦截 ----------
    r = client.get(f"{BASE}/users/me").json()
    check("无 token 访问被拦截", r["code"] in (4011, 4012))

    # ---------- 4. 部门 + 用户（审计数据来源） ----------
    r = client.get(f"{BASE}/departments/tree", headers=bearer(token)).json()
    dept_id = None
    if r["code"] == 0:
        for node in r["data"]:
            if node["name"] == "测试一部":
                dept_id = node["id"]
    if dept_id is None:
        r = client.post(f"{BASE}/departments", headers=bearer(token),
                        json={"parent_id": 0, "name": "测试一部", "ordery": 900}).json()
        check("创建部门", r["code"] == 0, str(r)[:200])
        dept_id = r["data"]["id"]
    else:
        check("创建部门（已存在，幂等）", True)

    # 查 pm / reader 角色 id
    r = client.get(f"{BASE}/roles", headers=bearer(token)).json()
    roles = {x["code"]: x["id"] for x in r["data"]}
    builtin = {"super_admin", "dept_manager", "controler", "assistant",
               "pm", "reviewer", "auditor", "reader"}
    check("角色列表（8 内置齐全）", r["code"] == 0 and builtin <= set(roles))

    # 创建测试用户 testpm（pm 角色：本人）；已存在则重置密码（幂等）
    r = client.post(f"{BASE}/users", headers=bearer(token), json={
        "username": "testpm", "name": "测试项目经理", "email": "testpm@whdb-test.com",
        "dept_id": dept_id, "role_ids": [roles["pm"]],
    }).json()
    if r["code"] == 4090:  # 已存在：管理员重置密码取新初始密码
        r2 = client.get(f"{BASE}/users", headers=bearer(token),
                        params={"q": "testpm"}).json()
        existed_id = r2["data"]["items"][0]["id"]
        # 归位部门（m2_smoke 等脚本可能把 testpm 挪去别的部门，破坏本部门隔离断言前提）
        client.patch(f"{BASE}/users/{existed_id}", headers=bearer(token),
                     json={"dept_id": dept_id})
        r = client.post(f"{BASE}/users/{existed_id}/password", headers=bearer(token),
                        json={}).json()
        check("用户已存在→重置密码（幂等）", r["code"] == 0 and "initial_password" in r["data"],
              str(r)[:200])
    else:
        check("创建用户（返回初始密码）", r["code"] == 0 and "initial_password" in r["data"],
              str(r)[:200])
    pm_pwd = r["data"].get("initial_password", "x") if r["code"] == 0 else "x"

    # 幂等清理：把 testpm 角色重置为纯 pm（清除历史运行附加的 viewer 角色）
    r2 = client.get(f"{BASE}/users", headers=bearer(token), params={"q": "testpm"}).json()
    if r2["code"] == 0 and r2["data"]["items"]:
        existed_id = r2["data"]["items"][0]["id"]
        client.put(f"{BASE}/users/{existed_id}/roles", headers=bearer(token),
                   json={"role_ids": [roles["pm"]]})

    # 权限矩阵：无 user:list 的角色调列表 → 4030
    pm = login(client, "testpm", pm_pwd)
    check("新用户登录（首登强制改密标志）", pm is not None and pm["must_change_password"] is True)
    if pm:
        r = client.get(f"{BASE}/users", headers=bearer(pm["tokens"]["access_token"])).json()
        check("权限矩阵：pm 调 /users 被拒(4030)", r["code"] == 4030, str(r)[:120])

    # data_scope 隔离：自定义角色（本部门 + user:list）应只见本部门
    r = client.post(f"{BASE}/roles", headers=bearer(token), json={
        "code": "dept_viewer", "name": "部门查看员（测试）", "data_scope": 20,
    }).json()
    if r["code"] != 0:  # 幂等：已存在则查回
        r = client.get(f"{BASE}/roles", headers=bearer(token)).json()
        viewer_role = next(x["id"] for x in r["data"] if x["code"] == "dept_viewer")
    else:
        viewer_role = r["data"]["id"]
    # 找 user:list 权限 id
    r = client.get(f"{BASE}/permissions", headers=bearer(token)).json()
    perm_user_list = next(p["id"] for p in r["data"] if p["code"] == "user:list")
    r = client.put(f"{BASE}/roles/{viewer_role}/permissions", headers=bearer(token),
                   json={"permission_ids": [perm_user_list]}).json()
    check("角色分配权限", r["code"] == 0, str(r)[:120])

    # testpm 改密后重分配角色，验证分配角色接口
    if pm:
        client.post(f"{BASE}/auth/login", json={"account": "testpm", "password": pm_pwd})
        r = client.patch(f"{BASE}/users/me/password", headers=bearer(pm["tokens"]["access_token"]),
                         json={"old_password": pm_pwd, "new_password": "Pm@Pass12345"}).json()
        check("本人改密", r["code"] == 0, str(r)[:120])
        # 改密踢出：旧 access 失效
        r = client.get(f"{BASE}/users/me", headers=bearer(pm["tokens"]["access_token"])).json()
        check("改密后旧 token 失效", r["code"] in (4011, 4012, 4013))
        pm = login(client, "testpm", "Pm@Pass12345")

    # 用 admin 查 testpm 的 user_id
    r = client.get(f"{BASE}/users", headers=bearer(token),
                   params={"q": "testpm"}).json()
    testpm_id = r["data"]["items"][0]["id"] if r["data"]["items"] else None
    r = client.put(f"{BASE}/users/{testpm_id}/roles", headers=bearer(token),
                   json={"role_ids": [roles["pm"], viewer_role]}).json()
    check("分配用户角色", r["code"] == 0, str(r)[:120])

    # 权限缓存失效验证：重新登录后 testpm 有 user:list
    pm = login(client, "testpm", "Pm@Pass12345")
    r = client.get(f"{BASE}/users", headers=bearer(pm["tokens"]["access_token"])).json()
    items = r["data"]["items"] if r["code"] == 0 else []
    names = {i["username"] for i in items}
    check("data_scope=20 本部门隔离（只见测试一部成员）",
          r["code"] == 0 and "testpm" in names and "admin" not in names,
          f"code={r['code']} names={names}")

    # ---------- 5. 停用踢出 ----------
    r = client.patch(f"{BASE}/users/{testpm_id}/status", headers=bearer(token),
                     json={"status": 20}).json()
    check("停用用户", r["code"] == 0, str(r)[:120])
    r = client.get(f"{BASE}/users/me", headers=bearer(pm["tokens"]["access_token"])).json()
    check("停用即踢出（4013）", r["code"] == 4013, str(r)[:120])
    # 恢复启用（便于重复执行）
    client.patch(f"{BASE}/users/{testpm_id}/status", headers=bearer(token), json={"status": 10})

    # ---------- 6. 字典 & 日志 ----------
    r = client.get(f"{BASE}/dicts/genders", headers=bearer(token)).json()
    check("性别字典", r["code"] == 0 and {"value": 1, "label": "男"} in r["data"])
    r = client.get(f"{BASE}/dicts/users", headers=bearer(token)).json()
    check("员工下拉", r["code"] == 0 and any(u["username"] == "admin" for u in r["data"]))
    r = client.get(f"{BASE}/operation-logs", headers=bearer(token)).json()
    actions = {i["action"] for i in r["data"]["items"]}
    check("操作审计日志落库（create/assign_role 等）",
          r["code"] == 0 and {"create", "assign_role"} <= actions,
          f"actions={actions}")
    r = client.get(f"{BASE}/login-logs", headers=bearer(token)).json()
    check("登录日志（含成功/失败）", r["code"] == 0 and r["data"]["total"] > 0)

    # ---------- 7. 登出黑名单 ----------
    r = client.post(f"{BASE}/auth/logout", headers=bearer(token)).json()
    check("登出", r["code"] == 0)
    r = client.get(f"{BASE}/users/me", headers=bearer(token)).json()
    check("登出后 token 进黑名单", r["code"] in (4011, 4012))

    print(f"\n结果：{len(passed)} 通过 / {len(failed)} 失败")
    if failed:
        print("失败项：", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
