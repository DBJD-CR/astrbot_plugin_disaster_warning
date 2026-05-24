"""
地震列表摘要日志服务。
负责将地震列表数据压缩为摘要日志，并回写到 MessageLogger 的统一日志入口。
"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger


class EarthquakeListSummaryService:
    """地震列表摘要日志服务。"""

    def __init__(self, logger_instance):
        # 通过主记录器复用配置与统一日志入口。
        self.logger = logger_instance

    def log_summary(
        self,
        *,
        source: str,
        earthquake_list: dict[str, Any],
        url: str | None = None,
        max_items: int | None = None,
    ) -> None:
        """记录地震列表摘要。"""
        # 摘要日志只在原始日志功能开启时工作，避免绕过总开关单独写盘。
        if not self.logger.enabled:
            return

        if source == "http_response" or "http" in source.lower():
            return
        if url and (url.startswith("http://") or url.startswith("https://")):
            return

        if max_items is None:
            max_items = self.logger.wolfx_list_log_max_items

        try:
            summary_data = self._build_summary_data(earthquake_list, max_items)
            self.logger.log_raw_message(
                source=source,
                message_type="earthquake_list_summary",
                payload_data=summary_data,
                connection_info=self._build_connection_info(url),
            )
        except Exception as e:
            logger.warning(f"[灾害预警] 地震列表摘要记录失败: {e}")
            self._log_fallback_summary(source, earthquake_list, url)

    def _build_summary_data(
        self,
        earthquake_list: dict[str, Any],
        max_items: int,
    ) -> dict[str, Any]:
        """构建地震列表摘要数据。"""
        summary_data: dict[str, Any] = {
            "summary": True,
            "message": f"地震列表摘要 (仅显示前 {max_items} 条)",
        }

        total_count = 0
        sample_events: list[dict[str, Any]] = []

        if isinstance(earthquake_list, dict):
            # Wolfx 列表按 No1/No2... 编号，摘要模式下按序抽取前 max_items 条作为样本。
            no_keys = [key for key in earthquake_list.keys() if key.startswith("No")]
            total_count = len(no_keys)
            sorted_keys = sorted(
                no_keys,
                key=lambda value: int(value[2:]) if value[2:].isdigit() else 999,
            )

            for key in sorted_keys[:max_items]:
                event = earthquake_list.get(key, {})
                if isinstance(event, dict):
                    event_data = {"key": key}
                    event_data.update(event)
                    sample_events.append(event_data)

        summary_data["total_events"] = total_count
        summary_data["sample_events"] = sample_events

        if total_count > max_items:
            summary_data["note"] = f"还有 {total_count - max_items} 条事件未显示"

        return summary_data

    def _build_connection_info(self, url: str | None) -> dict[str, Any]:
        # 给摘要日志补充最小连接上下文，便于后续区分它来自 HTTP 拉取还是 WebSocket 流。
        connection_info: dict[str, Any] = {"summary_mode": True}
        if url:
            connection_info.update(
                {
                    "url": url,
                    "method": "GET",
                    "connection_type": "http",
                }
            )
        else:
            connection_info["connection_type"] = "websocket"
        return connection_info

    def _log_fallback_summary(
        self,
        source: str,
        earthquake_list: dict[str, Any],
        url: str | None,
    ) -> None:
        """在摘要构建失败时记录兜底摘要。"""
        try:
            fallback_data = {
                "error": "摘要生成失败",
                "total_keys": len(earthquake_list)
                if isinstance(earthquake_list, dict)
                else 0,
            }
            self.logger.log_raw_message(
                source=source,
                message_type="earthquake_list_summary",
                payload_data=fallback_data,
                connection_info={"url": url} if url else {},
            )
        except Exception:
            pass
