"""临时冒烟检查：模块导入 + 模型元数据 + 服务函数签名。"""
import importlib
import sys

checks = []

def check(name):
    try:
        mod = importlib.import_module(name)
        checks.append((name, "OK", ""))
        return mod
    except Exception as e:
        checks.append((name, "FAIL", repr(e)))
        return None

# 1. 模块导入
warrant_models = check("app.warrant.models")
check("app.warrant.services")
check("app.warrant.services.warrant_service")
check("app.warrant.services.ext_service")
check("app.warrant.api.v1.warrants")
check("app.main")

# 2. 关键函数存在性
ws = importlib.import_module("app.warrant.services.warrant_service")
for fn in ("_get_warrant_with_scope", "_disp", "_get_or_404", "delete", "create", "get_detail"):
    ok = hasattr(ws, fn)
    checks.append((f"warrant_service.{fn}", "OK" if ok else "FAIL", "" if ok else "missing"))

# 3. CASCADE ondelete 元数据验证（FK 必须带 ondelete=CASCADE）
from sqlalchemy import inspect as sa_inspect
from app.core.db import Base
if warrant_models:
    for tbl_name, tbl in Base.metadata.tables.items():
        if not tbl_name.startswith("warrant") or tbl_name == "warrant_house_apps":
            continue
        for fk in tbl.foreign_keys:
            if fk.column.table.name == "warrants":
                ok = fk.ondelete == "CASCADE"
                checks.append((f"FK {tbl_name}.{fk.parent.name}", "OK" if ok else "FAIL", f"ondelete={fk.ondelete}"))

# 4. parent_id nullable 验证
if warrant_models:
    ha = Base.metadata.tables["warrant_house_apps"]
    pc = ha.columns["parent_id"]
    ok = pc.nullable
    checks.append(("warrant_house_apps.parent_id nullable", "OK" if ok else "FAIL", f"nullable={pc.nullable}"))

# 输出
fails = 0
for name, status, extra in checks:
    mark = "PASS" if status == "OK" else "FAIL"
    if status != "OK":
        fails += 1
    print(f"[{mark}] {name} {extra}")

print(f"\n总计 {len(checks)} 项，失败 {fails} 项")
sys.exit(1 if fails else 0)
