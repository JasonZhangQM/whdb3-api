"""客户模块审批 executors：向 approval 引擎注册 flow_code 生效函数（R4 依赖反转）。

approval 引擎在末节点同意的事务内回调 executor，实现"实例置通过 + 业务生效"原子完成。
"""

from app.approval.services import register_executor
from app.customer.services import customer_service

# 三个 flow：创建（完整草稿落库）/ 敏感修改（diff 应用）/ 批量移交（一条 UPDATE）
register_executor("customer_create", customer_service.apply_create)
register_executor("customer_update", customer_service.apply_change)
register_executor("customer_transfer", customer_service.apply_transfer)
