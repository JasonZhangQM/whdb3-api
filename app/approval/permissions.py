"""审批模块权限与菜单声明（seed 聚合消费）。

审批中心对全员开放：待办按审批人解析过滤，无需权限码（任务列表天然隔离）。
"""

ACTION_PERMISSIONS: list[tuple[str, str]] = []

MENUS: list[dict] = [
    {
        "caption": "审批中心",
        "path": "/approval",
        "icon": "lucide:file-check",
        "type": 20,  # 顶级页面（无 permission_code：全员可见）
        "component": "approval/index",
    },
]
