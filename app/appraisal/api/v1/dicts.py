"""评审模块字典接口。

2026-09-21：ExpertCategory 表已删除（迁移 a1b2c3d4e5f6）。
评委类型统一走枚举 expert_type（10 内部 / 20 外部），不需要 DB 字典。
本文件保留空 router 以便后续扩展其他 DB 字典。
"""

from fastapi import APIRouter

router = APIRouter(prefix="/dicts", tags=["appraisal-dict"])
