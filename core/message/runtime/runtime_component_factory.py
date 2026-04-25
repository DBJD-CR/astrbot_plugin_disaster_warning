"""
消息运行时组件工厂。
负责根据全局配置或会话级运行时配置构建过滤器、报数控制器等推送策略依赖，
减少 MessagePushManager 中的配置解释与对象装配职责。
"""

from __future__ import annotations

from typing import Any

from .local_monitor import LocalMonitor


class MessageRuntimeComponentFactory:
    """消息运行时组件工厂。"""

    def __init__(self):
        # 当前工厂无须持久状态，保留构造函数是为了统一实例化入口。
        pass

    @staticmethod
    def _build_keyword_filter_config(
        earthquake_filters: dict[str, Any],
    ) -> dict[str, Any]:
        """构建关键词过滤配置。"""
        keyword_filter_config = earthquake_filters.get("keyword_filter", {})
        return {
            "enabled": keyword_filter_config.get("enabled", False),
            "blacklist": list(keyword_filter_config.get("blacklist", [])),
            "whitelist": list(keyword_filter_config.get("whitelist", [])),
        }

    @staticmethod
    def _build_intensity_filter_config(
        earthquake_filters: dict[str, Any],
    ) -> dict[str, Any]:
        """构建烈度过滤配置。"""
        intensity_filter_config = earthquake_filters.get("intensity_filter", {})
        return {
            "enabled": intensity_filter_config.get("enabled", True),
            "min_magnitude": intensity_filter_config.get("min_magnitude", 2.0),
            "min_intensity": intensity_filter_config.get("min_intensity", 4.0),
        }

    @staticmethod
    def _build_scale_filter_config(
        earthquake_filters: dict[str, Any],
    ) -> dict[str, Any]:
        """构建震度等级过滤配置。"""
        scale_filter_config = earthquake_filters.get("scale_filter", {})
        return {
            "enabled": scale_filter_config.get("enabled", True),
            "min_magnitude": scale_filter_config.get("min_magnitude", 2.0),
            "min_scale": scale_filter_config.get("min_scale", 1.0),
        }

    @staticmethod
    def _build_usgs_filter_config(earthquake_filters: dict[str, Any]) -> dict[str, Any]:
        """构建以震级为主的过滤配置。"""
        magnitude_only_filter_config = earthquake_filters.get(
            "magnitude_only_filter", {}
        )
        return {
            "enabled": magnitude_only_filter_config.get("enabled", True),
            "min_magnitude": magnitude_only_filter_config.get("min_magnitude", 4.5),
        }

    @staticmethod
    def _build_global_quake_filter_config(
        earthquake_filters: dict[str, Any],
    ) -> dict[str, Any]:
        """构建 Global Quake 专用过滤配置。"""
        global_quake_filter_config = earthquake_filters.get("global_quake_filter", {})
        return {
            "enabled": global_quake_filter_config.get("enabled", True),
            "min_magnitude": global_quake_filter_config.get("min_magnitude", 4.5),
            "min_intensity": global_quake_filter_config.get("min_intensity", 5.0),
        }

    @staticmethod
    def _build_local_monitor(runtime_config: dict[str, Any]) -> LocalMonitor:
        """构建本地监控组件。"""
        return LocalMonitor(runtime_config.get("local_monitoring", {}))

    @staticmethod
    def _build_weather_filter_config(
        runtime_config: dict[str, Any],
        *,
        emit_enable_log: bool,
    ) -> dict[str, Any]:
        top_level_weather_filter = runtime_config.get("weather_filter", {})
        weather_config = runtime_config.get("weather_config", {})
        nested_weather_filter = (
            weather_config.get("weather_filter", {})
            if isinstance(weather_config, dict)
            else {}
        )

        weather_filter_config: dict[str, Any] = {}
        if isinstance(top_level_weather_filter, dict):
            weather_filter_config.update(top_level_weather_filter)
        if isinstance(nested_weather_filter, dict):
            weather_filter_config.update(nested_weather_filter)

        weather_filter_config["emit_enable_log"] = emit_enable_log
        return weather_filter_config

    @staticmethod
    def build_shared_components(
        runtime_config: dict[str, Any],
        *,
        emit_weather_enable_log: bool = False,
    ) -> dict[str, Any]:
        """构建与会话无关的共享过滤组件，供初始化与运行时复用。"""
        earthquake_filters = runtime_config.get("earthquake_filters", {})
        return {
            "keyword_filter": MessageRuntimeComponentFactory._build_keyword_filter_config(
                earthquake_filters
            ),
            "intensity_filter": MessageRuntimeComponentFactory._build_intensity_filter_config(
                earthquake_filters
            ),
            "scale_filter": MessageRuntimeComponentFactory._build_scale_filter_config(
                earthquake_filters
            ),
            "usgs_filter": MessageRuntimeComponentFactory._build_usgs_filter_config(
                earthquake_filters
            ),
            "global_quake_filter": MessageRuntimeComponentFactory._build_global_quake_filter_config(
                earthquake_filters
            ),
            "local_monitor": MessageRuntimeComponentFactory._build_local_monitor(
                runtime_config
            ),
            "weather_filter": MessageRuntimeComponentFactory._build_weather_filter_config(
                runtime_config,
                emit_enable_log=emit_weather_enable_log,
            ),
        }

    def build(
        self,
        runtime_config: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """基于运行时配置构建过滤组件（支持会话级配置）。"""
        del session_id
        return self.build_shared_components(runtime_config)
