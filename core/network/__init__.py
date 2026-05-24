"""
network 子系统导出。
统一收口 source 消息路由与网络基础设施的公共入口。
"""

# 从数据源消息路由器模块导入核心组件
from .source_message_router import SourceMessageRouter

# 声明对外公开的模块成员列表
__all__ = ["SourceMessageRouter"]
