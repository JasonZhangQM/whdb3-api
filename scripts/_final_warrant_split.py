"""warrant 模块 service 最终拆分脚本。

从 git HEAD 读取原始 ext_service.py + warrant_service.py，
按表拆成 7 个独立 service 文件，每个文件自带完整 import + 辅助函数，
不依赖循环引用。
"""
import subprocess
from pathlib import Path
import re

BASE = Path(r"c:\mysite\whdb3\whdb3-api\app\warrant\services")

def git_show(path):
    return subprocess.check_output(
        ["git", "show", f"HEAD:{path}"],
        cwd=r"c:\mysite\whdb3\whdb3-api", text=True, encoding="utf-8"
    )

# 读取原始文件
ext_raw = git_show("app/warrant/services/ext_service.py")
main_raw = git_show("app/warrant/services/warrant_service.py")

# ---------- 辅助函数：切分 ----------
def split_funcs(src: str):
    """按 def 切分，返回 (header_str, [(func_name, func_body_without_def_line)])"""
    lines = src.splitlines()
    header_end = 0
    blocks = []
    cur = None
    for i, line in enumerate(lines):
        if re.match(r"^def \w+\(", line):
            if cur is None:
                header_end = i
            else:
                cur["end"] = i
                blocks.append(cur)
            name = re.match(r"^def (\w+)\(", line).group(1)
            cur = {"name": name, "start": i, "end": len(lines), "sig": line, "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur is not None:
        blocks.append(cur)
    return "\n".join(lines[:header_end]), blocks

def func_block(cur):
    return cur["sig"] + "\n" + "\n".join(cur["body"])

# ---------- 解析原始文件 ----------
ext_header, ext_funcs = split_funcs(ext_raw)
main_header, main_funcs = split_funcs(main_raw)

print(f"原始 ext_service: {len(ext_funcs)} 函数, header {len(ext_header.splitlines())} 行")
print(f"原始 warrant_service: {len(main_funcs)} 函数, header {len(main_header.splitlines())} 行")

# ---------- ext_service 函数归属 ----------
# 每个新文件的函数列表
ownership_funcs = ["list_owners", "add_owner", "update_owner", "delete_owner", "_get_owner"]
type_detail_funcs = ["_get_warrant", "create_ext", "_add_house", "get_type_detail", "update_type_detail", "_delete_ext"]
real_estate_funcs = ["add_house", "delete_house", "add_ground", "delete_ground", "add_construction", "delete_construction", "_ground_dict"]
draft_extend_funcs = ["list_draft_extends", "add_draft_extend", "update_draft_extend", "delete_draft_extend", "_get_draft_extend"]
receive_extend_funcs = ["list_receive_extends", "add_receive_extend", "delete_receive_extend"]

def find_block(funcs, name):
    for f in funcs:
        if f["name"] == name:
            return func_block(f)
    return None

def collect_blocks(funcs, names):
    blocks = []
    for n in names:
        b = find_block(funcs, n)
        if b is None:
            print(f"  ⚠️ 找不到函数 {n}")
        else:
            blocks.append(b)
    return blocks

# ---------- 辅助函数（各文件内部 copy，不循环引用）----------
GET_WARRANT = '''def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


'''

GET_OR_404 = '''def _get_or_404(db: Session, warrant_id: int) -> Warrant:
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


'''

# ---------- 写入新文件 ----------
# 1. warrant_ownership_service.py
p = BASE / "warrant_ownership_service.py"
blocks = collect_blocks(ext_funcs, ownership_funcs)
content = f'''"""产权人 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.customer.models import Customer
from app.warrant.models import Warrant, WarrantOwnership
from app.warrant.schemas import OwnershipCreate, OwnershipUpdate

{GET_WARRANT}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 2. warrant_type_detail_service.py
p = BASE / "warrant_type_detail_service.py"
blocks = collect_blocks(ext_funcs, type_detail_funcs)
content = f'''"""权证按类型分发的详情 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.enums import WarrantType
from app.warrant.models import (
    Warrant, WarrantStock, WarrantVehicle, WarrantChattel,
    WarrantOther, WarrantPatent, WarrantSoftware,
)
from app.warrant.schemas import TypeDetailUpdate

{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 3. warrant_real_estate_service.py
p = BASE / "warrant_real_estate_service.py"
blocks = collect_blocks(ext_funcs, real_estate_funcs)
content = f'''"""不动产类 service（房产/土地/在建工程）。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantHouse, WarrantGround, WarrantConstruction

{GET_WARRANT}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 4. warrant_draft_extend_service.py
p = BASE / "warrant_draft_extend_service.py"
blocks = collect_blocks(ext_funcs, draft_extend_funcs)
content = f'''"""展期草稿 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantDraftExtend
from app.warrant.schemas import DraftExtendCreate, DraftExtendUpdate

{GET_WARRANT}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 5. warrant_receive_extend_service.py
p = BASE / "warrant_receive_extend_service.py"
blocks = collect_blocks(ext_funcs, receive_extend_funcs)
content = f'''"""已接收展期 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantReceiveExtend
from app.warrant.schemas import ReceiveExtendCreate

{GET_WARRANT}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 6. warrant_storage_service.py
storage_funcs = ["list_storages", "_latest_storages", "_storage_brief", "add_storage", "_apply_state"]
blocks = collect_blocks(main_funcs, storage_funcs)
p = BASE / "warrant_storage_service.py"
content = f'''"""权证存储 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.user.models import User
from app.warrant.enums import LABELS, StorageType, WarrantState
from app.warrant.models import Warrant, WarrantStorage

{GET_OR_404}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# 7. warrant_evaluate_service.py
evaluate_funcs = ["list_evaluates", "add_evaluate", "add_recheck", "list_evaluate_companies", "create_evaluate_company", "delete_evaluate_company"]
blocks = collect_blocks(main_funcs, evaluate_funcs)
p = BASE / "warrant_evaluate_service.py"
content = f'''"""权证评估 service + 评估公司字典。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import (
    Warrant, WarrantEvaluate, WarrantEvaluateRecheck, WarrantEvaluateCompany,
)

{GET_OR_404}{chr(10).join(blocks)}
'''
p.write_text(content, encoding="utf-8")
print(f"  + {p.name}")

# ---------- ext_service.py → 纯 re-export ----------
p = BASE / "ext_service.py"
content = '''"""ext_service 已按 AGENTS.md §2.2 拆分到独立 service 文件。

本文件保留作为聚合出口（API 层 25+ 处调用入口不变）。
"""

# 产权人
from .warrant_ownership_service import (
    list_owners, add_owner, update_owner, delete_owner, _get_owner, _get_warrant,
)  # noqa: F401

# 权证按类型分发详情
from .warrant_type_detail_service import (
    create_ext, get_type_detail, update_type_detail,
    _add_house, _delete_ext,
)  # noqa: F401

# 不动产类
from .warrant_real_estate_service import (
    add_house, delete_house, add_ground, delete_ground,
    add_construction, delete_construction, _ground_dict,
)  # noqa: F401

# 展期草稿
from .warrant_draft_extend_service import (
    list_draft_extends, add_draft_extend, update_draft_extend,
    delete_draft_extend, _get_draft_extend,
)  # noqa: F401

# 已接收展期
from .warrant_receive_extend_service import (
    list_receive_extends, add_receive_extend, delete_receive_extend,
)  # noqa: F401
'''
p.write_text(content, encoding="utf-8")
print(f"  ✓ ext_service.py → re-export ({len(content.splitlines())} 行)")

# ---------- warrant_service.py → 主表函数 + re-export ----------
# 主表函数（保留）
main_only_names = {
    "_disp", "_get_or_404", "_get_warrant_with_scope",
    "list_warrants", "_owner_names_map", "_user_names",
    "create", "_add_owners", "update", "delete",
    "get_detail",
    "batch_storage", "batch_transfer", "batch_cancel",
    "submit_release_out_request", "get_release_out_pending",
    "submit_lend_out_request", "get_lend_out_pending",
    "stats_overview", "stats_by_customer",
}

kept = []
for f in main_funcs:
    if f["name"] in main_only_names:
        kept.append(func_block(f))

# 组装 header（取原始 header，去掉末尾的 === 分隔线）
header_lines = main_header.splitlines()
cut = 0
for i, l in enumerate(header_lines):
    if l.startswith("# ==="):
        cut = i
        break
if cut == 0:
    cut = len(header_lines)
header_clean = "\n".join(header_lines[:cut])

reexport_block = '''
# ---------- 子模块 re-export（按 AGENTS.md §2.2 拆分到独立 service）----------
from .warrant_evaluate_service import (
    list_evaluates, add_evaluate, add_recheck,
    list_evaluate_companies, create_evaluate_company, delete_evaluate_company,
)  # noqa: F402,E402
from .warrant_storage_service import (
    list_storages, add_storage,
)  # noqa: F402,E402
'''

new_main = header_clean + "\n" + reexport_block + "\n" + "\n\n".join(kept) + "\n"
p = BASE / "warrant_service.py"
p.write_text(new_main, encoding="utf-8")
print(f"  ✓ warrant_service.py → {len(new_main.splitlines())} 行")

print("\n=== 拆分完成，验证 ===")

# ---------- 验证 ----------
errors = []
for fname in ["warrant_ownership_service.py", "warrant_type_detail_service.py",
              "warrant_real_estate_service.py", "warrant_draft_extend_service.py",
              "warrant_receive_extend_service.py", "warrant_storage_service.py",
              "warrant_evaluate_service.py", "ext_service.py", "warrant_service.py"]:
    mod = fname.replace(".py", "")
    try:
        __import__(f"app.warrant.services.{mod}")
        print(f"  ✓ {fname}")
    except Exception as e:
        errors.append((fname, str(e)))
        print(f"  ❌ {fname}: {str(e)[:80]}")

if not errors:
    import sys; sys.path.insert(0, str(BASE.parent.parent.parent))
    import app.main
    from app.main import app
    print(f"\n✅ FastAPI {len(app.routes)} routes — 拆分完成！")
else:
    print(f"\n❌ {len(errors)} 个文件有错误")
