"""
事件元数据解析工具
统一处理 source_id、报数、事件时间、唯一标识与发布时间等常用元数据，避免多处重复实现。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ...utils.time_converter import TimeConverter


def resolve_source_id(event: DisasterEvent) -> str:
    """从事件统一解析 source_id。"""
    # 新旧数据模型可能把 source_id 放在事件层或 data 层，这里统一兜底读取。
    source_id = getattr(event, "source_id", "") or getattr(event.data, "source_id", "")
    if isinstance(source_id, str) and source_id.strip():
        return source_id.strip()

    # 若显式 source_id 缺失，则退回枚举值反查注册表，保持后续判断路径统一使用 source_id。
    source_value = getattr(getattr(event, "source", None), "value", "")
    reverse_mapping = {v.value: k for k, v in DATA_SOURCE_MAPPING.items()}
    return reverse_mapping.get(source_value, source_value)


def resolve_report_num(event: DisasterEvent) -> int | None:
    """统一解析地震报数：优先 report_num，缺失时回退 updates。"""
    if not isinstance(event.data, EarthquakeData):
        return None

    for candidate in (
        getattr(event.data, "report_num", None),
        getattr(event.data, "updates", None),
    ):
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def infer_source_timezone(source_id: str):
    """根据 source_id 推断默认时区。"""
    normalized = (source_id or "").strip().lower()
    if "jma" in normalized or "p2p" in normalized:
        return TimeConverter._get_timezone("Asia/Tokyo")
    if normalized == "global_quake":
        return timezone.utc
    return TimeConverter._get_timezone("Asia/Shanghai")


def ensure_aware_datetime(value: Any, source_id: str = "") -> datetime | None:
    """将任意时间值规范为带时区信息的 datetime。"""
    dt = TimeConverter.parse_datetime(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    inferred_tz = infer_source_timezone(source_id)
    return dt.replace(tzinfo=inferred_tz)


def ensure_utc_datetime(value: Any, source_id: str = "") -> datetime | None:
    """将任意时间值规范为 UTC aware datetime。"""
    dt = ensure_aware_datetime(value, source_id=source_id)
    if dt is None:
        return None
    return dt.astimezone(timezone.utc)


def resolve_event_time_aware(event: DisasterEvent) -> datetime | None:
    """获取事件发生时间并补齐时区信息。"""
    raw_time = None
    if isinstance(event.data, EarthquakeData):
        raw_time = event.data.shock_time
    elif isinstance(event.data, TsunamiData):
        raw_time = event.data.issue_time
    elif isinstance(event.data, WeatherAlarmData):
        raw_time = event.data.effective_time or event.data.issue_time

    if raw_time is None:
        return None
    return ensure_aware_datetime(raw_time, resolve_source_id(event))


def resolve_event_time_utc(event: DisasterEvent) -> datetime | None:
    """获取事件发生时间并统一归一化为 UTC。"""
    event_time = resolve_event_time_aware(event)
    if event_time is None:
        return None
    return event_time.astimezone(timezone.utc)


def resolve_event_publish_time_utc(event: DisasterEvent) -> datetime:
    """解析事件发布时间并归一化为 UTC（优先发布时间，其次接收时间）。"""
    data = event.data
    candidate = None

    if isinstance(data, EarthquakeData):
        candidate = data.create_time or data.update_time or data.shock_time
    elif isinstance(data, (TsunamiData, WeatherAlarmData)):
        candidate = getattr(data, "issue_time", None)

    if candidate is None:
        candidate = event.receive_time if hasattr(event, "receive_time") else None

    resolved = ensure_utc_datetime(candidate, resolve_source_id(event))
    return resolved or datetime.now(timezone.utc)


def resolve_event_unique_key(event: DisasterEvent) -> str:
    """统一解析事件唯一键，确保同一事件多报在统计层归并为同一个集合。"""
    # 该唯一键主要面向统计归并与 recent_push 去重，不追求全局永久唯一，
    # 但必须尽量保证“同一事件多报稳定、不同行情不误并”。
    data = event.data
    source_id = resolve_source_id(event)

    if isinstance(data, EarthquakeData):
        stable_event_id = (
            getattr(data, "event_id", None)
            or getattr(data, "id", None)
            or getattr(event, "id", None)
        )
        stable_event_id = str(stable_event_id or "").strip()
        if stable_event_id:
            # 对地震/预警类事件，优先只使用来源 + 稳定事件ID。
            # 同一事件多报时，震中名称、发震时间文本格式、位置描述都可能被修正，
            # 若把这些易变字段拼入唯一键，会导致趋势图和总事件数被重复累计。
            return "|".join([source_id, stable_event_id])

        shock_time = resolve_event_time_utc(event)
        shock_time_text = shock_time.isoformat() if shock_time else ""
        place_name = (getattr(data, "place_name", None) or "").strip()

        # 仅在稳定事件ID缺失时，才退化到时间+地点指纹；
        # 这里仍避免纳入 magnitude / lat / lon / report_num 等随多报变化的字段。
        return "|".join(
            [
                source_id,
                shock_time_text,
                place_name,
            ]
        )

    if isinstance(data, WeatherAlarmData):
        stable_event_id = getattr(data, "id", None) or getattr(event, "id", None)
        stable_event_id = str(stable_event_id or "").strip()
        if stable_event_id:
            return "|".join([source_id, stable_event_id])

        effective_time = resolve_event_time_utc(event)
        effective_time_text = effective_time.isoformat() if effective_time else ""
        title_text = (
            getattr(data, "title", None) or getattr(data, "headline", None) or ""
        ).strip()
        return "|".join(
            [
                source_id,
                effective_time_text,
                title_text,
            ]
        )

    if isinstance(data, TsunamiData):
        stable_event_id = getattr(data, "id", None) or getattr(event, "id", None)
        stable_event_id = str(stable_event_id or "").strip()
        if stable_event_id:
            return "|".join([source_id, stable_event_id])

        issue_time = resolve_event_time_utc(event)
        issue_time_text = issue_time.isoformat() if issue_time else ""
        title_text = (getattr(data, "title", None) or "").strip()
        return "|".join(
            [
                source_id,
                issue_time_text,
                title_text,
            ]
        )

    receive_time = ensure_utc_datetime(getattr(event, "receive_time", None), source_id)
    receive_time_text = receive_time.isoformat() if receive_time else ""
    return "|".join([source_id, str(event.id), receive_time_text])
