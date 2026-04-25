"""
Web 管理端连接状态载荷构建器。
统一组装 /api/connections 与实时数据中的连接状态视图，避免重复拼装逻辑。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ....services.query.source_runtime_query_service import SourceRuntimeQueryService


class ConnectionsPayloadBuilder:
    """连接状态载荷构建器。"""

    def __init__(
        self,
        disaster_service,
        config: dict[str, Any],
        latency_cache: dict[str, float | None] | None = None,
    ):
        # 构建器既可依赖真实灾害服务，也可在服务未完全就绪时退化为纯配置查询模式。
        self.disaster_service = disaster_service
        self.config = config
        self.source_runtime_query = (
            disaster_service.source_runtime_query
            if disaster_service
            else SourceRuntimeQueryService(config)
        )
        self.latency_cache = latency_cache if latency_cache is not None else {}

    def build(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """构建连接状态视图。"""
        # 若服务或连接管理器尚未就绪，则返回空视图，避免管理端接口抛错。
        if not self.disaster_service or not self.disaster_service.ws_manager:
            return {}

        # 先读取真实运行时连接状态，再交给统一查询服务补齐展示层所需结构。
        actual_connections = (
            self.disaster_service.ws_manager.get_all_connections_status()
        )
        snapshot = self.source_runtime_query.build_runtime_snapshot(
            actual_connections=actual_connections,
            latency_cache=self.latency_cache,
        )
        return dict(snapshot.get("connections", {}))

    def build_api_payload(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """构建 /api/connections 响应载荷。"""
        return {
            "connections": self.build(expected_sources),
            "timestamp": datetime.now().isoformat(),
        }
