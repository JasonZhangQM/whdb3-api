"""客户模块服务层。

import 本包即触发 executors 注册（审批引擎 R4 依赖反转）。
"""

from app.customer.services import (  # noqa: F401
    credit_region_service,
    customer_service,
    group_service,
    region_service,
)
