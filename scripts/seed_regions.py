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

增量策略：
  - 用 INSERT ... ON DUPLICATE KEY UPDATE 按 code upsert
  - 已存在的 code → 更新 name/level/status（保留原 id）
  - 新增的 code → 插入新行
  - 不再删除任何行，不会让已有的客户 region_id 引用失效
  - parent_id 两轮回填：先按层级顺序 upsert 拿到 code→id，再用 UPDATE 语句回填
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.user.models import Region  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent / "regions.json"


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
    """转换为 Region 表格式，推断 parent_code。"""
    nodes: dict[str, dict] = {}
    for r in raw:
        code6 = r["code"]
        name = r["name"]
        town = r.get("town", 0)

        if town and int(town) != 0:
            full_code = f"{code6}{int(town):06d}"
            parent_code = f"{code6}000000"
        else:
            full_code = f"{code6}000000"
            if code6[2:] == "0000":
                parent_code = None
            elif code6[4:] == "00":
                parent_code = f"{code6[:2]}0000000000"
            else:
                parent_code = f"{code6[:4]}00000000"

        level = _calc_level(full_code)
        nodes[full_code] = {
            "code": full_code,
            "name": name,
            "level": level,
            "parent_code": parent_code,
        }

    return list(nodes.values())


def _fix_parent_chain(nodes: list[dict]) -> list[dict]:
    """二次修正 parent_code：如果推断的父级不存在，逐级向上直到找到。"""
    code_set = {n["code"] for n in nodes}
    for n in nodes:
        pc = n["parent_code"]
        while pc is not None and pc not in code_set:
            if pc[4:] == "00000000":
                pc = pc[:2] + "0000000000"
            elif pc[6:] == "000000":
                pc = pc[:4] + "00000000"
            else:
                pc = pc[:6] + "000000"
        n["parent_code"] = pc
    return nodes


def seed_regions(db) -> None:
    """增量 seed：ON DUPLICATE KEY UPDATE upsert，不删旧行。"""
    raw = _load_data()
    nodes = _transform(raw)
    nodes = _fix_parent_chain(nodes)
    print(f"解析 {len(raw)} 条原始数据 → {len(nodes)} 个节点")

    # 按层级排序：省 → 市 → 区县 → 乡镇街道（确保父先于子）
    nodes.sort(key=lambda n: (n["level"], n["code"]))

    # ---- 第一轮：纯 upsert，parent_id 先填 0（后面回填） ----
    # 用原生 SQL，一条 INSERT 就能处理多行 + ON DUPLICATE KEY UPDATE
    BATCH = 5000
    upsert_sql = text("""
        INSERT INTO user_regions (code, name, level, parent_id, ordery, status)
        VALUES (:code, :name, :level, 0, 0, 10)
        ON DUPLICATE KEY UPDATE
            name   = VALUES(name),
            level  = VALUES(level),
            status = VALUES(status)
    """)

    total_affected = 0
    for i in range(0, len(nodes), BATCH):
        batch = nodes[i:i + BATCH]
        db.execute(upsert_sql, batch)
        total_affected += len(batch)
        print(f"  upsert 批次 {i//BATCH+1}: {len(batch)} 条 (累计 {total_affected})")
    db.flush()

    # ---- 查出现有 code→id 映射 ----
    all_codes = [n["code"] for n in nodes]
    code_to_id: dict[str, int] = dict(
        db.execute(
            select(Region.code, Region.id).where(Region.code.in_(all_codes))
        ).all()
    )

    # ---- 第二轮：批量回填 parent_id ----
    # 只更新那些 parent_code 能在 code_to_id 里找到的行
    updates: list[dict] = []
    for n in nodes:
        if n["parent_code"] and n["parent_code"] in code_to_id:
            updates.append({
                "code": n["code"],
                "parent_id": code_to_id[n["parent_code"]],
            })

    if updates:
        # MySQL 用 JOIN UPDATE 一次搞定
        parent_ids_sql = text("""
            UPDATE user_regions r
            JOIN (SELECT :code AS code, :parent_id AS parent_id) AS v ON r.code = v.code
            SET r.parent_id = v.parent_id
        """)
        # 分批（MySQL 单条 UPDATE 用 CASE WHEN 也可以，但逐条更稳）
        BATCH_U = 2000
        for i in range(0, len(updates), BATCH_U):
            db.execute(parent_ids_sql, updates[i:i + BATCH_U])
        db.flush()
        print(f"  回填 parent_id: {len(updates)} 条")

    # ---- 统计 ----
    counts: dict[int, int] = {}
    for n in nodes:
        counts[n["level"]] = counts.get(n["level"], 0) + 1
    level_names = {10: "省", 20: "市", 30: "区县", 40: "乡镇街道"}
    total = sum(counts.values())
    for lv in (10, 20, 30, 40):
        print(f"  {level_names.get(lv, lv)}: {counts.get(lv, 0)} 条")
    print(f"  合计: {total} 条")

    # 比一下数据库实际总行数，确认是增量（不是替换）
    actual_total = db.execute(text("SELECT COUNT(*) FROM user_regions")).scalar()
    print(f"  数据库实际总行数: {actual_total} 条")
    if actual_total > total:
        print(f"  ⚠ 数据库比 json 多 {actual_total - total} 条（可能是历史遗留的已停用区域，未被 json 覆盖）")


def main() -> None:
    with SessionLocal() as db:
        with db.begin():
            seed_regions(db)
    print("✓ 行政区划 seed 完成（增量 upsert，未清空）")


if __name__ == "__main__":
    main()
