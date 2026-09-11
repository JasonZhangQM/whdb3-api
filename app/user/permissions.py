"""用户模块权限与菜单声明（详设裁决 11：各模块自带 permissions.py，seed 聚合消费）。

权限 code 约定 `资源:操作`；菜单可见性由权限码单通道推导（不建 role_menus）。
"""

# 操作权限（type=20）。菜单权限（type=10）由 MENUS 树自动生成并挂 menu_id。
ACTION_PERMISSIONS: list[tuple[str, str]] = [
    # 用户
    ("user:create", "用户新增"),
    ("user:update", "用户修改"),
    ("user:delete", "用户删除"),
    ("user:export", "用户导出"),
    ("user:reset_pwd", "重置密码"),
    ("user:assign_role", "分配用户角色"),
    ("user:transfer", "业务移交"),
    # 部门
    ("user:dept_create", "部门新增"),
    ("user:dept_update", "部门修改"),
    ("user:dept_delete", "部门删除"),
    # 角色
    ("user:role_create", "角色新增"),
    ("user:role_update", "角色修改"),
    ("user:role_delete", "角色删除"),
    ("user:role_assign", "角色权限分配"),
    # 菜单
    ("user:menu_create", "菜单新增"),
    ("user:menu_update", "菜单修改"),
    ("user:menu_delete", "菜单删除"),
]

# 菜单树：permission_code 即 type=10 菜单权限（seed 自动建权限记录并回挂 menu_id）
MENUS: list[dict] = [
    {
        "caption": "工作台",
        "path": "/dashboard",
        "redirect": "/dashboard/workspace",
        "icon": "lucide:home",
        "type": 10,  # 目录（无权限码：全员可见，登录落地页）
        "children": [
            {"caption": "工作台", "path": "/dashboard/workspace", "component": "dashboard/workspace/index", "type": 20},
        ],
    },
    {
        "caption": "系统管理",
        "path": "/system",
        "icon": "lucide:settings",
        "type": 10,  # 目录
        "children": [
            {"caption": "用户管理", "path": "/system/users", "component": "system/user/index", "type": 20, "permission_code": "user:list"},
            {"caption": "部门管理", "path": "/system/departments", "component": "system/dept/index", "type": 20, "permission_code": "user:dept_list"},
            {"caption": "角色管理", "path": "/system/roles", "component": "system/role/index", "type": 20, "permission_code": "user:role_list"},
            {"caption": "菜单管理", "path": "/system/menus", "component": "system/menu/index", "type": 20, "permission_code": "user:menu_list"},
            {"caption": "行政区划", "path": "/system/regions", "component": "system/region/index", "type": 20, "permission_code": "user:region_list"},
            {"caption": "操作日志", "path": "/system/operation-logs", "component": "system/log/operation", "type": 20, "permission_code": "user:log_operation"},
            {"caption": "登录日志", "path": "/system/login-logs", "component": "system/log/login", "type": 20, "permission_code": "user:log_login"},
        ],
    },
]

# 内置角色（总体方案 §5.2；super_admin 由 seed 创建且不可经界面增删）
BUILTIN_ROLES: list[dict] = [
    {"code": "super_admin", "name": "超级管理员", "data_scope": 40, "description": "全部数据，系统内置"},
    # 业务岗位（data_scope=10：本人；20：本部门；30：本部门及下级；40：全部）
    {"code": "pm", "name": "项目经理", "data_scope": 10, "description": "本人"},
    {"code": "controler", "name": "风控岗", "data_scope": 10, "description": "本人"},
    {"code": "lawyer", "name": "法务岗", "data_scope": 10, "description": "本人"},
    {"code": "recovery_specialist", "name": "追偿岗", "data_scope": 10, "description": "本人"},
    # 部门岗位
    {"code": "dept_manager", "name": "业务部负责人", "data_scope": 30, "description": "本部门及下级"},
    # 后台岗位
    {"code": "risk_leader", "name": "风控法务部负责人", "data_scope": 40, "description": "全部"},
    {"code": "committee_secretary", "name": "审保会秘书", "data_scope": 40, "description": "全部"},
    {"code": "warrant_manager", "name": "权证管理岗", "data_scope": 40, "description": "全部"},
    {"code": "records_manager", "name": "档案管理岗", "data_scope": 40, "description": "全部"},
    {"code": "accounting_specialist", "name": "会计岗", "data_scope": 40, "description": "全部"},
    # 管理层
    {"code": "business_manager", "name": "分管业务副总经理", "data_scope": 40, "description": "全部"},
    {"code": "risk_manager", "name": "分管风控副总经理", "data_scope": 40, "description": "全部"},
    {"code": "general_manager", "name": "总经理", "data_scope": 40, "description": "全部"},
    {"code": "board_chairman", "name": "董事长", "data_scope": 40, "description": "全部"},
    # 只读岗位
    {"code": "auditor", "name": "审计", "data_scope": 40, "description": "全部只读"},
    {"code": "reader", "name": "只读", "data_scope": 20, "description": "本部门只读"},
]
