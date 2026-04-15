"""
灾害服务状态投影服务。
负责聚合 DisasterWarningService 的运行状态、连接概览、子数据源状态、运行时长与活动数据源，
减少主服务类中的状态投影逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class DisasterServiceStatusService:
    """灾害服务状态投影服务。"""

    def __init__(self, service):
        self.service = service

    def get_service_status(self) -> dict[str, Any]:
        """获取服务状态。"""
        connection_status = self.service.ws_manager.get_all_connections_status()
        # 这里聚合的是“连接状态投影”，供 Web 管理端与命令查询统一复用。
        active_websocket_connections = sum(
            1 for status in connection_status.values() if status["connected"]
        )
        global_quake_connected = any(
            "global_quake" in task.get_name() if hasattr(task, "get_name") else False
            for task in self.service.connection_tasks
        )
        sub_source_status = self.get_sub_source_status()

        return {
            "running": self.service.running,
            "active_websocket_connections": active_websocket_connections,
            "global_quake_connected": global_quake_connected,
            "total_connections": len(connection_status),
            "connection_details": connection_status,
            "sub_source_status": sub_source_status,
            "statistics_summary": self.service.statistics_manager.get_summary(),
            "data_sources": self.get_active_data_sources(),
            "message_logger_enabled": self.service.message_logger.enabled
            if self.service.message_logger
            else False,
            "uptime": self.get_uptime(),
            "start_time": self.service.start_time.isoformat()
            if hasattr(self.service, "start_time")
            else None,
        }

    def get_sub_source_status(self) -> dict[str, dict[str, bool]]:
        """获取所有子数据源的启用状态。"""
        status = {
            "fan_studio": {},
            "p2p_earthquake": {},
            "wolfx": {},
            "global_quake": {},
        }

        # 这里输出的是配置层视角的“子数据源开关”，不等价于实时连接状态。
        data_sources = self.service.config.get("data_sources", {})

        fan_config = data_sources.get("fan_studio", {})
        if isinstance(fan_config, dict):
            status["fan_studio"] = {
                k: v
                for k, v in fan_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        p2p_config = data_sources.get("p2p_earthquake", {})
        if isinstance(p2p_config, dict):
            status["p2p_earthquake"] = {
                k: v
                for k, v in p2p_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        wolfx_config = data_sources.get("wolfx", {})
        if isinstance(wolfx_config, dict):
            status["wolfx"] = {
                k: v
                for k, v in wolfx_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        gq_config = data_sources.get("global_quake", {})
        if isinstance(gq_config, dict):
            status["global_quake"] = {"enabled": gq_config.get("enabled", False)}

        return status

    def get_uptime(self) -> str:
        """获取服务运行时间。"""
        if not self.service.running or not hasattr(self.service, "start_time"):
            return "未运行"

        delta = datetime.now(timezone.utc) - self.service.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分")
        parts.append(f"{seconds}秒")
        return "".join(parts)

    def get_active_data_sources(self) -> list[str]:
        """获取活跃的数据源。"""
        active_sources: list[str] = []
        data_sources = self.service.config.get("data_sources", {})
        for service_name, service_config in data_sources.items():
            # 这里的“活跃”定义为配置层已启用，不代表当前连接一定在线。
            if isinstance(service_config, dict) and service_config.get(
                "enabled", False
            ):
                for source_name, enabled in service_config.items():
                    if (
                        source_name != "enabled"
                        and isinstance(enabled, bool)
                        and enabled
                    ):
                        active_sources.append(f"{service_name}.{source_name}")
        return active_sources
