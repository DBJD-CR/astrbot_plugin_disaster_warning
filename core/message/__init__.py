"""
消息子系统导出入口。

该文件当前不承载具体业务逻辑，
主要用于统一导出高层消息推送总管理器与记录器。
"""

from .message_logger import MessageLogger, get_message_logger
from .message_manager import MessagePushManager

__all__ = [
    "MessageLogger",
    "get_message_logger",
    "MessagePushManager",
]
