"""ext_service 已按 AGENTS.md §2.2 拆分到独立 service 文件。

本文件保留作为聚合出口（API 层 25+ 处调用入口不变）。
"""

# 产权人
from .warrant_ownership_service import (
    list_owners, add_owner, update_owner, delete_owner, _get_owner, _get_warrant,
)  # noqa: F401

# 权证按类型分发详情
from .warrant_type_detail_service import (
    create_ext, get_type_detail, update_type_detail,
    _add_house, _delete_ext,
)  # noqa: F401

# 不动产类
from .warrant_real_estate_service import (
    add_house, delete_house, add_ground, delete_ground,
    add_construction, delete_construction, _ground_dict,
)  # noqa: F401

# 展期草稿
from .warrant_draft_extend_service import (
    list_draft_extends, add_draft_extend, update_draft_extend,
    delete_draft_extend, _get_draft_extend,
)  # noqa: F401

# 已接收展期
from .warrant_receive_extend_service import (
    list_receive_extends, add_receive_extend, delete_receive_extend,
)  # noqa: F401
