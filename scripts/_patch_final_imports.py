"""最终补全：逐个导入 + 自动抓 NameError → 补 import 行。"""
import sys
import re
from pathlib import Path

sys.path.insert(0, r"c:\mysite\whdb3\whdb3-api")
BASE = Path(r"c:\mysite\whdb3\whdb3-api\app\warrant\services")

FILES = [
    "warrant_storage_service.py",
    "warrant_evaluate_service.py",
]

# 已知各文件可能用到的 schema
SCHEMA_MAP = {
    "warrant_storage_service.py": ["StorageCreate"],
    "warrant_evaluate_service.py": ["EvaluateCreate", "EvaluateRecheckCreate"],
}

for fname in FILES:
    p = BASE / fname
    content = p.read_text(encoding="utf-8")

    # 检查是否已有 from app.warrant.schemas
    if "from app.warrant.schemas" in content:
        continue

    # 在 models import 之后插入 schemas import
    needed = SCHEMA_MAP.get(fname, [])
    if needed:
        # 找最后一个 import 行
        lines = content.splitlines()
        insert_idx = 0
        for i, l in enumerate(lines):
            if l.startswith("from app.warrant.models") or l.startswith("from app.warrant.enums"):
                # 找到多行 import 的闭合
                if "(" in l and ")" not in l:
                    j = i + 1
                    while j < len(lines) and ")" not in lines[j]:
                        j += 1
                    insert_idx = j + 1
                else:
                    insert_idx = i + 1

        if insert_idx > 0:
            schema_import = f"from app.warrant.schemas import ({', '.join(needed)})\n"
            lines.insert(insert_idx, schema_import)
            content = "\n".join(lines)
            p.write_text(content, encoding="utf-8")
            print(f"  ✓ {fname}: 补了 schemas import")

# ---------- 最终验证 ----------
print("\n=== 验证 ===")
try:
    from app.warrant.services import warrant_storage_service
    print("  ✓ warrant_storage_service OK")
except Exception as e:
    print(f"  ❌ warrant_storage_service: {e}")

try:
    from app.warrant.services import warrant_evaluate_service
    print("  ✓ warrant_evaluate_service OK")
except Exception as e:
    print(f"  ❌ warrant_evaluate_service: {e}")

try:
    from app.warrant.services import warrant_ownership_service
    print("  ✓ warrant_ownership_service OK")
except Exception as e:
    print(f"  ❌ warrant_ownership_service: {e}")

try:
    from app.warrant.services import ext_service, warrant_service
    print("  ✓ ext_service + warrant_service OK")
except Exception as e:
    print(f"  ❌ ext/warrant_service: {e}")

try:
    from app.main import app
    print(f"\n✅ FastAPI {len(app.routes)} routes — 拆分完成！")
except Exception as e:
    print(f"  ❌ FastAPI: {e}")
