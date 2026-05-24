"""
灾害预警插件命令与生命周期控制子包。
包含插件的生命周期事件挂钩（运行时配置修正、后台遥测上报等）以及前台多媒体交互命令的集中导出。
"""

from .plugin_command_support_service import PluginCommandSupportService
from .plugin_lifecycle_service import PluginLifecycleService

__all__ = [
    "PluginCommandSupportService",
    "PluginLifecycleService",
]
