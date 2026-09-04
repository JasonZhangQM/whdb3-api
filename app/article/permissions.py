"""项目模块权限与菜单声明（seed 聚合消费）。

M3a 新增：11 个操作权限码 + 菜单树。
"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    # 主管理
    ("article:create", "项目新增"),
    ("article:update", "项目修改"),
    ("article:delete", "项目删除"),
    ("article:detail", "项目详情"),
    # 子资源管理（状态流转 / 业务操作）
    ("article:feedback", "风控反馈提交"),
    ("article:quota", "单项额度设置"),
    ("article:lending", "放款次序管理"),
    ("article:sure", "反担保措施管理"),
    # 审批
    ("article:sign", "发起签批审批"),
    ("article:change", "发起变更审批"),
]

MENUS: list[dict] = [
    {
        "caption": "项目管理",
        "path": "/article",
        "icon": "lucide:folder-archive",
        "type": 10,  # 一级目录；模块内页面挂子级
        "children": [
            {
                "caption": "项目列表",
                "path": "/article/list",
                "component": "article/index",
                "type": 20,
                "permission_code": "article:list",
            },
        ],
    },
]
