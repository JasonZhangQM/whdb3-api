"""seed：国民经济行业分类（GB/T 4754-2017，含 2019 修订单）。

数据源：atlas-pocket 的 output/industries.csv
格式：code, name, level, parent_code（完整包含门类 A-T + 大类 + 中类 + 小类）

Industry 表字段映射：
  code      ← CSV.code（门类=字母、大类=2位数字、中类=3位、小类=4位）
  name      ← CSV.name
  ind_typ   ← 根据门类推断（10一产 / 20二产 / 30三产）
  parent_id ← 通过 parent_code 回填

幂等：全量清空重建。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.customer.models import Industry  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "industries.csv"

# 门类 code → ind_typ 映射（10=一产, 20=二产, 30=三产）
_SECTOR_IND_TYP: dict[str, int] = {
    "A": 10,  # 农、林、牧、渔业
    "B": 20,  # 采矿业
    "C": 20,  # 制造业
    "D": 20,  # 电力、热力、燃气及水生产和供应业
    "E": 20,  # 建筑业
    "F": 30,  # 批发和零售业
    "G": 30,  # 交通运输、仓储和邮政业
    "H": 30,  # 住宿和餐饮业
    "I": 30,  # 信息传输、软件和信息技术服务业
    "J": 30,  # 金融业
    "K": 30,  # 房地产业
    "L": 30,  # 租赁和商务服务业
    "M": 30,  # 科学研究和技术服务业
    "N": 30,  # 水利、环境和公共设施管理业
    "O": 30,  # 居民服务、修理和其他服务业
    "P": 30,  # 教育
    "Q": 30,  # 卫生和社会工作
    "R": 30,  # 文化、体育和娱乐业
    "S": 30,  # 公共管理、社会保障和社会组织
    "T": 30,  # 国际组织
}


def _infer_ind_typ(code: str, level: str, parent_code: str | None) -> int:
    """根据 code/parent_code 推断 ind_typ：门类直接查，子类从 parent_code 或 code 前缀推断。"""
    if level == "门类":
        return _SECTOR_IND_TYP.get(code, 30)
    # 大类的 parent_code 是门类字母
    if parent_code and parent_code in _SECTOR_IND_TYP:
        return _SECTOR_IND_TYP[parent_code]
    # 兜底：逐级截取 code 前缀直到匹配门类
    for i in range(len(code)):
        prefix = code[: i + 1]
        if prefix in _SECTOR_IND_TYP:
            return _SECTOR_IND_TYP[prefix]
    return 30


def _load_nodes() -> list[dict]:
    """加载 CSV 全部节点并推断 ind_typ。"""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"数据文件不存在：{DATA_PATH}\n"
            f"请先下载：Invoke-WebRequest -Uri "
            f"'https://raw.githubusercontent.com/ldx-person/atlas-pocket/main/output/industries.csv' "
            f"-OutFile '{DATA_PATH}'"
        )
    nodes = []
    with DATA_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = row["code"].strip()
            parent_code = row["parent_code"].strip() or None
            level = row["level"].strip()
            nodes.append({
                "code": code,
                "name": row["name"].strip(),
                "level": level,
                "parent_code": parent_code,
                "ind_typ": _infer_ind_typ(code, level, parent_code),
            })
    return nodes


def seed_industries(db) -> None:
    """幂等 seed：全量清空重建，分批插入并回填 parent_id。"""
    nodes = _load_nodes()
    print(f"解析完成：{len(nodes)} 个节点（门类 → 大类 → 中类 → 小类）")

    # 清空旧数据（外键 customers.industry_id 会被 MySQL 置 NULL）
    db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    db.execute(text("DELETE FROM customer_industries"))
    db.flush()
    db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    db.expire_all()

    # 按层级排序：门类 → 大类 → 中类 → 小类（父先于子）
    level_order = {"门类": 0, "大类": 1, "中类": 2, "小类": 3}
    nodes.sort(key=lambda n: (level_order.get(n["level"], 99), n["code"]))

    # 分批插入
    BATCH = 1000
    code_to_id: dict[str, int] = {}

    for i in range(0, len(nodes), BATCH):
        batch = nodes[i : i + BATCH]
        objs = []
        for n in batch:
            parent_id = 0
            if n["parent_code"] and n["parent_code"] in code_to_id:
                parent_id = code_to_id[n["parent_code"]]
            objs.append(Industry(
                code=n["code"],
                name=n["name"],
                ind_typ=n["ind_typ"],
                parent_id=parent_id,
            ))
        db.add_all(objs)
        db.flush()
        inserted = db.execute(
            select(Industry.code, Industry.id).where(
                Industry.code.in_([o.code for o in objs])
            )
        ).all()
        for row in inserted:
            code_to_id[row.code] = row.id
        print(f"  批次 {i // BATCH + 1}: {len(batch)} 条, code_to_id 累计 {len(code_to_id)}")

    # 第二轮回填 parent_id（有些父节点在后续批次才插入）
    updates = []
    for n in nodes:
        if n["parent_code"] and n["parent_code"] in code_to_id:
            rid = code_to_id[n["code"]]
            correct_parent = code_to_id[n["parent_code"]]
            existing = db.get(Industry, rid)
            if existing and existing.parent_id != correct_parent:
                existing.parent_id = correct_parent
                updates.append(rid)
    if updates:
        db.flush()
        print(f"  回填 parent_id: {len(updates)} 条")

    # 统计
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["level"]] = counts.get(n["level"], 0) + 1
    ind_typ_counts: dict[int, int] = {}
    for n in nodes:
        ind_typ_counts[n["ind_typ"]] = ind_typ_counts.get(n["ind_typ"], 0) + 1
    for lv in ("门类", "大类", "中类", "小类"):
        print(f"  {lv}: {counts.get(lv, 0)} 条")
    print(f"  合计: {sum(counts.values())} 条")
    typ_names = {10: "一产", 20: "二产", 30: "三产"}
    for t in (10, 20, 30):
        print(f"    {typ_names[t]}: {ind_typ_counts.get(t, 0)} 条")


def main() -> None:
    with SessionLocal() as db:
        with db.begin():
            seed_industries(db)
    print("✓ 行业分类 seed 完成")


if __name__ == "__main__":
    main()
