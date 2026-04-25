"""
统一数据源运行态查询服务。
集中提供基于数据源目录的启用态、分组摘要、连接映射与运行态快照，避免上层继续直接依赖旧配置结构。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ...sources.source_catalog import SOURCE_CATALOG
from ...sources.source_entry import ProviderFamily, SourceEntry
from ..config.config_service import ConfigAccessor

_CONNECTION_GROUP_ALIAS: dict[str, str] = {
    ProviderFamily.FAN_STUDIO.value: "fan_studio_all",
    ProviderFamily.P2P.value: "p2p_main",
    ProviderFamily.WOLFX.value: "wolfx_all",
    ProviderFamily.GLOBAL_QUAKE.value: "global_quake",
}

_CONNECTION_DISPLAY_NAME: dict[str, str] = {
    "fan_studio_all": "FAN Studio",
    "p2p_main": "P2P地震情報",
    "wolfx_all": "Wolfx",
    "global_quake": "Global Quake",
}


class SourceRuntimeQueryService:
    """基于统一数据源目录的运行态查询服务。"""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config_accessor = ConfigAccessor(config or {})

    def _data_sources_config(self) -> dict[str, Any]:
        """获取数据源配置总表。"""
        return self.config_accessor.data_sources_config()

    def _group_config(self, config_group: str) -> dict[str, Any]:
        """获取指定数据源分组的配置。"""
        data_sources = self._data_sources_config()
        value = data_sources.get(config_group, {})
        return value if isinstance(value, dict) else {}

    def is_source_enabled(self, source_id: str) -> bool:
        """判断指定数据源是否在当前配置中启用。"""
        entry = SOURCE_CATALOG.get((source_id or "").strip())
        if entry is None:
            return False
        group_cfg = self._group_config(entry.config_group)
        if not group_cfg.get("enabled", False):
            return False
        return bool(group_cfg.get(entry.config_key, False))

    def is_family_enabled(self, provider_family: str) -> bool:
        """判断指定提供方家族下是否存在已启用数据源。"""
        family_value = (provider_family or "").strip()
        if not family_value:
            return False
        return any(
            self.is_source_enabled(source_id)
            for source_id, entry in SOURCE_CATALOG.items()
            if entry.provider_family.value == family_value
        )

    def get_enabled_source_ids(self) -> list[str]:
        return [
            source_id
            for source_id in SOURCE_CATALOG
            if self.is_source_enabled(source_id)
        ]

    def get_enabled_source_labels(self) -> list[str]:
        labels: list[str] = []
        for source_id in self.get_enabled_source_ids():
            entry = SOURCE_CATALOG[source_id]
            labels.append(f"{entry.config_group}.{entry.config_key}")
        return labels

    def build_sub_source_status(self) -> dict[str, dict[str, bool]]:
        """按配置分组构建子数据源启用状态表。"""
        grouped: dict[str, dict[str, bool]] = defaultdict(dict)
        for source_id, entry in SOURCE_CATALOG.items():
            grouped[entry.config_group][entry.config_key] = self.is_source_enabled(
                source_id
            )
        return dict(grouped)

    def get_connection_group_key(self, entry: SourceEntry) -> str:
        """解析数据源所属连接分组键。"""
        explicit_group = (entry.connection_group or "").strip()
        if explicit_group:
            return explicit_group
        return _CONNECTION_GROUP_ALIAS.get(
            entry.provider_family.value, entry.provider_family.value
        )

    def get_expected_connection_groups(self) -> dict[str, str]:
        """获取理论上应存在的连接分组及其展示名称。"""
        groups: dict[str, str] = {}
        for entry in SOURCE_CATALOG.values():
            group_key = self.get_connection_group_key(entry)
            groups[group_key] = _CONNECTION_DISPLAY_NAME.get(group_key, group_key)
        return groups

    def get_connection_group_source_map(self) -> dict[str, list[str]]:
        """构建连接分组到数据源标识列表的映射。"""
        grouped: dict[str, list[str]] = defaultdict(list)
        for source_id, entry in SOURCE_CATALOG.items():
            group_key = self.get_connection_group_key(entry)
            grouped[group_key].append(source_id)
        return {key: sorted(value) for key, value in grouped.items()}

    def build_connection_group_status(self) -> dict[str, dict[str, bool]]:
        """构建连接分组下各数据源的启用状态。"""
        grouped: dict[str, dict[str, bool]] = defaultdict(dict)
        for source_id, entry in SOURCE_CATALOG.items():
            group_key = self.get_connection_group_key(entry)
            grouped[group_key][source_id] = self.is_source_enabled(source_id)
        return dict(grouped)

    def build_runtime_snapshot(
        self,
        *,
        actual_connections: dict[str, dict[str, Any]] | None = None,
        latency_cache: dict[str, float | None] | None = None,
        running: bool = False,
        start_time: str | None = None,
        uptime: str = "未运行",
        active_websocket_connections: int = 0,
        message_logger_enabled: bool = False,
        global_quake_connected: bool = False,
    ) -> dict[str, Any]:
        """构建统一运行态快照。

        用于同时供给管理端实时面板、状态接口与连接信息展示。
        """
        actual_connections = actual_connections or {}
        latency_cache = latency_cache or {}
        expected_groups = self.get_expected_connection_groups()
        group_source_map = self.get_connection_group_source_map()
        group_status_map = self.build_connection_group_status()

        connections: dict[str, dict[str, Any]] = {}
        for group_key, display_name in expected_groups.items():
            # 即使某分组当前尚未建立真实连接，也要给前端返回完整的占位状态。
            conn_info = dict(
                actual_connections.get(
                    group_key,
                    {
                        "connected": False,
                        "retry_count": 0,
                        "has_handler": False,
                        "status": "未连接",
                    },
                )
            )
            conn_info["enabled"] = any(group_status_map.get(group_key, {}).values())
            conn_info["latency"] = latency_cache.get(group_key)
            conn_info["sub_sources"] = dict(group_status_map.get(group_key, {}))
            conn_info["source_ids"] = list(group_source_map.get(group_key, []))
            connections[display_name] = conn_info

        return {
            "running": running,
            "uptime": uptime,
            "active_websocket_connections": active_websocket_connections,
            "global_quake_connected": global_quake_connected,
            "total_connections": len(actual_connections),
            "connection_details": actual_connections,
            "connections": connections,
            "sub_source_status": self.build_sub_source_status(),
            "data_sources": self.get_enabled_source_labels(),
            "enabled_source_ids": self.get_enabled_source_ids(),
            "message_logger_enabled": message_logger_enabled,
            "start_time": start_time,
        }


__all__ = ["SourceRuntimeQueryService"]
