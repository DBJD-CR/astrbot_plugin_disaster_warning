"""
融合状态仓储。
负责维护 CENC / CWA EEW 融合过程中使用的 pending 队列与 Wolfx 缓存，
减少 MessagePushManager 对状态容器与清理逻辑的直接持有。
"""

from __future__ import annotations

import time
from typing import Any

from ...domain.event_identity import EventIdentity
from ...domain.event_models import EarthquakeEvent, EventEnvelope


class FusionStateStore:
    """融合状态存储与清理服务。"""

    def __init__(self, ttl_seconds: int = 120):
        # 两组 pending 与缓存分别服务于 CENC 融合和 CWA EEW 融合。
        self.ttl_seconds = ttl_seconds
        self.cenc_pending: dict[str, dict[str, Any]] = {}
        self.cenc_wolfx_cache: dict[str, dict[int, dict[str, Any]]] = {}
        self.cwa_eew_pending: dict[str, dict[str, Any]] = {}
        self.cwa_eew_wolfx_cache: dict[str, dict[int, dict[str, Any]]] = {}

    def prune(self) -> None:
        """清理融合 pending 与缓存中过期条目。"""
        now_ts = time.time()
        ttl = self.ttl_seconds

        for pending_dict in [self.cenc_pending, self.cwa_eew_pending]:
            expired_keys: list[str] = []
            for pending_key, item in pending_dict.items():
                if not isinstance(item, dict):
                    expired_keys.append(pending_key)
                    continue
                created_at = float(item.get("created_at", 0.0) or 0.0)
                if created_at > 0 and (now_ts - created_at) > ttl:
                    future = item.get("future")
                    # 超时 pending 在清理时主动唤醒 future，保证等待协程能自然回落到 timeout 路径。
                    if (
                        future is not None
                        and hasattr(future, "done")
                        and not future.done()
                    ):
                        future.set_result("timeout")
                    expired_keys.append(pending_key)
            for pending_key in expired_keys:
                pending_dict.pop(pending_key, None)

        for cache_dict in [self.cenc_wolfx_cache, self.cwa_eew_wolfx_cache]:
            expired_event_keys: list[str] = []
            for event_key, reports in cache_dict.items():
                if not isinstance(reports, dict):
                    expired_event_keys.append(event_key)
                    continue

                expired_reports: list[int] = []
                for report_num, payload in reports.items():
                    created_at = 0.0
                    if isinstance(payload, dict):
                        created_at = float(payload.get("created_at", 0.0) or 0.0)
                    if created_at > 0 and (now_ts - created_at) > ttl:
                        expired_reports.append(report_num)

                for report_num in expired_reports:
                    reports.pop(report_num, None)

                if not reports:
                    expired_event_keys.append(event_key)

            for event_key in expired_event_keys:
                cache_dict.pop(event_key, None)

    @staticmethod
    def get_fusion_event_key(
        data: EarthquakeEvent | EventEnvelope | object,
    ) -> str:
        """融合事件键：优先统一 identity.event_id。"""
        if isinstance(data, EventEnvelope):
            identity = getattr(data, "identity", None)
            if isinstance(identity, EventIdentity):
                event_id = str(identity.event_id or "").strip()
                if event_id:
                    return event_id
            return str(data.id or "").strip()
        return str(getattr(data, "id", "") or "").strip()

    @staticmethod
    def get_fusion_report_num(
        data: EarthquakeEvent | EventEnvelope | object,
    ) -> int:
        """融合报次：统一依赖领域身份字段。"""
        try:
            if isinstance(data, EventEnvelope):
                identity = getattr(data, "identity", None)
                if (
                    isinstance(identity, EventIdentity)
                    and identity.report_num is not None
                ):
                    value = int(identity.report_num)
                    return value if value > 0 else 1
            return 1
        except (TypeError, ValueError):
            return 1
        except Exception:
            return 1

    @staticmethod
    def select_cached_report_payload(
        reports: dict[int, dict[str, Any]], target_report: int
    ) -> dict[str, Any] | None:
        """按报次精确匹配缓存（仅同报次融合）。"""
        if not reports:
            return None
        return reports.get(target_report)

    @staticmethod
    def find_best_pending_key(
        pending_dict: dict[str, dict[str, Any]],
        event_key: str,
        report_num: int,
    ) -> str | None:
        """在同 event_key 的 pending 中按报次精确匹配。"""
        exact = [
            (k, v)
            for k, v in pending_dict.items()
            if isinstance(v, dict)
            and v.get("event_key") == event_key
            and int(v.get("report_num", 1) or 1) == report_num
        ]
        if not exact:
            return None

        exact.sort(key=lambda item: float(item[1].get("created_at", 0.0)))
        return exact[0][0]
