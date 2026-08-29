"""预置客户标签（行业标签 + 业务标签）。

常见标签覆盖：专精特新资质、高新技术企业、行业分类、企业规模、风险特征等。
设计原则：不追求全量，提供 20-30 条高频使用的预置值，业务方可在标签管理页面自行增删。

幂等：按 name 查重，已存在则跳过。
"""

# 先导入全部模型，让 Base.metadata 注册所有表（SQLAlchemy 排 FK 依赖需要）
import app.customer.models  # noqa: F401
import app.user.models  # noqa: F401

from app.core.db import SessionLocal
from app.customer.models import ExtraTag

# type=10 行业标签（业务方常按"行业特色"打标签，与国民经济行业分类互补）
INDUSTRY_TAGS = [
    "专精特新",
    "高新技术企业",
    "小巨人企业",
    "瞪羚企业",
    "独角兽企业",
    "农业龙头",
    "制造业单项冠军",
    "文化创意",
    "生物医药",
    "新能源",
    "新材料",
    "高端装备",
]

# type=20 业务标签（担保业务维度的客户画像）
BIZ_TAGS = [
    "小微企业",
    "个体工商户",
    "房地产相关",
    "地方平台",
    "国企",
    "民营企业",
    "外资背景",
    "上市公司",
    "涉诉",
    "关注类",
    "存量客户",
    "新增客户",
    "首贷客户",
    "续贷客户",
    "大额担保",
    "小额担保",
]

ADMIN_USER_ID = 1


def seed_tags() -> None:
    db = SessionLocal()
    try:
        existing = {name for (name,) in db.query(ExtraTag.name).all()}
        to_create: list[ExtraTag] = []
        for name in INDUSTRY_TAGS:
            if name not in existing:
                to_create.append(ExtraTag(
                    name=name, type=10, status=10, created_by=ADMIN_USER_ID,
                ))
        for name in BIZ_TAGS:
            if name not in existing:
                to_create.append(ExtraTag(
                    name=name, type=20, status=10, created_by=ADMIN_USER_ID,
                ))
        if to_create:
            db.add_all(to_create)
            db.commit()
            print(f"[seed_tags] 新增 {len(to_create)} 条预置标签（行业 {sum(1 for t in to_create if t.type == 10)} + 业务 {sum(1 for t in to_create if t.type == 20)}）")
        else:
            print("[seed_tags] 预置标签已全部存在，跳过")
        total = db.query(ExtraTag).count()
        print(f"[seed_tags] 总计 {total} 条标签")
    finally:
        db.close()


if __name__ == "__main__":
    seed_tags()
