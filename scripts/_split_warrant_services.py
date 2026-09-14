"""拆分 warrant 模块 service 文件。

- 读入 ext_service.py / warrant_service.py 原始内容
- 按所属表分组，抽取函数体
- 生成新文件：ownership / type_detail / real_estate / draft_extend / receive_extend / storage / evaluate
- 重写 ext_service.py → 纯 re-export
- 重写 warrant_service.py → 主表 CRUD + 审批 + re-export
"""
import re
from pathlib import Path

BASE = Path(r"c:\mysite\whdb3\whdb3-api\app\warrant\services")
EXT_PATH = BASE / "ext_service.py"
MAIN_PATH = BASE / "warrant_service.py"

def read_lines(p: Path):
    return p.read_text(encoding="utf-8").splitlines()

def split_functions(lines):
    """按 'def xxx' 把文件切成函数块。返回 list of (func_name, start_line, end_line, block_lines)"""
    funcs = []
    current = None
    header = []  # 首个 def 之前的内容（imports / docstring）
    for i, line in enumerate(lines):
        if re.match(r"^def \w+\(", line):
            if current is None:
                header = lines[:i]
            else:
                current["end"] = i
                funcs.append(current)
            name = re.match(r"^def (\w+)\(", line).group(1)
            current = {"name": name, "start": i, "end": len(lines), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        funcs.append(current)
    return header, funcs

# ---------- 1. 解析 ext_service.py ----------
ext_lines = read_lines(EXT_PATH)
ext_header, ext_funcs = split_functions(ext_lines)
print(f"ext_service.py: header {len(ext_header)} 行, {len(ext_funcs)} 个函数")

# 按表分组 ext_service 的函数
ext_by_file = {
    "warrant_ownership_service.py": ["list_owners", "add_owner", "update_owner", "delete_owner", "_get_owner"],
    "warrant_type_detail_service.py": ["create_ext", "_add_house", "get_type_detail", "update_type_detail", "_delete_ext", "_get_warrant"],
    "warrant_real_estate_service.py": ["add_house", "delete_house", "add_ground", "delete_ground", "add_construction", "delete_construction", "_ground_dict"],
    "warrant_draft_extend_service.py": ["list_draft_extends", "add_draft_extend", "update_draft_extend", "delete_draft_extend", "_get_draft_extend"],
    "warrant_receive_extend_service.py": ["list_receive_extends", "add_receive_extend", "delete_receive_extend"],
}
# 反向映射：函数名 → 目标文件
ext_func_target = {}
for fname, fnames in ext_by_file.items():
    for fn in fnames:
        ext_func_target[fn] = fname

# 从 ext_header 里提取 imports（去掉注释和空行前缀）
# 先从原始 header 里取，保留所有 from/import 语句
ext_imports_block = [l for l in ext_header if l.startswith("from ") or l.startswith("import ")]
print(f"ext imports: {len(ext_imports_block)} 行")

# 函数体按目标文件分组收集
ext_content_by_file = {k: [] for k in ext_by_file}
for f in ext_funcs:
    target = ext_func_target.get(f["name"])
    if target is None:
        print(f"  ⚠️ 未分配的函数: {f['name']} — 跳过")
        continue
    # 加 def 行
    block = [ext_lines[f["start"]]] + f["lines"]
    ext_content_by_file[target].append("\n".join(block))

# ---------- 2. 解析 warrant_service.py ----------
main_lines = read_lines(MAIN_PATH)
main_header, main_funcs = split_functions(main_lines)
print(f"warrant_service.py: header {len(main_header)} 行, {len(main_funcs)} 个函数")

# 主表函数（保留在 warrant_service）vs 跨表函数（re-export）
main_only_funcs = {
    "_disp", "_get_or_404", "_get_warrant_with_scope",
    "list_warrants", "_owner_names_map", "_user_names",
    "create", "_add_owners", "update", "delete",
    "batch_storage", "batch_transfer", "batch_cancel",
    "submit_release_out_request", "get_release_out_pending",
    "submit_lend_out_request", "get_lend_out_pending",
    "stats_overview", "stats_by_customer",
}

main_by_file = {
    "warrant_storage_service.py": ["list_storages", "_latest_storages", "_storage_brief", "add_storage", "_apply_state"],
    "warrant_evaluate_service.py": ["list_evaluates", "add_evaluate", "add_recheck", "list_evaluate_companies", "create_evaluate_company", "delete_evaluate_company"],
}
main_func_target = {}
for fname, fnames in main_by_file.items():
    for fn in fnames:
        main_func_target[fn] = fname

main_content_by_file = {k: [] for k in main_by_file}
for f in main_funcs:
    target = main_func_target.get(f["name"])
    if target is None:
        continue  # 保留在主文件
    block = [main_lines[f["start"]]] + f["lines"]
    main_content_by_file[target].append("\n".join(block))

# ---------- 3. 写新 service 文件 ----------
# 公共头部（每个文件需要的 import 各不相同，简单处理：直接放 ext 的 imports + main 的 imports 并集）

all_imports = list(dict.fromkeys(ext_imports_block + [
    l for l in main_header if l.startswith("from ") or l.startswith("import ")
]))

# 各新文件的 import 定制
ownership_imports = '''"""产权人 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantOwnership'''

type_detail_imports = '''"""权证按类型分发的详情 service。

WarrantType 枚举：1=股票/基金 2=车辆 3=动产 4=不动产（按 subtype 分派）
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.enums import WarrantType
from app.warrant.models import (
    Warrant, WarrantStock, WarrantVehicle, WarrantChattel,
    WarrantOther, WarrantPatent, WarrantSoftware, WarrantMortgage,
)'''

real_estate_imports = '''"""不动产类 service（房产/土地/在建工程）。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantHouse, WarrantGround, WarrantConstruction'''

draft_extend_imports = '''"""展期草稿 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantDraftExtend'''

receive_extend_imports = '''"""已接收展期 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.warrant.models import Warrant, WarrantReceiveExtend'''

storage_imports = '''"""权证存储 service。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.user.models import User
from app.warrant.models import Warrant, WarrantStorage'''

evaluate_imports = '''"""权证评估 service + 评估公司字典。"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.exceptions import BizError
from app.user.models import User
from app.warrant.models import (
    Warrant, WarrantEvaluate, WarrantEvaluateRecheck, WarrantEvaluateCompany,
)'''

imports_map = {
    "warrant_ownership_service.py": ownership_imports,
    "warrant_type_detail_service.py": type_detail_imports,
    "warrant_real_estate_service.py": real_estate_imports,
    "warrant_draft_extend_service.py": draft_extend_imports,
    "warrant_receive_extend_service.py": receive_extend_imports,
    "warrant_storage_service.py": storage_imports,
    "warrant_evaluate_service.py": evaluate_imports,
}

for fname, blocks in {**ext_content_by_file, **main_content_by_file}.items():
    if not blocks:
        continue
    content = imports_map[fname] + "\n\n" + "\n\n".join(blocks) + "\n"
    (BASE / fname).write_text(content, encoding="utf-8")
    print(f"  + {fname}: {len(blocks)} 个函数, {len(content.splitlines())} 行")

# ---------- 4. 重写 ext_service.py → 纯 re-export ----------
reexport_lines = [
    '"""ext_service 已按 AGENTS.md §2.2 拆分到独立 service 文件。',
    '',
    '本文件保留作为聚合出口（API 层 25+ 处调用入口不变），',
    '所有函数通过 re-export 暴露。',
    '"""',
    '',
    '# 产权人',
    'from .warrant_ownership_service import (',
    '    list_owners, add_owner, update_owner, delete_owner, _get_owner,',
    ')  # noqa: F401',
    '',
    '# 权证按类型分发详情',
    'from .warrant_type_detail_service import (',
    '    create_ext, get_type_detail, update_type_detail, _add_house, _delete_ext, _get_warrant,',
    ')  # noqa: F401',
    '',
    '# 不动产类',
    'from .warrant_real_estate_service import (',
    '    add_house, delete_house, add_ground, delete_ground,',
    '    add_construction, delete_construction, _ground_dict,',
    ')  # noqa: F401',
    '',
    '# 展期草稿',
    'from .warrant_draft_extend_service import (',
    '    list_draft_extends, add_draft_extend, update_draft_extend,',
    '    delete_draft_extend, _get_draft_extend,',
    ')  # noqa: F401',
    '',
    '# 已接收展期',
    'from .warrant_receive_extend_service import (',
    '    list_receive_extends, add_receive_extend, delete_receive_extend,',
    ')  # noqa: F401',
    '',
]
(EXT_PATH).write_text("\n".join(reexport_lines) + "\n", encoding="utf-8")
print(f"\n✓ ext_service.py → {len(reexport_lines)} 行（re-export）")

# ---------- 5. 重写 warrant_service.py ----------
reexport_main = [
    '# ---------- 子模块 re-export（按 AGENTS.md §2.2 拆分到独立 service）----------',
    'from .warrant_evaluate_service import (',
    '    list_evaluates, add_evaluate, add_recheck,',
    '    list_evaluate_companies, create_evaluate_company, delete_evaluate_company,',
    ')  # noqa: F402,E402',
    'from .warrant_storage_service import (',
    '    list_storages, add_storage,',
    ')  # noqa: F402,E402',
    '',
]

# 收集要保留在主文件的函数块
kept_blocks = []
for f in main_funcs:
    if f["name"] in main_only_funcs:
        block = [main_lines[f["start"]]] + f["lines"]
        kept_blocks.append("\n".join(block))

# 组装新主文件
# 取原始 header（imports + docstring），但去掉末尾那行 "# ============"
kept_header = []
skip = False
for line in main_header:
    if line.startswith("# =="):
        skip = True
    if skip:
        break
    kept_header.append(line)

new_main = "\n".join(kept_header) + "\n\n" + "\n".join(reexport_main) + "\n" + "\n\n".join(kept_blocks) + "\n"
MAIN_PATH.write_text(new_main, encoding="utf-8")
print(f"✓ warrant_service.py → {len(new_main.splitlines())} 行（主表函数 + re-export）")

print("\n拆分完成。验证中...")
