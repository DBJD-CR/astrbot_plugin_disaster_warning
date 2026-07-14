"""
Web 管理端连接状态载荷构建器。
统一组装 /api/connections 与实时数据中的连接状态视图，避免重复拼装逻辑。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from ....services.query.source_runtime_query_service import SourceRuntimeQueryService


class ConnectionsPayloadBuilder:
    """连接状态载荷构建器。"""

    EQSC_DISPLAY_NAME = "EQSC API"

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

    @staticmethod
    def resolve_eqsc_host(config: dict[str, Any] | None) -> str:
        """从配置解析 EQSC 探测主机名，失败时回退官方域名。"""
        eqsc_cfg = {}
        if isinstance(config, dict):
            data_sources = config.get("data_sources", {})
            if isinstance(data_sources, dict):
                raw = data_sources.get("eqsc", {})
                if isinstance(raw, dict):
                    eqsc_cfg = raw
        base_url = str(eqsc_cfg.get("base_url", "") or "").strip()
        if base_url:
            try:
                parsed = urlparse(
                    base_url if "://" in base_url else f"https://{base_url}"
                )
                if parsed.hostname:
                    return parsed.hostname
            except Exception:
                pass
        return "equake.top"

    def _build_eqsc_connection_info(self) -> dict[str, Any]:
        """构建 EQSC HTTP 辅助通道的连接状态条目。"""
        eqsc_cfg = {}
        data_sources = (
            self.config.get("data_sources", {}) if isinstance(self.config, dict) else {}
        )
        if isinstance(data_sources, dict):
            raw = data_sources.get("eqsc", {})
            if isinstance(raw, dict):
                eqsc_cfg = raw

        config_enabled = bool(eqsc_cfg.get("enabled", False))
        token_configured = bool(str(eqsc_cfg.get("refresh_token", "") or "").strip())
        latency = self.latency_cache.get("eqsc")

        health: dict[str, Any] = {}
        enrichment = None
        if self.disaster_service is not None:
            enrichment = getattr(
                self.disaster_service, "typhoon_enrichment_service", None
            )
        if enrichment is not None:
            getter = getattr(enrichment, "get_health_status", None)
            if callable(getter):
                try:
                    maybe_health = getter()
                    if isinstance(maybe_health, dict):
                        health = maybe_health
                except Exception:
                    health = {}

        # enabled：配置启用且 refresh_token 已配置（服务可工作）
        enabled = (
            bool(health.get("enabled"))
            if health
            else (config_enabled and token_configured)
        )
        # 子数据源启用仅跟随「启用EQSC台风富化」配置开关
        effective_config_enabled = bool(
            health.get("config_enabled", config_enabled) if health else config_enabled
        )
        circuit_open = bool(health.get("circuit_open", False))
        access_token_valid = bool(health.get("access_token_valid", False))
        sub_sources = health.get("sub_sources")
        if not isinstance(sub_sources, dict):
            # 与 FAN 台风开关对齐的展示键；仅一个子数据源
            sub_sources = {
                "china_typhoon": effective_config_enabled,
            }

        # HTTP 通道无 WS 重试语义。
        # 活跃连接判定：AccessToken 当前有效即视为 connected。
        # latency 缓存区分：
        # - 键不存在：尚未完成首次探测（测量中）
        # - 值为 None：连续探测失败（不可达）
        # - 值为数字：TCP 可达
        latency_probed = "eqsc" in self.latency_cache
        unreachable = latency_probed and latency is None

        if not enabled:
            status_text = "未启用"
            connected = False
        elif circuit_open:
            status_text = "熔断中"
            connected = False
        elif access_token_valid:
            # AccessToken 有效即视为活跃连接（可用）
            status_text = "可用"
            connected = True
        elif unreachable:
            status_text = "离线"
            connected = False
        else:
            # 已启用但 AccessToken 尚未获取/已失效
            status_text = "鉴权失效"
            connected = False

        return {
            "enabled": enabled,
            "connected": connected,
            "retry_count": 0,
            "has_handler": False,
            "status": status_text,
            "latency": latency,
            "sub_sources": dict(sub_sources),
            "source_ids": ["eqsc"],
            "connection_type": "http",
            "provider": "eqsc",
            "circuit_open": circuit_open,
            "token_configured": bool(health.get("token_configured", token_configured)),
            "config_enabled": effective_config_enabled,
            "access_token_valid": access_token_valid,
        }

    def build(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """构建连接状态视图。"""
        # 若服务或连接管理器尚未就绪，则返回空视图，避免管理端接口抛错。
        if not self.disaster_service or not self.disaster_service.ws_manager:
            # 即便 WS 管理器未就绪，也尽量返回 EQSC 占位，便于配置页预览
            return {self.EQSC_DISPLAY_NAME: self._build_eqsc_connection_info()}

        # 先读取真实运行时连接状态，再交给统一查询服务补齐展示层所需结构。
        actual_connections = (
            self.disaster_service.ws_manager.get_all_connections_status()
        )
        snapshot = self.source_runtime_query.build_runtime_snapshot(
            actual_connections=actual_connections,
            latency_cache=self.latency_cache,
        )
        connections = dict(snapshot.get("connections", {}))
        # EQSC 不是 WebSocket 连接组，单独合并进连接状态面板
        connections[self.EQSC_DISPLAY_NAME] = self._build_eqsc_connection_info()
        return connections

    def build_api_payload(
        self, expected_sources: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """构建 /api/connections 响应载荷。"""
        return {
            "connections": self.build(expected_sources),
            "timestamp": datetime.now().isoformat(),
        }
