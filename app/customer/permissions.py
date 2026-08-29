"""客户模块权限与菜单声明（seed 聚合消费）。"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    ("customer:create", "客户新增（发起创建审批）"),
    ("customer:update", "客户修改（自由字段/敏感修改审批）"),
    ("customer:delete", "客户删除"),
    ("customer:transfer", "批量管护移交（发起移交审批）"),
    ("customer:detail", "客户详情"),
]

MENUS: list[dict] = [
    {
        "caption": "客户管理",
        "path": "/customer",
        "icon": "lucide:users",
        "type": 10,  # 一级目录：模块即目录，模块内页面挂子级
        "children": [
            {
                "caption": "客户列表",
                "path": "/customer/list",
                "component": "custom/index",
                "type": 20,
                "permission_code": "customer:list",
            },
            {
                "caption": "客户标签",
                "path": "/customer/tags",
                "component": "custom/tags",
                "type": 20,
                "permission_code": "customer:list",
            },
        ],
    },
]
