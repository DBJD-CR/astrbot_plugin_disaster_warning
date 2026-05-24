"""
统计记录合并器。
负责事件摘要记录在 recent_pushes / major_events 中的匹配、合并与更新。
"""

from __future__ import annotations

from typing import Any

from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)
from .event_record_factory import EventRecordFactory


class EventRecordMerger:
    """事件记录合并器。"""

    @staticmethod
    def merge_existing_record(
        target_list: list[dict[str, Any]],
        event: EventEnvelope,
        *,
        source_id: str,
        event_unique_id: str,
        current_time: str,
        description: str,
        earthquake_level: float | None = None,
    ) -> dict[str, Any] | None:
        if isinstance(event.event, EarthquakeEvent):
            # 地震事件允许保留报次演进历史，因此走专门的合并分支。
            return EventRecordMerger._merge_earthquake_record(
                target_list,
                event,
                source_id=source_id,
                event_unique_id=event_unique_id,
                current_time=current_time,
                description=description,
                earthquake_level=earthquake_level,
            )

        if isinstance(event.event, (WeatherEvent, TsunamiEvent)):
            # 气象与海啸事件通常按唯一标识覆盖最新摘要，不维护地震那样的报次历史。
            return EventRecordMerger._merge_non_earthquake_record(
                target_list,
                event,
                source_id=source_id,
                event_unique_id=event_unique_id,
                current_time=current_time,
                description=description,
            )

        return None

    @staticmethod
    def _merge_earthquake_record(
        target_list: list[dict[str, Any]],
        event: EventEnvelope,
        *,
        source_id: str,
        event_unique_id: str,
        current_time: str,
        description: str,
        earthquake_level: float | None,
    ) -> dict[str, Any] | None:
        domain_event = event.event
        if not isinstance(domain_event, EarthquakeEvent):
            return None

        identity = getattr(event, "identity", None)
        real_event_id = str(getattr(identity, "event_id", "") or "").strip()
        if not real_event_id:
            return None

        for i, record in enumerate(target_list):
            rec_source = record.get("source")
            rec_real_id = record.get("real_event_id")
            rec_legacy_id = record.get("event_id")
            # 同一来源下才尝试合并，避免不同数据源恰好 event_id 相同造成误命中。
            if rec_source != source_id:
                continue

            rec_unique_id = record.get("unique_id")
            is_match = False
            if rec_real_id and rec_real_id == real_event_id:
                is_match = True
            elif not rec_real_id and rec_legacy_id == real_event_id:
                is_match = True
            elif rec_unique_id and rec_unique_id == event_unique_id:
                is_match = True

            if not is_match:
                continue

            # 命中旧记录时，先把旧摘要压入 history，再用当前事件内容覆盖主记录。
            old_record = record.copy()
            old_record.pop("history", None)
            if "history" not in record:
                record["history"] = []
            record["history"].insert(0, old_record)
            if len(record["history"]) > 50:
                record["history"] = record["history"][:50]

            EventRecordFactory.apply_common_fields(
                record,
                event,
                current_time=current_time,
                event_unique_id=event_unique_id,
                description=description,
                source_id=source_id,
                update_count=record.get("update_count", 1) + 1,
            )
            record["real_event_id"] = real_event_id
            EventRecordFactory.apply_earthquake_fields(
                record,
                event,
                earthquake_level=earthquake_level,
            )

            # 更新后的记录重新放回列表头部，保证最近一次报文始终排在最前面。
            updated_record = target_list.pop(i)
            target_list.insert(0, updated_record)
            return updated_record

        return None

    @staticmethod
    def _merge_non_earthquake_record(
        target_list: list[dict[str, Any]],
        event: EventEnvelope,
        *,
        source_id: str,
        event_unique_id: str,
        current_time: str,
        description: str,
    ) -> dict[str, Any] | None:
        for i, record in enumerate(target_list):
            rec_source = record.get("source")
            rec_unique_id = record.get("unique_id")
            if rec_source != source_id or rec_unique_id != event_unique_id:
                continue

            # 非地震事件命中后直接覆盖摘要内容，不再额外维护历史链条。
            EventRecordFactory.apply_common_fields(
                record,
                event,
                current_time=current_time,
                event_unique_id=event_unique_id,
                description=description,
                source_id=source_id,
                update_count=1,
            )
            record["subtitle"] = ""
            record["weather_detail"] = ""
            record.pop("history", None)

            if isinstance(event.event, WeatherEvent):
                EventRecordFactory.apply_weather_fields(record, event)
            elif isinstance(event.event, TsunamiEvent):
                EventRecordFactory.apply_tsunami_fields(record, event)

            updated_record = target_list.pop(i)
            target_list.insert(0, updated_record)
            return updated_record

        return None
