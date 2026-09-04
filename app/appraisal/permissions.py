"""评审模块权限与菜单声明（seed 聚合消费）。

M3a 新增：6 个操作权限码 + 菜单树。
"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    # 评审会管理
    ("appraisal:create", "评审会新建"),
    ("appraisal:update", "评审会修改"),
    ("appraisal:delete", "评审会删除"),
    ("appraisal:finish", "评审会完成（含状态联动）"),
    # 专家库管理
    ("appraisal:expert_create", "专家新增"),
    ("appraisal:expert_update", "专家修改"),
    ("appraisal:expert_delete", "专家删除"),
]

MENUS: list[dict] = [
    {
        "caption": "评审管理",
        "path": "/appraisal",
        "icon": "lucide:users-round",
        "type": 10,  # 一级目录
        "children": [
            {
                "caption": "评审会列表",
                "path": "/appraisal/list",
                "component": "appraisal/index",
                "type": 20,
                "permission_code": "appraisal:list",
            },
            {
                "caption": "专家库",
                "path": "/appraisal/experts",
                "component": "appraisal/experts",
                "type": 20,
                "permission_code": "appraisal:expert_list",
            },
        ],
    },
]
