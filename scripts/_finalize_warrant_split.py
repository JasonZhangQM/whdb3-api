"""只执行覆盖步骤：ext_service.py → re-export，warrant_service.py → 主表函数 + re-export。

前提：7 个新 service 文件已经存在（由 _split_warrant_services.py 生成）。
"""
from pathlib import Path
import re

BASE = Path(r"c:\mysite\whdb3\whdb3-api\app\warrant\services")

# ---------- 1. ext_service.py → 纯 re-export ----------
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
    '# 权证按类型分发详情（股票/基金/车辆/动产/其他/专利/软件）',
    'from .warrant_type_detail_service import (',
    '    create_ext, get_type_detail, update_type_detail,',
    '    _add_house, _delete_ext, _get_warrant,',
    ')  # noqa: F401',
    '',
    '# 不动产类（房产/土地/在建工程）',
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
(BASE / "ext_service.py").write_text("\n".join(reexport_lines) + "\n", encoding="utf-8")
print(f"✓ ext_service.py → {len(reexport_lines)} 行（re-export）")

# ---------- 2. warrant_service.py → 主表函数 + re-export ----------
# 读入原始 warrant_service.py，按函数名保留主表函数，删除跨表函数
lines = (BASE / "warrant_service.py").read_text(encoding="utf-8").splitlines()

# 定义：主表函数（保留）vs 跨表函数（re-export）
main_only = {
    "_disp", "_get_or_404", "_get_warrant_with_scope",
    "list_warrants", "_owner_names_map", "_user_names",
    "create", "_add_owners", "update", "delete",
    "batch_storage", "batch_transfer", "batch_cancel",
    "submit_release_out_request", "get_release_out_pending",
    "submit_lend_out_request", "get_lend_out_pending",
    "stats_overview", "stats_by_customer",
}
reexport_funcs = {
    # storage 相关
    "list_storages", "_latest_storages", "_storage_brief", "add_storage", "_apply_state",
    # evaluate 相关
    "list_evaluates", "add_evaluate", "add_recheck",
    "list_evaluate_companies", "create_evaluate_company", "delete_evaluate_company",
}

# 切分函数块
def split_funcs(lns):
    funcs = []
    current = None
    header_end = 0
    for i, line in enumerate(lns):
        if re.match(r"^def \w+\(", line):
            if current is None:
                header_end = i
            else:
                current["end"] = i
                funcs.append(current)
            name = re.match(r"^def (\w+)\(", line).group(1)
            current = {"name": name, "start": i, "end": len(lns)}
    if current is not None:
        funcs.append(current)
    return header_end, funcs

header_end, funcs = split_funcs(lines)
print(f"  原始 warrant_service.py: header {header_end} 行, {len(funcs)} 个函数")

# 先找 header 末尾（第一个 "def" 之前，跳过 === 分隔线）
header_lines = lines[:header_end]
# 从 header_lines 里找最后一个 "from " 或 "import " 的位置，后面加 re-export
last_import_idx = 0
for i, l in enumerate(header_lines):
    if l.startswith("from ") or l.startswith("import "):
        last_import_idx = i

reexport_block = [
    '',
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

new_header = header_lines[:last_import_idx+1] + [''] + reexport_block + header_lines[last_import_idx+1:]

# 组装保留的函数块
kept_blocks = []
skipped = []
for f in funcs:
    if f["name"] in main_only:
        block = [lines[f["start"]]] + lines[f["start"]+1:f["end"]]
        kept_blocks.append("\n".join(block))
    elif f["name"] in reexport_funcs:
        skipped.append(f["name"])
    else:
        print(f"  ⚠️ warrant_service 中未分类的函数: {f['name']}")

print(f"  保留 {len(kept_blocks)} 个主表函数, 跳过 {len(skipped)} 个跨表函数 → re-export")
print(f"  跳过的: {skipped}")

new_main = "\n".join(new_header) + "\n\n" + "\n\n".join(kept_blocks) + "\n"
(BASE / "warrant_service.py").write_text(new_main, encoding="utf-8")
print(f"✓ warrant_service.py → {len(new_main.splitlines())} 行（主表函数 + re-export）")

print("\n拆分完成！")
