"""机构模块 services 公共助手：枚举 label 转换、主表取数。"""

from sqlalchemy.orm import Session

from app.institution.enums import LABELS
from app.institution.models import Institution


def disp(group: str, value: int | None) -> str | None:
    """枚举值 → 中文 label（组内未定义时回退原值字符串）。"""
    if value is None:
        return None
    return LABELS[group].get(value, str(value))


def get_or_404(db: Session, institution_id: int) -> Institution:
    inst = db.get(Institution, institution_id)
    if inst is None:
        from app.core.exceptions import BizError

        raise BizError(4041, "机构不存在")
    return inst
