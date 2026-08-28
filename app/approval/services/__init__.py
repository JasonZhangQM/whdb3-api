"""审批服务聚合出口：引擎写链路 + 查询读链路拆分，此处仅 re-export。

路由层统一 `from app.approval import services as svc` 后调 `svc.xxx`；
业务模块 executor 注册用 `from app.approval.services import register_executor`。
"""

from app.approval.services.engine_service import (  # noqa: F401
    APPLY_EXECUTORS,
    act,
    register_executor,
    submit,
    withdraw,
)
from app.approval.services.query_service import (  # noqa: F401
    get_instance_detail,
    has_pending_instance,
    list_my_submitted,
    list_my_tasks,
)
