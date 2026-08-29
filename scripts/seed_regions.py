"""seed：国标行政区划（省/市/区县/乡镇街道，共约 4.5 万条）。

数据源：uiwjs/province-city-china 的 data.json（2024 年版）
格式：{code, name, province, city, area, town}
  - 省：code=xx0000, province=xx, city=area=town=0
  - 市：code=xxxx00, province=xx, city=xx, area=town=0
  - 区县：code=xxxxxx, province=xx, city=xx, area=xx, town=0
  - 乡镇街道：code=区县code, town=xxxxxx, 完整 code = code + town

Region 表 level 映射：
  10 = 省（直辖市也归此类）
  20 = 市（地级市/自治州/盟，含直辖市的区县级"市"概念）
  30 = 区县（市辖区/县级市/县/自治县/旗）
  40 = 乡镇街道（街道/镇/乡/民族乡）

幂等：按 code upsert，先全量清空再重建。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.customer.models import Region  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "regions.json"

# code 长度 → level（国标：省 2 位 + 4 零 = 6 位完整码）
# 但数据源里省的 code 是 xx0000（6 位），市是 xxxx00，区县是 xxxxxx
# 乡镇街道在数据源里 code=区县6位 + town=6位，完整 12 位

def _calc_level(code_12: str) -> int:
    """根据完整 12 位 code 推断 level。"""
    if code_12[2:] == "0000000000":  # xx + 10 个 0 → 省
        return 10
    if code_12[4:] == "00000000":    # xxxx + 8 个 0 → 市
        return 20
    if code_12[6:] == "000000":      # xxxxxx + 6 个 0 → 区县
        return 30
    return 40                         # 否则 → 乡镇街道


def _load_data() -> list[dict]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"数据文件不存在：{DATA_PATH}\n"
            f"请先下载：node -e \"const fs=require('fs');fetch('https://raw.githubusercontent.com/uiwjs/province-city-china/master/packages/core/dist/data.json').then(r=>r.text()).then(t=>fs.writeFileSync('scripts/regions.json',t))\""
        )
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return raw


def _transform(raw: list[dict]) -> list[dict]:
    """转换为 Region 表格式，推断 parent_id。"""
    # 先按完整 code 组装节点
    nodes: dict[str, dict] = {}
    for r in raw:
        code6 = r["code"]
        name = r["name"]
        town = r.get("town", 0)

        if town and int(town) != 0:
            # 乡镇街道：完整 code = 区县 6 位 + town 6 位 = 12 位
            full_code = f"{code6}{int(town):06d}"
            parent_code = f"{code6}000000"  # 父级区县的 12 位 full_code
        else:
            full_code = f"{code6}000000"  # 补 6 个 0 → 12 位
            if code6[2:] == "0000":       # 省
                parent_code = None
            elif code6[4:] == "00":       # 市
                parent_code = f"{code6[:2]}0000000000"
            else:                          # 区县
                # 先尝试找"市"这一级（如 330105 → 330100 杭州市）
                parent_code = f"{code6[:4]}00000000"
                # 如果数据源里没有这个"市"（直辖市/省直管县没有市这一级），
                # 则向上跳一级直接挂省（如 110101 东城区 → 110000 北京市）
                candidate_province = f"{code6[:2]}0000000000"
                # 先记 parent_code，后面回填时如果找不到就再修正
                # 这里先存候选，等第一轮回填后用实际存在性来最终决定

        level = _calc_level(full_code)
        nodes[full_code] = {
            "code": full_code,
            "name": name,
            "level": level,
            "parent_code": parent_code,
        }

    # parent_code → parent_id 映射（先查库，没有就用临时占位）
    return list(nodes.values())


def _fix_parent_chain(nodes: list[dict]) -> list[dict]:
    """二次修正 parent_code：如果推断的父级不存在，逐级向上直到找到。

    典型场景：直辖市（北京/上海/天津/重庆）数据源里没有"市"这一级，
    区县 110101 的父级应该是省 110000 而不是不存在的 110100000000。
    """
    code_set = {n["code"] for n in nodes}
    for n in nodes:
        pc = n["parent_code"]
        # 逐级向上：12 位 code → 缩到 8 位（市）→ 缩到 2 位（省）→ None
        while pc is not None and pc not in code_set:
            if pc[4:] == "00000000":       # 市不存在 → 跳省
                pc = pc[:2] + "0000000000"
            elif pc[6:] == "000000":       # 区县不存在 → 跳市
                pc = pc[:4] + "00000000"
            else:                           # 乡镇不存在 → 跳区县
                pc = pc[:6] + "000000"
        n["parent_code"] = pc
    return nodes


def seed_regions(db) -> dict[str, int]:
    """幂等 seed：全量清空重建，返回 code → id 映射。"""
    raw = _load_data()
    nodes = _transform(raw)
    nodes = _fix_parent_chain(nodes)  # 修正直辖市等缺失中间层级的 parent_code
    print(f"解析 {len(raw)} 条原始数据 → {len(nodes)} 个节点")

    # 清空旧数据（物理外键 customers.region_id → customer_regions.id，
    # 临时关闭外键检查；客户 region_id 会被 MySQL 自动置 NULL）
    db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    db.query(Region).delete(synchronize_session=False)
    db.flush()
    db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    # 分批插入（4.5 万条，每批 5000）
    BATCH = 5000
    code_to_id: dict[str, int] = {}

    # 按层级排序：省 → 市 → 区县 → 乡镇街道（确保父先于子）
    nodes.sort(key=lambda n: (n["level"], n["code"]))

    for i in range(0, len(nodes), BATCH):
        batch = nodes[i:i + BATCH]
        objs = []
        for n in batch:
            parent_id = None
            if n["parent_code"] and n["parent_code"] in code_to_id:
                parent_id = code_to_id[n["parent_code"]]
            objs.append(Region(
                code=n["code"],
                name=n["name"],
                level=n["level"],
                parent_id=parent_id or 0,
                status=10,
            ))
        db.add_all(objs)
        db.flush()
        # 回填 code→id（通过查询刚插入的批次）
        inserted = db.execute(
            select(Region.code, Region.id).where(
                Region.code.in_([o.code for o in objs])
            )
        ).all()
        for row in inserted:
            code_to_id[row.code] = row.id
        print(f"  批次 {i//BATCH+1}: {len(batch)} 条, code_to_id 累计 {len(code_to_id)}")

    # 第二轮回填 parent_id（有些父节点在后续批次才插入，需要补）
    updates = []
    for n in nodes:
        if n["parent_code"] and n["parent_code"] in code_to_id:
            rid = code_to_id[n["code"]]
            parent_id = code_to_id[n["parent_code"]]
            existing = db.get(Region, rid)
            if existing and existing.parent_id != parent_id:
                existing.parent_id = parent_id
                updates.append(rid)
    if updates:
        db.flush()
        print(f"  回填 parent_id: {len(updates)} 条")

    # 统计
    counts: dict[int, int] = {}
    for n in nodes:
        counts[n["level"]] = counts.get(n["level"], 0) + 1
    level_names = {10: "省", 20: "市", 30: "区县", 40: "乡镇街道"}
    total = sum(counts.values())
    for lv in (10, 20, 30, 40):
        print(f"  {level_names.get(lv, lv)}: {counts.get(lv, 0)} 条")
    print(f"  合计: {total} 条")
    return code_to_id


def main() -> None:
    with SessionLocal() as db:
        with db.begin():
            seed_regions(db)
    print("✓ 行政区划 seed 完成")


if __name__ == "__main__":
    main()
