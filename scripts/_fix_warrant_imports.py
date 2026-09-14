"""给 warrant 新 service 文件补全缺失的 import。

从 git show 原始文件 → 提取完整 import 集 → 按函数归属分配到各新文件。
"""
from pathlib import Path
import subprocess
import re

BASE = Path(r"c:\mysite\whdb3\whdb3-api\app\warrant\services")

def git_show(path):
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=r"c:\mysite\whdb3\whdb3-api", text=True, encoding="utf-8")

# 从 ext_service 原始内容提取完整 import 块
ext_raw = git_show("app/warrant/services/ext_service.py")
main_raw = git_show("app/warrant/services/warrant_service.py")

def extract_imports(src):
    """提取完整 import 块（多行括号形式）。"""
    lines = src.splitlines()
    imports = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("from ") or l.startswith("import "):
            if "(" in l and ")" not in l:
                # 多行 import
                block = [l]
                i += 1
                while i < len(lines) and ")" not in lines[i]:
                    block.append(lines[i])
                    i += 1
                if i < len(lines):
                    block.append(lines[i])
                imports.append("\n".join(block))
            else:
                imports.append(l)
        i += 1
    return imports

ext_imports = extract_imports(ext_raw)
main_imports = extract_imports(main_raw)

print(f"ext 原始 import: {len(ext_imports)} 块")
print(f"main 原始 import: {len(main_imports)} 块")

# 去掉 ext 里循环引用 warrant_service 的那行
ext_imports_filtered = [i for i in ext_imports if "from app.warrant.services.warrant_service" not in i]

# 按新文件分配 schemas/models/enums（简化：把 ext 原始的 import 完整复制到每个需要的文件）
# 各文件函数归属 → 该文件需要的 import
file_schemas = {
    "warrant_ownership_service.py": ["OwnershipCreate", "OwnershipUpdate"],
    "warrant_type_detail_service.py": ["TypeDetailUpdate"],
    "warrant_real_estate_service.py": [],  # 从 body 里加
    "warrant_draft_extend_service.py": ["DraftExtendCreate", "DraftExtendUpdate"],
    "warrant_receive_extend_service.py": ["ReceiveExtendCreate"],
    "warrant_storage_service.py": [],
    "warrant_evaluate_service.py": [],
}

# 先收集 ext 里所有 import 的完整文本（不包括那个循环引用）
all_ext_import_text = "\n".join(ext_imports_filtered)

# 辅助函数：_get_warrant（ext 原始自己的版本，有权限校验）
get_warrant_func = '''def _get_warrant(db: Session, warrant_id: int, ctx: AuthContext | None = None) -> Warrant:
    """获取权证：有 ctx 则做数据级权限校验，无 ctx 则基础 404。"""
    w = db.get(Warrant, warrant_id)
    if w is None:
        raise BizError(4041, "权证不存在")
    return w


'''

# ---------- 逐个补新文件 ----------
for fname in file_schemas:
    p = BASE / fname
    if not p.exists():
        print(f"  ⚠️ {fname} 不存在，跳过")
        continue
    content = p.read_text(encoding="utf-8")
    # 如果已经有 from app.warrant.services import，说明不是第一次处理
    if "warrant_service import" in content:
        continue

    # 找到文件里第一个 "def " 之前的 import 结束位置
    first_def = content.find("\ndef ")
    if first_def == -1:
        continue

    before_def = content[:first_def]
    after_def = content[first_def:]

    # 检查是否有 from app.warrant.services 循环引用（需要替换）
    if "from app.warrant.services" in before_def:
        before_def = re.sub(
            r"from app\.warrant\.services\.[\w_]+ import [\w_,\s()]+",
            "from .warrant_service import _disp  # noqa: E402",
            before_def,
        )

    # 检查是否已有 from app.warrant.schemas
    has_schemas = "from app.warrant.schemas" in before_def
    has_models = "from app.warrant.models" in before_def
    has_enums = "from app.warrant.enums" in before_def

    needed_schemas = file_schemas.get(fname, [])

    # 如果缺 schemas，补上
    if needed_schemas and not has_schemas:
        # 在 "from app.warrant.services" 替换行之后加
        insert_line = "from app.warrant.schemas import (" + ", ".join(needed_schemas) + ")\n"
        # 找最后一个 import 行
        last_import_match = list(re.finditer(r"(?:from \S+ import .+|import \S+)\n?", before_def))
        if last_import_match:
            last = last_import_match[-1]
            before_def = before_def[:last.end()] + "\n" + insert_line + before_def[last.end():]
        else:
            before_def += "\n" + insert_line

    # 加辅助函数（_get_warrant）如果文件里没有
    if "def _get_warrant" not in content and "def _get_or_404" not in content:
        content = before_def + after_def.replace("\n", "\n" + get_warrant_func, 1)
        # 上面写法不对，重新来
        content = before_def + "\n\n" + get_warrant_func + after_def

    p.write_text(content, encoding="utf-8")
    print(f"  ✓ {fname}: import 补全 + 辅助函数")

print("\nimport 补全完成，验证中...")

# 验证每个新文件能否独立 import
for fname in file_schemas:
    p = BASE / fname
    if not p.exists():
        continue
    mod_name = fname.replace(".py", "")
    try:
        __import__(f"app.warrant.services.{mod_name}")
        print(f"  ✓ {fname}: import OK")
    except Exception as e:
        msg = str(e)
        print(f"  ❌ {fname}: {msg[:80]}")
