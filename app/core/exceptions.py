"""业务异常与全局错误码。

错误码分段：
0 成功 | 400x 参数/表单校验失败 | 401x 未认证 | 403x 无权限
404x 资源不存在 | 409x 业务状态冲突 | 500x 服务端异常
"""

from typing import Any


class BizError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# 常用错误码（各模块可按需扩展，保持分段约定）
ERR_PARAM = 4001          # 参数校验失败
ERR_UNAUTHORIZED = 4011   # 未认证 / token 过期
ERR_TOKEN_INVALID = 4012  # token 无效
ERR_FORBIDDEN = 4031      # 无权限
ERR_NOT_FOUND = 4041      # 资源不存在
ERR_CONFLICT = 4091       # 业务状态冲突
ERR_INTERNAL = 5001       # 服务端异常
