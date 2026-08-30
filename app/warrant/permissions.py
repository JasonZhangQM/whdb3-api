"""权证模块权限与菜单声明（seed 聚合消费）。"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    ("warrant:list", "权证列表查看"),
    ("warrant:create", "权证新增"),
    ("warrant:update", "权证修改（评估/明细/所有权人）"),
    ("warrant:delete", "权证删除"),
    ("warrant:storage", "权证出入库（含批量/移交）"),
    ("warrant:detail", "权证详情"),
]

MENUS: list[dict] = [
    {
        "caption": "权证管理",
        "path": "/warrant",
        "icon": "lucide:file-badge",
        "type": 10,  # 一级目录：模块即目录，模块内页面挂子级
        "children": [
            {
                "caption": "权证列表",
                "path": "/warrant/list",
                "component": "warrant/index",
                "type": 20,
                "permission_code": "warrant:list",
            },
        ],
    },
    # 审批中心菜单由 app/approval/permissions.py 单一来源声明（单页面结构）。
]
