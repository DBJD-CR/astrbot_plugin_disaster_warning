"""
会话消息发送适配器。
封装 AstrBot 上下文发送能力，便于后续扩展重试、限速与回执统计。
"""

from __future__ import annotations


class SessionSender:
    """会话发送器。"""

    def __init__(self, context):
        # 发送器只包装 AstrBot 上下文，不额外持有复杂发送状态。
        self.context = context

    async def send(self, session: str, message):
        """发送消息到指定会话。"""
        # 所有消息最终都从这里落到具体会话发送能力，便于后续集中扩展重试或限速。
        await self.context.send_message(session, message)
