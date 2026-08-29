"""用户模块权限与菜单声明（详设裁决 11：各模块自带 permissions.py，seed 聚合消费）。

权限 code 约定 `资源:操作`；菜单可见性由权限码单通道推导（不建 role_menus）。
"""

# 操作权限（type=20）。菜单权限（type=10）由 MENUS 树自动生成并挂 menu_id。
ACTION_PERMISSIONS: list[tuple[str, str]] = [
    ("user:create", "用户新增"),
    ("user:update", "用户修改"),
    ("user:delete", "用户删除"),
    ("user:export", "用户导出"),
    ("user:reset_pwd", "重置密码"),
    ("user:assign_role", "分配用户角色"),
    ("user:transfer", "业务移交"),
    ("dept:create", "部门新增"),
    ("dept:update", "部门修改"),
    ("dept:delete", "部门删除"),
    ("role:create", "角色新增"),
    ("role:update", "角色修改"),
    ("role:delete", "角色删除"),
    ("role:assign", "角色权限分配"),
    ("menu:create", "菜单新增"),
    ("menu:update", "菜单修改"),
    ("menu:delete", "菜单删除"),
    ("region:list", "行政区划查看"),
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
            {"caption": "部门管理", "path": "/system/departments", "component": "system/dept/index", "type": 20, "permission_code": "dept:list"},
            {"caption": "角色管理", "path": "/system/roles", "component": "system/role/index", "type": 20, "permission_code": "role:list"},
            {"caption": "菜单管理", "path": "/system/menus", "component": "system/menu/index", "type": 20, "permission_code": "menu:list"},
            {"caption": "行政区划", "path": "/system/regions", "component": "system/region/index", "type": 20, "permission_code": "region:list"},
            {"caption": "操作日志", "path": "/system/operation-logs", "component": "system/log/operation", "type": 20, "permission_code": "log:operation"},
            {"caption": "登录日志", "path": "/system/login-logs", "component": "system/log/login", "type": 20, "permission_code": "log:login"},
        ],
    },
]

# 内置角色（总体方案 §5.2；super_admin 由 seed 创建且不可经界面增删）
BUILTIN_ROLES: list[dict] = [
    {"code": "super_admin", "name": "超级管理员", "data_scope": 40, "description": "全部数据，系统内置"},
    {"code": "dept_manager", "name": "部门负责人", "data_scope": 30, "description": "本部门及下级"},
    {"code": "controler", "name": "风控专员", "data_scope": 10, "description": "本人"},
    {"code": "pm", "name": "项目经理", "data_scope": 10, "description": "本人"},
    {"code": "auditor", "name": "审计", "data_scope": 40, "description": "全部只读"},
    {"code": "reader", "name": "只读", "data_scope": 20, "description": "本部门只读"},
]
