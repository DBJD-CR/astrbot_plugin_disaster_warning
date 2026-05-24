"""
会话消息发送适配器。
封装 AstrBot 上下文发送能力，便于后续扩展重试、限速与回执统计。
"""

from __future__ import annotations


class SessionSendFailedError(RuntimeError):
    """会话消息发送失败。"""


class SessionSender:
    """会话发送器。"""

    def __init__(self, context):
        # 发送器只包装 AstrBot 上下文，不额外持有复杂发送状态。
        self.context = context

    async def send(self, session: str, message) -> None:
        """发送消息到指定会话。

        AstrBot 的 context.send_message 会在找不到目标平台实例时返回 False，
        但不会抛出异常。这里将该返回值显式转换为发送失败异常，避免上层把
        “框架未实际投递”的场景误统计为成功。
        """
        # 所有消息最终都从这里落到具体会话发送能力，便于后续集中扩展重试或限速。
        sent = await self.context.send_message(session, message)
        if sent is False:
            raise SessionSendFailedError(
                f"AstrBot 未找到可处理会话 {session} 的平台实例，消息未发送"
            )
