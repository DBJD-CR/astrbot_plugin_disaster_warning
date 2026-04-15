"""
灾害服务连接与事件支持服务。
负责连接名到数据源的映射、数据源启用判断与事件摘要日志构建，
进一步减少 DisasterWarningService 中残留的细节方法。
"""

from __future__ import annotations

from astrbot.api import logger

from ....models.models import (
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ...support.config_accessor import ConfigAccessor


class DisasterServiceSupportService:
    """灾害服务连接与事件支持服务。"""

    CONNECTION_SOURCE_MAPPING: dict[str, str] = {
        "fan_studio_all": "fan_studio_mixed",
        "p2p_main": "jma_p2p",
        "wolfx_all": "wolfx_mixed",
        "global_quake": "global_quake",
    }

    def __init__(self, service):
        self.service = service
        self.config_accessor = ConfigAccessor(service.config)

    def get_data_source_from_connection(self, connection_name: str) -> str:
        """从连接名称获取数据源 ID。"""
        # 连接名是运行时概念，data_source 是状态展示/通知概念，这里提供统一映射出口。
        return self.CONNECTION_SOURCE_MAPPING.get(connection_name, "unknown")

    def is_fan_studio_source_enabled(self, source_key: str) -> bool:
        """检查特定的 FAN Studio 数据源是否启用。"""
        fan_studio_config = self.config_accessor.data_sources_config().get(
            "fan_studio", {}
        )
        if not isinstance(fan_studio_config, dict) or not fan_studio_config.get(
            "enabled", True
        ):
            return False
        return fan_studio_config.get(source_key, True)

    def is_wolfx_source_enabled(self, source_key: str) -> bool:
        """检查特定的 Wolfx 数据源是否启用。"""
        wolfx_config = self.config_accessor.data_sources_config().get("wolfx", {})
        if not isinstance(wolfx_config, dict) or not wolfx_config.get("enabled", True):
            return False
        return wolfx_config.get(source_key, True)

    def log_event(self, event: DisasterEvent) -> None:
        """记录事件摘要日志。"""
        try:
            # 这里只输出轻量摘要，避免日志层过度依赖完整序列化逻辑。
            if isinstance(event.data, EarthquakeData):
                earthquake = event.data
                log_info = (
                    f"地震事件 - 震级: M{earthquake.magnitude}, 位置: {earthquake.place_name}, "
                    f"时间: {earthquake.shock_time}, 数据源: {event.source.value}"
                )
            elif isinstance(event.data, TsunamiData):
                tsunami = event.data
                log_info = f"海啸事件 - 级别: {tsunami.level}, 标题: {tsunami.title}, 数据源: {event.source.value}"
            elif isinstance(event.data, WeatherAlarmData):
                weather = event.data
                log_info = f"气象事件 - 标题: {weather.title or weather.headline}, 数据源: {event.source.value}"
            else:
                log_info = (
                    f"未知事件类型 - ID: {event.id}, 数据源: {event.source.value}"
                )

            logger.debug(f"[灾害预警] 事件详情: {log_info}")
        except Exception:
            logger.debug(
                f"[灾害预警] 事件详情: ID={event.id}, 类型={event.disaster_type.value}, 数据源={event.source.value}"
            )
