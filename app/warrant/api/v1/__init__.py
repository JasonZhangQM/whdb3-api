"""权证模块路由聚合：M2 范围 37 接口（字典 9 + 主管理 7 + 所有权人 4 + 出入库 2 + 评估 3 + 票据明细 4 + 应收明细 3 + 批量 3 + 统计 2）。

他权 3 接口与项目绑定 4 接口依赖 agrees/articles 表（M3 合同/项目模块），届时补挂。
"""

from fastapi import APIRouter

from app.warrant.api.v1 import dicts, warrants

router = APIRouter()
router.include_router(dicts.router)
router.include_router(warrants.router)
