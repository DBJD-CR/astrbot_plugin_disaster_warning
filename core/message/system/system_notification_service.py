"""
系统消息推送服务。

该服务专门处理不依赖领域事件的系统级提示，
例如离线告警、运行提示等。
这类消息不需要经过规则过滤与展示器链路，
因此采用更直接的发送方式。
"""

from __future__ import annotations

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain


class MessageSystemNotificationService:
    """系统提示消息推送服务。"""

    def __init__(self, manager):
        # 通过主消息管理器复用统一的会话发送能力与配置访问能力。
        self.manager = manager  # 主消息推送管理器 MessagePushManager 实例

    async def push_system_message(
        self,
        message: str,
        target_sessions: list[str] | None = None,
    ) -> int:
        """推送系统提示消息（不走事件过滤与复杂模版渲染，用于直接向控制台或运维群广播警告信息）。"""
        sessions = (
            target_sessions
            if target_sessions is not None
            else self.manager.config.get("target_sessions", [])
        )
        if not sessions:
            logger.warning("[灾害预警] 没有配置目标会话，系统提示消息未发送")
            return 0

        # 系统消息没有事件上下文，因此只构造最小文本消息链直接发送。
        msg_chain = MessageChain([Comp.Plain(message)])
        success_count = 0
        # 遍历目标会话并同步下发纯文本提示
        for session in sessions:
            try:
                await self.manager.session_sender.send(session, msg_chain)  # 发送消息
                success_count += 1
            except Exception as e:
                logger.error(f"[灾害预警] 系统提示消息发送到 {session} 失败: {e}")

        if success_count > 0:
            logger.info(f"[灾害预警] 系统提示消息已发送到 {success_count} 个会话")
        return success_count
