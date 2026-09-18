"""评审模块权限与菜单声明（seed 聚合消费）。

权限码规范：资源:操作（AGENTS.md §5.2）。
- appraisal:list / appraisal:expert_list 已在 seed.py 内置角色权限表声明
- 补调完成(resolve)、纪要编辑(summary)、意见录入(comment)复用已建码
"""

ACTION_PERMISSIONS: list[tuple[str, str]] = [
    # 评审会（7 个）
    ("appraisal:list", "评审会列表"),
    ("appraisal:read", "评审会详情查看"),
    ("appraisal:create", "评审会新建"),
    ("appraisal:update", "评审会修改（排会/移出/纪要编辑）"),
    ("appraisal:delete", "评审会删除"),
    ("appraisal:finish", "评审会完成（含状态联动）"),
    ("appraisal:comment", "评委意见录入"),
    # 补调（1 个）
    ("appraisal:supply_resolve", "补调完成登记"),
    # 专家库（4 个）
    ("appraisal:expert_list", "专家库列表"),
    ("appraisal:expert_create", "专家新增"),
    ("appraisal:expert_update", "专家修改"),
    ("appraisal:expert_delete", "专家删除（含软删停用）"),
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
