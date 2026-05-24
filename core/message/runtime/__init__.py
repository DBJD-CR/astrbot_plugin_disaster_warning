"""
消息运行时子系统导出入口。

该文件当前主要作为运行时子包初始化文件存在。
后续若需要统一导出浏览器管理、缓存或资源清理相关能力，
可在此处集中整理。
"""

# 从 runtime 暴露核心内部服务
from .bootstrap_service import MessageManagerBootstrapService
from .browser_manager import BrowserManager
from .fusion_state_store import FusionStateStore
from .local_monitor import LocalMonitor
from .remote_media_service import MessageRemoteMediaService
from .resource_cleanup_service import MessageResourceCleanupService
from .runtime_component_factory import MessageRuntimeComponentFactory

__all__ = [
    "MessageManagerBootstrapService",
    "BrowserManager",
    "FusionStateStore",
    "LocalMonitor",
    "MessageRemoteMediaService",
    "MessageResourceCleanupService",
    "MessageRuntimeComponentFactory",
]
