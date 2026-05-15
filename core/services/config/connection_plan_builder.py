"""
数据源连接配置工厂。
负责基于统一 source catalog 构建灾害服务所需的 WebSocket 连接计划，
避免继续在应用服务层硬编码 provider 子源列表。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ...sources.source_catalog import SOURCE_CATALOG
from ...sources.source_entry import SourceEntry
from ..query.source_runtime_query_service import SourceRuntimeQueryService


class ConnectionPlanBuilder:
    """数据源连接配置工厂。

    负责把已启用的数据源目录项转换为运行时可直接消费的连接计划。
    """

    @staticmethod
    def _resolve_connection_plan(
        entry: SourceEntry,
    ) -> tuple[str, dict[str, Any]] | None:
        """从单个数据源目录项解析连接分组键与连接参数。"""
        plan = entry.build_connection_plan()
        group_key = str(plan.get("group_key") or "").strip()
        if not group_key:
            return None
        return group_key, {
            key: value
            for key, value in plan.items()
            if key != "group_key" and value not in (None, "")
        }

    @classmethod
    def build(cls, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """根据统一数据源目录与启用状态构建连接计划。"""
        runtime_query = SourceRuntimeQueryService(config)
        connections: dict[str, dict[str, Any]] = {}

        # 只为当前已启用的数据源生成连接计划，避免创建无效连接占位。
        enabled_source_ids = runtime_query.get_enabled_source_ids()
        enabled_entries = [
            SOURCE_CATALOG[source_id]
            for source_id in enabled_source_ids
            if source_id in SOURCE_CATALOG
        ]

        for entry in enabled_entries:
            resolved = cls._resolve_connection_plan(entry)
            if resolved is None:
                continue
            group_key, plan = resolved
            # 同一连接分组只保留一份计划，避免多个子源重复覆盖同一连接。
            if group_key in connections:
                continue
            connections[group_key] = plan
            if group_key == "fan_studio_all":
                logger.info("[灾害预警] 已配置 FAN Studio 全量数据连接")
            elif group_key == "p2p_main":
                logger.info("[灾害预警] 已配置 P2P 地震情报连接")
            elif group_key == "wolfx_all":
                logger.info("[灾害预警] 已配置 Wolfx 全量数据连接")
            elif group_key == "global_quake":
                logger.info("[灾害预警] Global Quake 数据源已启用")
            else:
                logger.info(f"[灾害预警] 已配置数据连接，连接分组为 {group_key}")

        return connections
