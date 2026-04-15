"""
数据源连接配置工厂。
负责根据 data_sources 配置构建灾害服务所需的 WebSocket 连接计划，减少 DisasterWarningService 中的连接拼装职责。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger


class ConnectionPlanBuilder:
    """数据源连接配置工厂。"""

    @staticmethod
    def build(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """根据插件配置构建连接计划。"""
        connections: dict[str, dict[str, Any]] = {}
        data_sources = config.get("data_sources", {})

        fan_studio_config = data_sources.get("fan_studio", {})
        if isinstance(fan_studio_config, dict) and fan_studio_config.get(
            "enabled", True
        ):
            primary_server = "wss://ws.fanstudio.tech"
            backup_server = "wss://ws.fanstudio.hk"
            # FAN Studio 使用单条 /all 聚合连接承载多个子数据源，因此只要任一子源启用就需要建连。
            fan_sub_sources = [
                "china_earthquake_warning",
                "china_earthquake_warning_provincial",
                "taiwan_cwa_earthquake",
                "taiwan_cwa_report",
                "china_cenc_earthquake",
                "usgs_earthquake",
                "china_weather_alarm",
                "china_tsunami",
                "japan_jma_eew",
            ]
            any_fan_source_enabled = any(
                fan_studio_config.get(source, True) for source in fan_sub_sources
            )
            if any_fan_source_enabled:
                connections["fan_studio_all"] = {
                    "url": f"{primary_server}/all",
                    "backup_url": f"{backup_server}/all",
                    "handler": "fan_studio",
                }
                logger.info("[灾害预警] 已配置 FAN Studio 全量数据连接 (/all)")

        p2p_config = data_sources.get("p2p_earthquake", {})
        if isinstance(p2p_config, dict) and p2p_config.get("enabled", True):
            p2p_enabled = any(
                p2p_config.get(key, True)
                for key in [
                    "japan_jma_eew",
                    "japan_jma_earthquake",
                    "japan_jma_tsunami",
                ]
            )
            if p2p_enabled:
                connections["p2p_main"] = {
                    "url": "wss://api.p2pquake.net/v2/ws",
                    "handler": "p2p",
                }

        wolfx_config = data_sources.get("wolfx", {})
        if isinstance(wolfx_config, dict) and wolfx_config.get("enabled", True):
            wolfx_sub_sources = [
                "japan_jma_eew",
                "china_cenc_eew",
                "taiwan_cwa_eew",
                "japan_jma_earthquake",
                "china_cenc_earthquake",
            ]
            any_wolfx_source_enabled = any(
                wolfx_config.get(source, True) for source in wolfx_sub_sources
            )
            if any_wolfx_source_enabled:
                connections["wolfx_all"] = {
                    "url": "wss://ws-api.wolfx.jp/all_eew",
                    "handler": "wolfx",
                }
                logger.info("[灾害预警] 已配置 Wolfx 全量数据连接 (/all_eew)")

        global_quake_config = data_sources.get("global_quake", {})
        if isinstance(global_quake_config, dict) and global_quake_config.get(
            "enabled", False
        ):
            connections["global_quake"] = {
                "url": "wss://gqm.aloys23.link/ws",
                "handler": "global_quake",
            }
            logger.info("[灾害预警] Global Quake 数据源已启用")

        return connections
