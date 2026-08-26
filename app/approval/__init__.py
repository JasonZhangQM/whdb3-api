"""通用审批引擎模块。

四张表：流程定义 / 流程节点 / 审批实例 / 审批任务。
executor 注册表实现依赖反转：approval 永不 import 业务模块，
各业务模块 services/executors.py 启动时注册（R4 规则）。
"""
