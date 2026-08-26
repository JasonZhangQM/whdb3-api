"""权证模块权限与菜单声明（seed 聚合消费）。"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    ("warrant:create", "权证新增"),
    ("warrant:update", "权证修改（评估/明细/所有权人）"),
    ("warrant:delete", "权证删除"),
    ("warrant:storage", "权证出入库（含批量/移交）"),
    ("warrant:detail", "权证详情"),
]

MENUS: list[dict] = [
    {
        "caption": "基础数据",
        "path": "/basic",
        "icon": "lucide:database",
        "type": 10,  # 目录（与机构/客户模块共同聚合，seed 按 path 幂等）
        "children": [
            {
                "caption": "权证管理",
                "path": "/basic/warrants",
                "component": "warrant/index",
                "type": 20,
                "permission_code": "warrant:list",
            },
        ],
    },
    {
        "caption": "审批中心",
        "path": "/approval",
        "icon": "lucide:file-check",
        "type": 10,  # 目录（登录即可见，无权限码）
        "children": [
            {
                "caption": "我的申请",
                "path": "/approval/my-submitted",
                "component": "approval/my-submitted/index",
                "type": 20,
            },
            {
                "caption": "待我审批",
                "path": "/approval/my-tasks",
                "component": "approval/my-tasks/index",
                "type": 20,
            },
        ],
    },
]
