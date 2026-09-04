"""统一字典接口：GET /api/v1/dicts 聚合各模块枚举，前端三值分离的真相源。

返回格式：
{
  "code": 0,
  "data": {
    "customer.classification": [{"value": 10, "label": "正常"}, {"value": 20, "label": "关注"}, ...],
    "warrant.warrant_type": [{"value": 1, "label": "房产"}, ...],
    "approval.instance_status": [{"value": 10, "label": "审批中"}, ...],
    ...
  }
}
"""

from fastapi import APIRouter

from app.core.response import ok

router = APIRouter(tags=["dict"])


# ============ 模块注册（按业务层枚举逐个登记） ============
# 每个模块 import 本枚举的 LABELS，统一加上模块前缀防 key 冲突。
# 新增模块的枚举时在下面追加一行即可。

from app.appraisal.enums import LABELS as appraisal_labels  # noqa: E402
from app.approval.enums import LABELS as approval_labels  # noqa: E402
from app.article.enums import LABELS as article_labels  # noqa: E402
from app.customer.enums import LABELS as customer_labels  # noqa: E402
from app.institution.enums import LABELS as institution_labels  # noqa: E402
from app.user.enums import LABELS as user_labels  # noqa: E402
from app.warrant.enums import LABELS as warrant_labels  # noqa: E402


def _flatten() -> dict[str, list[dict]]:
    """把各模块 LABELS 扁平化成 { 模块前缀.key: [{value, label}, ...] }。"""
    merged: dict[str, list[dict]] = {}

    module_labels: list[tuple[str, dict[str, dict[int, str]]]] = [
        ("customer", customer_labels),
        ("warrant", warrant_labels),
        ("institution", institution_labels),
        ("approval", approval_labels),
        ("user", user_labels),
        ("article", article_labels),
        ("appraisal", appraisal_labels),
    ]

    for module_name, labels in module_labels:
        for key, mapping in labels.items():
            full_key = f"{module_name}.{key}"
            merged[full_key] = [
                {"value": v, "label": label} for v, label in mapping.items()
            ]

    return merged


# 模块枚举在服务启动时 import 一次，返回值可做进程内缓存（枚举不会运行时变动）
_ALL_DICTS = _flatten()


@router.get("/dicts")
def get_all_dicts() -> dict:
    """返回所有枚举字典。前端启动时拉取一次，Pinia 全局缓存。"""
    return ok(_ALL_DICTS)


@router.get("/dicts/{name}")
def get_dict(name: str) -> dict:
    """按 key 查单个字典（用于按需懒加载场景）。"""
    data = _ALL_DICTS.get(name, [])
    return ok(data)
