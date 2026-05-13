"""
Web 管理端实时数据载荷构建器。
统一组装 WebSocket / 实时视图需要的状态、统计、连接与地震摘要数据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .....utils.version import get_plugin_version
from ....services.display import build_admin_statistics_projection
from ....services.query.source_runtime_query_service import SourceRuntimeQueryService
from .connections_payload_builder import ConnectionsPayloadBuilder


class RealtimePayloadBuilder:
    """实时载荷构建器。"""

    def __init__(
        self,
        disaster_service,
        config: dict[str, Any],
        latency_cache: dict[str, float | None] | None = None,
    ):
        """初始化实时载荷构建器及其依赖。"""
        # 实时载荷构建器负责拼装多个子视图，因此长期持有查询器与连接载荷构建器。
        self.disaster_service = disaster_service
        self.config = config
        self.latency_cache = latency_cache if latency_cache is not None else {}
        self.source_runtime_query = (
            disaster_service.source_runtime_query
            if disaster_service
            else SourceRuntimeQueryService(config)
        )
        self._connections_payload_builder = ConnectionsPayloadBuilder(
            disaster_service=disaster_service,
            config=config,
            latency_cache=self.latency_cache,
        )

    async def build(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """构建实时数据。"""
        result: dict[str, Any] = {"timestamp": datetime.now().isoformat()}

        # 实时面板按“状态、统计、连接、近期地震、通知”五个区块组织数据，便于前端按模块渲染。
        result["status"] = self.build_status_payload()
        result["statistics"] = self.build_statistics_payload()
        result["connections"] = self.build_connections_payload(expected_sources)
        result["earthquakes"] = self._build_recent_earthquakes_payload()
        result["notifications"] = await self._build_notifications_payload()
        return result

    def _build_runtime_snapshot(self) -> dict[str, Any]:
        """构建供多个管理端接口复用的运行时快照。"""
        # 运行时快照是多个管理端接口共享的底层数据来源。
        if not self.disaster_service:
            return {}

        actual_connections = {}
        if getattr(self.disaster_service, "ws_manager", None):
            actual_connections = (
                self.disaster_service.ws_manager.get_all_connections_status()
            )

        # 这里统计的是网络接入层的活动连接数，而不是管理端前端页面连接数。
        active_websocket_connections = sum(
            1
            for status in actual_connections.values()
            if isinstance(status, dict) and status.get("connected")
        )
        global_quake_connected = any(
            "global_quake" in task.get_name() if hasattr(task, "get_name") else False
            for task in getattr(self.disaster_service, "connection_tasks", [])
        )
        return self.source_runtime_query.build_runtime_snapshot(
            actual_connections=actual_connections,
            latency_cache=self.latency_cache,
            running=bool(getattr(self.disaster_service, "running", False)),
            start_time=self.disaster_service.start_time.isoformat()
            if hasattr(self.disaster_service, "start_time")
            else None,
            uptime=self.disaster_service.get_uptime()
            if hasattr(self.disaster_service, "get_uptime")
            else "未运行",
            active_websocket_connections=active_websocket_connections,
            message_logger_enabled=self.disaster_service.message_logger.enabled
            if getattr(self.disaster_service, "message_logger", None)
            else False,
            global_quake_connected=global_quake_connected,
        )

    def build_status_payload(self) -> dict[str, Any]:
        """构建管理端状态面板所需的状态数据。"""
        snapshot = self._build_runtime_snapshot()
        if not snapshot:
            return {}

        return {
            "running": snapshot.get("running", False),
            "uptime": snapshot.get("uptime", "未知"),
            "active_connections": snapshot.get("active_websocket_connections", 0),
            "total_connections": snapshot.get("total_connections", 0),
            "connection_details": snapshot.get("connection_details", {}),
            "data_sources": snapshot.get("data_sources", []),
            "enabled_source_ids": snapshot.get("enabled_source_ids", []),
            "sub_source_status": snapshot.get("sub_source_status", {}),
            "message_logger_enabled": snapshot.get("message_logger_enabled", False),
            "eew_query_status": self.disaster_service.get_eew_query_status_data(),
            "start_time": snapshot.get("start_time"),
            "version": get_plugin_version(),
        }

    def build_statistics_payload(self) -> dict[str, Any]:
        """构建统计面板所需的数据。"""
        if not self.disaster_service or not self.disaster_service.statistics_manager:
            return {}

        statistics_manager = self.disaster_service.statistics_manager
        return build_admin_statistics_projection(
            statistics_manager.stats,
            log_stats=(
                self.disaster_service.message_logger.get_log_summary()
                if self.disaster_service.message_logger
                else {}
            ),
        )

    def build_connections_payload(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """构建连接状态视图。"""
        return self._connections_payload_builder.build(expected_sources)

    def build_status_api_payload(self) -> dict[str, Any]:
        """构建 /api/status 载荷。"""
        payload = self.build_status_payload().copy()
        payload["timestamp"] = datetime.now().isoformat()
        return payload

    def build_statistics_api_payload(self) -> dict[str, Any]:
        """构建 /api/statistics 载荷。"""
        payload = self.build_statistics_payload().copy()
        payload["recent_pushes"] = list(payload.get("event_summary_views", []))[:50]
        payload["timestamp"] = datetime.now().isoformat()
        return payload

    async def _build_notifications_payload(self) -> dict[str, Any]:
        """构建通知中心实时载荷。"""
        notification_center = getattr(
            self.disaster_service, "notification_center", None
        )
        if not notification_center:
            return {
                "items": [],
                "meta": {
                    "unread_count": 0,
                    "last_sync_at": None,
                    "total_count": 0,
                },
            }
        return await notification_center.get_payload()

    def _build_recent_earthquakes_payload(self) -> list[dict[str, Any]]:
        """构建近期地震摘要列表。"""
        # 近期地震列表来自统计投影视图，避免重复维护另一套摘要拼装逻辑。
        if not self.disaster_service or not self.disaster_service.statistics_manager:
            return []

        payload = self.build_statistics_payload()
        return list(payload.get("earthquake_views", []))
