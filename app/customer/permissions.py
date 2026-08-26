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
        "caption": "基础数据",
        "path": "/basic",
        "icon": "lucide:database",
        "type": 10,  # 目录（与机构/权证模块共同聚合，seed 按 path 幂等）
        "children": [
            {
                "caption": "客户管理",
                "path": "/basic/customers",
                "component": "custom/index",
                "type": 20,
                "permission_code": "customer:list",
            },
        ],
    },
]
