"""
Web 管理端实时数据载荷构建器。
统一组装 WebSocket / 实时视图需要的状态、统计、连接与地震摘要数据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ....utils.version import get_plugin_version
from ...support.event_view_factory import EventViewFactory
from .connections_payload_builder import ConnectionsPayloadBuilder


class RealtimePayloadBuilder:
    """实时载荷构建器。"""

    def __init__(
        self,
        disaster_service,
        config: dict[str, Any],
        latency_cache: dict[str, float | None] | None = None,
    ):
        self.disaster_service = disaster_service
        self.config = config
        self.latency_cache = latency_cache if latency_cache is not None else {}

    async def build(self, expected_sources: dict[str, str]) -> dict[str, Any]:
        """构建实时数据。"""
        result: dict[str, Any] = {"timestamp": datetime.now().isoformat()}

        # WebSocket 全量推送统一复用这份实时载荷，保证各视图刷新时看到的是同一批快照数据。
        result["status"] = self.build_status_payload()
        result["statistics"] = self.build_statistics_payload()
        result["connections"] = self.build_connections_payload(expected_sources)
        result["earthquakes"] = self._build_recent_earthquakes_payload()
        return result

    def build_status_payload(self) -> dict[str, Any]:
        if not self.disaster_service:
            return {}

        status = self.disaster_service.get_service_status()
        # status 区块重点承载管理端首页概览所需字段，避免前端自行拼接多个接口结果。
        return {
            "running": status.get("running", False),
            "uptime": status.get("uptime", "未知"),
            "active_connections": status.get("active_websocket_connections", 0),
            "total_connections": status.get("total_connections", 0),
            "connection_details": status.get("connection_details", {}),
            "data_sources": status.get("data_sources", []),
            "sub_source_status": status.get("sub_source_status", {}),
            "message_logger_enabled": status.get("message_logger_enabled", False),
            "eew_query_status": self.disaster_service.get_eew_query_status_data(),
            "start_time": status.get("start_time"),
            "version": get_plugin_version(),
        }

    def build_statistics_payload(self) -> dict[str, Any]:
        if not self.disaster_service or not self.disaster_service.statistics_manager:
            return {}

        statistics_manager = self.disaster_service.statistics_manager
        payload = statistics_manager.query_service.get_realtime_statistics_payload()
        payload["log_stats"] = (
            self.disaster_service.message_logger.get_log_summary()
            if self.disaster_service.message_logger
            else {}
        )
        return payload

    def build_connections_payload(
        self, expected_sources: dict[str, str]
    ) -> dict[str, Any]:
        builder = ConnectionsPayloadBuilder(
            disaster_service=self.disaster_service,
            config=self.config,
            latency_cache=self.latency_cache,
        )
        return builder.build(expected_sources)

    def build_status_api_payload(self) -> dict[str, Any]:
        """构建 /api/status 载荷。"""
        payload = self.build_status_payload().copy()
        payload["timestamp"] = datetime.now().isoformat()
        return payload

    def build_statistics_api_payload(self) -> dict[str, Any]:
        """构建 /api/statistics 载荷。"""
        payload = self.build_statistics_payload().copy()
        stats = (
            self.disaster_service.statistics_manager.stats
            if self.disaster_service and self.disaster_service.statistics_manager
            else {}
        )
        payload["recent_pushes"] = stats.get("recent_pushes", [])[:50]
        payload["session_stats"] = stats.get("session_stats", {})
        payload["timestamp"] = datetime.now().isoformat()
        return payload

    def _build_recent_earthquakes_payload(self) -> list[dict[str, Any]]:
        if not self.disaster_service or not self.disaster_service.statistics_manager:
            return []

        stats = self.disaster_service.statistics_manager.stats
        recent_pushes = stats.get("recent_pushes", [])
        return EventViewFactory.build_recent_earthquake_views(recent_pushes)
