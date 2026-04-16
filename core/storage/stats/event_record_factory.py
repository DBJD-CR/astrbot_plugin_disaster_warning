"""
统计记录工厂。
负责将事件转换为 recent_pushes / major_events / 数据库存储共用的基础记录结构。
"""

from __future__ import annotations

from typing import Any

from ....models.models import (
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ...support.event_metadata import resolve_report_num, resolve_source_id


def _resolve_weather_level(data: WeatherAlarmData) -> str | None:
    """统一解析气象预警级别。"""
    if data.alert_level:
        return data.alert_level

    title_text = data.title or data.headline or ""
    for color in ["红色", "橙色", "黄色", "蓝色"]:
        if color in title_text:
            return color
    return None


class EventRecordFactory:
    """事件记录工厂。"""

    @staticmethod
    def apply_common_fields(
        record: dict[str, Any],
        event: DisasterEvent,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        source_id: str | None = None,
        update_count: int = 1,
    ) -> dict[str, Any]:
        """填充各类事件记录共享字段。"""
        # 共享字段确保 recent_pushes、major_events 与数据库记录具备一致的基础结构。
        resolved_source_id = source_id or resolve_source_id(event)
        record.update(
            {
                "timestamp": current_time,
                "event_id": event.id,
                "type": event.disaster_type.value,
                "source": resolved_source_id,
                "source_id": getattr(event.data, "source_id", "")
                or getattr(event, "source_id", "")
                or "",
                "description": description,
                "unique_id": event_unique_id,
                "update_count": update_count,
            }
        )
        return record

    @staticmethod
    def apply_earthquake_fields(
        record: dict[str, Any],
        event: DisasterEvent,
        *,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """填充地震事件专有字段。"""
        data = event.data
        if not isinstance(data, EarthquakeData):
            return record

        record.update(
            {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "magnitude": data.magnitude,
                "depth": data.depth,
                "time": data.shock_time.isoformat() if data.shock_time else None,
                "real_event_id": data.event_id,
                "level": earthquake_level,
            }
        )

        report_num = resolve_report_num(event)
        if report_num is not None:
            record["report_num"] = report_num
        return record

    @staticmethod
    def apply_weather_fields(
        record: dict[str, Any],
        event: DisasterEvent,
    ) -> dict[str, Any]:
        """填充气象预警专有字段。"""
        data = event.data
        if not isinstance(data, WeatherAlarmData):
            return record

        record.update(
            {
                "subtitle": data.headline or "",
                "weather_detail": data.description or "",
                "time": data.issue_time.isoformat() if data.issue_time else None,
            }
        )
        if data.type:
            record["weather_type_code"] = data.type
        else:
            record.pop("weather_type_code", None)

        level = _resolve_weather_level(data)
        if level is not None:
            record["level"] = level
        else:
            record.pop("level", None)
        return record

    @staticmethod
    def apply_tsunami_fields(
        record: dict[str, Any],
        event: DisasterEvent,
    ) -> dict[str, Any]:
        """填充海啸事件专有字段。"""
        data = event.data
        if not isinstance(data, TsunamiData):
            return record

        record.update(
            {
                "time": data.issue_time.isoformat() if data.issue_time else None,
                "level": data.level,
            }
        )
        return record

    @staticmethod
    def build_base_record(
        event: DisasterEvent,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """构建基础统计记录。"""
        source_id = resolve_source_id(event)
        record: dict[str, Any] = {
            "subtitle": "",
            "weather_detail": "",
        }
        EventRecordFactory.apply_common_fields(
            record,
            event,
            current_time=current_time,
            event_unique_id=event_unique_id,
            description=description,
            source_id=source_id,
            update_count=1,
        )

        if isinstance(event.data, EarthquakeData):
            EventRecordFactory.apply_earthquake_fields(
                record,
                event,
                earthquake_level=earthquake_level,
            )
        elif isinstance(event.data, WeatherAlarmData):
            EventRecordFactory.apply_weather_fields(record, event)
        elif isinstance(event.data, TsunamiData):
            EventRecordFactory.apply_tsunami_fields(record, event)

        return record
