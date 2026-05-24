"""
文本消息构建器。
负责将灾害事件转换为纯文本消息链，减少 MessagePushManager 的展示逻辑职责。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain

from ...domain.event_models import EventEnvelope
from ..presenters.presenter_registry import present_message


class TextMessageBuilder:
    """纯文本消息构建器。"""

    def __init__(self, default_config: dict[str, Any] | None = None):
        # 默认配置用于在未显式传入完整配置时提供展示参数兜底。
        self.default_config = default_config or {}

    def build(
        self,
        event: EventEnvelope,
        source_id: str,
        config: dict[str, Any],
        full_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建纯文本部分的消息。"""
        active_config = full_config or self.default_config
        display_timezone = active_config.get("display_timezone", "UTC+8")
        # 日本震度详情是否展开由消息格式配置单独控制。
        detailed_jma = config.get("detailed_jma_intensity", False)

        options = {
            "timezone": display_timezone,
            "detailed_jma_intensity": detailed_jma,
            "local_monitoring": active_config.get("local_monitoring", {}),
        }

        data = event.event
        if hasattr(data, "description") or hasattr(data, "headline"):
            # 气象消息正文通常较长，因此单独允许配置描述截断长度。
            weather_config = active_config.get("weather_config", {})
            options["max_description_length"] = weather_config.get(
                "max_description_length", 384
            )

        if data is not None:
            message_text = present_message(
                event,
                source_id,
                options=options,
            )
        else:
            logger.warning(f"[灾害预警] 未知事件类型: {type(data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return MessageChain([Plain(message_text)])
