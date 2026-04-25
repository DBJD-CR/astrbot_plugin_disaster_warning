"""
事件去重与指纹服务。
统一承接运行时事件去重、报次更新判定与事件指纹生成逻辑，
用于替代旧 support 层中的去重业务实现。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from astrbot.api import logger

from ...domain.event_models import EarthquakeEvent, EventEnvelope
from ...sources.source_catalog import get_source_entry
from .event_identity import EventIdentityService


class EventDeduplicationService:
    """运行时事件去重服务。

    负责在短时间窗口内识别重复事件，并允许合法的报次更新或状态升级继续放行。
    """

    def __init__(
        self,
        time_window_minutes: int = 1,
        location_tolerance_km: float = 20.0,
        magnitude_tolerance: float = 0.5,
    ):
        # 时间窗口、位置容差和震级容差共同决定“同一事件”的聚类范围。
        self.time_window = timedelta(minutes=time_window_minutes)
        self.location_tolerance = location_tolerance_km
        self.magnitude_tolerance = magnitude_tolerance
        self.recent_events: dict[str, dict[str, dict[str, Any]]] = {}

    @staticmethod
    def _extract_issue_type_from_earthquake(
        earthquake: EarthquakeEvent,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """统一提取日本地震情报类型，优先读取元数据字段。"""
        active_metadata = metadata if isinstance(metadata, dict) else {}
        info_type = str(
            active_metadata.get("info_type")
            or active_metadata.get("issue_type")
            or getattr(getattr(earthquake, "metadata", {}), "get", lambda *_: "")(
                "info_type"
            )
            or ""
        ).strip()
        if info_type:
            return info_type
        return ""

    @staticmethod
    def _get_domain_earthquake(event: EventEnvelope) -> EarthquakeEvent | None:
        """从统一事件中安全提取地震领域对象。"""
        if isinstance(event.event, EarthquakeEvent):
            return event.event
        return None

    @staticmethod
    def _get_source_id(event: EventEnvelope) -> str:
        """解析事件对应的数据源标识。"""
        resolved_source_id = EventIdentityService.resolve_source_id(event)
        if resolved_source_id:
            return resolved_source_id
        source = getattr(event, "source", None)
        source_value = getattr(source, "value", source)
        return str(source_value or "unknown")

    @staticmethod
    def _resolve_report_num(
        event: EventEnvelope,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """解析当前事件报次，缺失时回退为首报。"""
        del metadata
        resolved = EventIdentityService.resolve_report_num(event)
        if isinstance(resolved, int) and resolved > 0:
            return resolved
        return 1

    def should_push_event(self, event: EventEnvelope) -> bool:
        """判断是否应该推送事件。

        对非地震事件默认直接放行，地震事件则进入指纹与报次更新判定链路。
        """
        envelope = event
        domain_eq = self._get_domain_earthquake(event)
        if domain_eq is None:
            return True

        metadata = envelope.metadata if isinstance(envelope.metadata, dict) else {}
        source_id = self._get_source_id(event)
        event_fingerprint = self.generate_event_fingerprint(event, domain_eq, source_id)
        current_time = self._to_utc(domain_eq.occurred_at, source_id)

        logger.debug(f"[灾害预警] 检查事件: {source_id}, 指纹: {event_fingerprint}")

        # 指纹命中说明近期已有相近事件，需要进一步区分是重复还是合法更新。
        if event_fingerprint in self.recent_events:
            source_events = self.recent_events[event_fingerprint]

            if source_id in source_events:
                existing_event = source_events[source_id]
                existing_timestamp = existing_event["timestamp"]
                if existing_timestamp.tzinfo is None:
                    existing_timestamp = existing_timestamp.astimezone(timezone.utc)

                time_diff = abs(
                    (current_time - existing_timestamp).total_seconds() / 60
                )
                if time_diff <= self.time_window.total_seconds() / 60:
                    if self._should_allow_update(
                        event,
                        domain_eq,
                        existing_event,
                        source_id,
                        metadata=metadata,
                    ):
                        logger.debug(f"[灾害预警] 允许同一数据源更新: {source_id}")
                        current_report = self._resolve_report_num(event, metadata)
                        existing_event["processed_reports"].add(current_report)
                        existing_event["timestamp"] = current_time
                        existing_event["is_final"] = existing_event["is_final"] or bool(
                            metadata.get("is_final", False)
                        )
                        return True
                    logger.info(f"[灾害预警] 同一数据源重复事件，过滤: {source_id}")
                    return False

            # 同一指纹但来自不同数据源的事件允许继续入链，便于后续融合策略处理。
            logger.info(f"[灾害预警] 不同数据源，允许推送: {source_id}")
            current_report = self._resolve_report_num(event, metadata)
            issue_type = self._extract_issue_type_from_earthquake(domain_eq, metadata)
            self.recent_events[event_fingerprint][source_id] = {
                "timestamp": current_time,
                "source": source_id,
                "latitude": domain_eq.latitude or 0,
                "longitude": domain_eq.longitude or 0,
                "magnitude": domain_eq.magnitude or 0,
                "info_type": metadata.get("info_type")
                or self._extract_issue_type_from_earthquake(domain_eq, metadata)
                or "",
                "issue_type": issue_type,
                "processed_reports": {current_report},
                "is_final": bool(metadata.get("is_final", False)),
            }
            return True

        current_report = self._resolve_report_num(event, metadata)
        issue_type = self._extract_issue_type_from_earthquake(domain_eq, metadata)
        self.recent_events[event_fingerprint] = {
            source_id: {
                "timestamp": current_time,
                "source": source_id,
                "latitude": domain_eq.latitude or 0,
                "longitude": domain_eq.longitude or 0,
                "magnitude": domain_eq.magnitude or 0,
                "info_type": metadata.get("info_type")
                or self._extract_issue_type_from_earthquake(domain_eq, metadata)
                or "",
                "issue_type": issue_type,
                "processed_reports": {current_report},
                "is_final": bool(metadata.get("is_final", False)),
            }
        }
        logger.debug(f"[灾害预警] 事件通过基础去重检查: {source_id}")
        return True

    def generate_event_fingerprint(
        self,
        event: EventEnvelope,
        domain_eq: EarthquakeEvent,
        source_id: str,
    ) -> str:
        """生成事件指纹。

        优先使用稳定事件标识，缺失时再退回到时间、位置和震级聚类键。
        """
        identity = getattr(event, "identity", None)
        stable_event_id = str(getattr(identity, "event_id", "") or "").strip()
        source_entry = get_source_entry(source_id)
        if source_entry is not None and stable_event_id:
            fingerprint_prefix = source_entry.identity_fingerprint_prefix
            if fingerprint_prefix:
                return f"{fingerprint_prefix}_{stable_event_id}"
        if domain_eq.latitude is None or domain_eq.longitude is None:
            return "unknown_location"

        lat_grid = round(domain_eq.latitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )
        lon_grid = round(domain_eq.longitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )
        mag_grid = (
            round((domain_eq.magnitude or 0) / self.magnitude_tolerance)
            * self.magnitude_tolerance
        )
        utc_time = self._to_utc(domain_eq.occurred_at, source_id)
        time_minute = utc_time.replace(second=0, microsecond=0)
        return f"{lat_grid:.3f},{lon_grid:.3f},{mag_grid:.1f},{time_minute.strftime('%Y%m%d%H%M')}"

    def _should_allow_update(
        self,
        event: EventEnvelope,
        domain_eq: EarthquakeEvent,
        existing_event: dict[str, Any],
        source_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """判断是否允许同源事件更新。

        允许的新情况包括报次增加、最终报到达，以及部分来源的状态升级。
        """
        active_metadata = metadata if isinstance(metadata, dict) else {}
        current_report = self._resolve_report_num(event, active_metadata)
        processed_reports = existing_event.get("processed_reports", set())
        if not isinstance(processed_reports, set):
            old_updates = existing_event.get("updates", 1)
            processed_reports = {old_updates}

        if current_report not in processed_reports:
            logger.info(
                f"[灾害预警] 新报数: 第{current_report}报 (已处理: {sorted(processed_reports)})"
            )
            return True

        current_is_final = bool(active_metadata.get("is_final", False))
        if current_is_final and not existing_event.get("is_final", False):
            logger.info("[灾害预警] 最终报更新: 非最终报 -> 最终报")
            return True

        current_info_type = str(
            active_metadata.get("info_type")
            or self._extract_issue_type_from_earthquake(domain_eq, active_metadata)
            or ""
        ).lower()
        if source_id == "usgs_fanstudio":
            existing_info_type = (existing_event.get("info_type", "") or "").lower()
            if existing_info_type == "automatic" and current_info_type == "reviewed":
                logger.debug("[灾害预警] 允许USGS状态升级: automatic -> reviewed")
                return True

        jma_types = ["ScalePrompt", "Destination", "ScaleAndDestination", "DetailScale"]
        current_issue_type = self._extract_issue_type_from_earthquake(
            domain_eq, active_metadata
        )
        existing_issue_type = existing_event.get("issue_type", "")
        if current_issue_type in jma_types and existing_issue_type in jma_types:
            try:
                curr_idx = jma_types.index(current_issue_type)
                prev_idx = jma_types.index(existing_issue_type)
                if curr_idx > prev_idx:
                    logger.debug(
                        f"[灾害预警] 允许JMA情报升级: {existing_issue_type} -> {current_issue_type}"
                    )
                    return True
            except ValueError:
                pass

        existing_info_type = (existing_event.get("info_type", "") or "").lower()
        if "自动" in existing_info_type and "正式" in current_info_type:
            logger.debug(
                f"[灾害预警] 允许状态升级: {existing_info_type} -> {current_info_type}"
            )
            return True

        logger.debug(f"[灾害预警] 报数 {current_report} 已处理过，跳过")
        return False

    def cleanup_old_events(self):
        """清理过期事件。"""
        # 过期阈值放宽到两倍时间窗口，兼顾短时补报场景与内存占用控制。
        cutoff_aware = datetime.now(timezone.utc) - self.time_window * 2
        old_fingerprints = []
        for fingerprint, source_events in self.recent_events.items():
            all_expired = True
            for event_info in source_events.values():
                timestamp = event_info["timestamp"]
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                if timestamp >= cutoff_aware:
                    all_expired = False
                    break
            if all_expired:
                old_fingerprints.append(fingerprint)

        for fingerprint in old_fingerprints:
            del self.recent_events[fingerprint]

    @staticmethod
    def _to_utc(dt: datetime | None, source_id: str | None = None) -> datetime:
        """将时间转换为 UTC 时区时间对象。"""
        if dt is None:
            return datetime.now(timezone.utc)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)

        normalized_source_id = (source_id or "").strip()
        resolved = EventIdentityService.ensure_utc_datetime(dt, normalized_source_id)
        return resolved or datetime.now(timezone.utc)


__all__ = ["EventDeduplicationService"]
