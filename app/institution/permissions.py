"""机构模块权限与菜单声明（seed 聚合消费）。"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    ("institution:create", "机构新增"),
    ("institution:update", "机构修改"),
    ("institution:delete", "机构删除"),
    ("institution:detail", "机构详情"),
]

MENUS: list[dict] = [
    {
        "caption": "基础数据",
        "path": "/basic",
        "icon": "lucide:database",
        "type": 10,  # 目录
        "children": [
            {
                "caption": "机构管理",
                "path": "/basic/institutions",
                "component": "institution/index",
                "type": 20,
                "permission_code": "institution:list",
            },
        ],
    },
]
