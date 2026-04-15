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

from ....models.models import EarthquakeData, TsunamiData, WeatherAlarmData
from ....utils.formatters import (
    CWAReportFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)


class TextMessageBuilder:
    """纯文本消息构建器。"""

    def __init__(self, default_config: dict[str, Any] | None = None):
        self.default_config = default_config or {}

    def build(
        self,
        event,
        source_id: str,
        config: dict[str, Any],
        full_config: dict[str, Any] | None = None,
    ) -> MessageChain:
        """构建纯文本部分的消息。"""
        active_config = full_config or self.default_config
        display_timezone = active_config.get("display_timezone", "UTC+8")
        detailed_jma = config.get("detailed_jma_intensity", False)

        # 文本构建器只负责“生成文本正文”，不关心地图、图标或远程媒体附件。
        if isinstance(event.data, WeatherAlarmData):
            weather_config = active_config.get("weather_config", {})
            options = {
                "max_description_length": weather_config.get(
                    "max_description_length", 384
                ),
                "timezone": display_timezone,
            }
            message_text = format_weather_message(source_id, event.data, options)
        elif isinstance(event.data, TsunamiData):
            options = {"timezone": display_timezone}
            message_text = format_tsunami_message(source_id, event.data, options)
        elif isinstance(event.data, EarthquakeData):
            options = {
                "detailed_jma_intensity": detailed_jma,
                "timezone": display_timezone,
            }
            # CWA 报告源有单独 formatter，用于兼容其专属字段与展示格式。
            if source_id == "cwa_fanstudio_report":
                message_text = CWAReportFormatter.format_message(event.data, options)
            else:
                message_text = format_earthquake_message(source_id, event.data, options)
        else:
            logger.warning(f"[灾害预警] 未知事件类型: {type(event.data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return MessageChain([Plain(message_text)])
