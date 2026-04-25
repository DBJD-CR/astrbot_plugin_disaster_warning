"""
统计记录工厂。
负责将事件转换为事件摘要记录，供 recent_pushes / major_events / 数据库存储共用。
"""

from __future__ import annotations

from typing import Any

from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)
from ...domain.event_payload import SourcePayload
from ...services.identity.event_identity import resolve_report_num, resolve_source_id


def _adapt_event_envelope(event: EventEnvelope) -> EventEnvelope:
    """统一获取领域 envelope。"""
    return event


def _resolve_weather_level(
    weather_event: WeatherEvent | None,
    payload: dict[str, Any],
    metadata: dict[str, Any],
) -> str | None:
    """统一解析气象预警级别。"""
    # 先从领域事件自身元数据中取值，再逐层回退到统一元数据和原始载荷。
    event_metadata = (
        getattr(weather_event, "metadata", None)
        if isinstance(weather_event, WeatherEvent)
        else None
    )
    if not isinstance(event_metadata, dict):
        event_metadata = {}

    for source_dict, keys in (
        # 不同来源的级别字段命名并不一致，因此这里按一组候选键逐层兜底查找。
        (event_metadata, ["level", "alert_level", "alertLevel", "warningLevel"]),
        (metadata, ["level", "alert_level", "alertLevel", "warningLevel"]),
        (payload, ["alert_level", "alertLevel", "warningLevel", "level"]),
    ):
        for key in keys:
            value = source_dict.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    title_text = ""
    # 若结构化字段全部缺失，则退回到标题文本中按颜色关键词推断预警级别。
    if weather_event is not None:
        title_text = f"{weather_event.title or ''}{weather_event.headline or ''}"
    if not title_text:
        title_text = f"{metadata.get('title', '')}{metadata.get('headline', '')}"
    if not title_text:
        title_text = f"{payload.get('title', '')}{payload.get('headline', '')}"
    for color in ["红色", "橙色", "黄色", "蓝色", "白色"]:
        if color in title_text:
            return color
    return None


class EventRecordFactory:
    """事件记录工厂。"""

    @staticmethod
    def apply_common_fields(
        record: dict[str, Any],
        event: EventEnvelope,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        source_id: str | None = None,
        update_count: int = 1,
    ) -> dict[str, Any]:
        """填充各类事件记录共享字段。"""
        envelope = _adapt_event_envelope(event)
        # 来源标识优先使用显式传入值，其次回退到事件自身来源或统一解析结果。
        resolved_source_id = source_id or envelope.source_id or resolve_source_id(event)
        event_id = envelope.id
        event_type = envelope.event_type
        record.update(
            {
                "timestamp": current_time,
                "event_id": event_id,
                "type": event_type,
                "source": resolved_source_id,
                "source_id": envelope.source_id or resolved_source_id,
                "description": description,
                "unique_id": event_unique_id,
                "update_count": update_count,
            }
        )
        return record

    @staticmethod
    def apply_earthquake_fields(
        record: dict[str, Any],
        event: EventEnvelope,
        *,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """填充地震事件专有字段。"""
        envelope = _adapt_event_envelope(event)
        data = envelope.event
        if not isinstance(data, EarthquakeEvent):
            return record

        occurred_at = data.occurred_at.isoformat() if data.occurred_at else None
        # 地震记录除通用字段外，还需要补齐位置、震级、深度和报次相关信息。
        record.update(
            {
                "latitude": data.latitude,
                "longitude": data.longitude,
                "magnitude": data.magnitude,
                "depth": data.depth,
                "time": occurred_at,
                "real_event_id": envelope.id,
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
        event: EventEnvelope,
    ) -> dict[str, Any]:
        """填充气象预警专有字段。"""
        envelope = _adapt_event_envelope(event)
        domain_event = envelope.event
        if not isinstance(domain_event, WeatherEvent):
            return record

        # 气象来源字段差异较大，因此需要同时查看载荷、统一元数据和领域事件对象。
        payload = (
            envelope.payload.to_dict()
            if isinstance(envelope.payload, SourcePayload)
            else {}
        )
        metadata = envelope.metadata if isinstance(envelope.metadata, dict) else {}
        description = (
            getattr(domain_event, "description", None)
            or metadata.get("description")
            or metadata.get("detail")
            or payload.get("description")
            or payload.get("detail")
            or ""
        )
        record.update(
            {
                "subtitle": domain_event.headline or "",
                "weather_detail": description,
                "time": domain_event.effective_at.isoformat()
                if domain_event.effective_at
                else None,
            }
        )
        event_metadata = (
            getattr(domain_event, "metadata", None)
            if isinstance(domain_event, WeatherEvent)
            else None
        )
        if not isinstance(event_metadata, dict):
            event_metadata = {}

        # 天气类型编码可能分散在多个来源字段中，这里统一做多层兜底提取。
        weather_type_code = (
            event_metadata.get("weather_code")
            or event_metadata.get("weather_type")
            or event_metadata.get("type")
            or event_metadata.get("alert_code")
            or event_metadata.get("alertCode")
            or event_metadata.get("code")
            or metadata.get("weather_code")
            or metadata.get("weather_type")
            or metadata.get("type")
            or metadata.get("alert_code")
            or metadata.get("alertCode")
            or metadata.get("code")
            or payload.get("weather_code")
            or payload.get("weather_type")
            or payload.get("type")
            or payload.get("alert_code")
            or payload.get("alertCode")
            or payload.get("code")
            or ""
        )
        if weather_type_code:
            record["weather_type_code"] = weather_type_code
        else:
            record.pop("weather_type_code", None)

        level = _resolve_weather_level(domain_event, payload, metadata)
        if level is not None:
            record["level"] = level
        else:
            record.pop("level", None)
        return record

    @staticmethod
    def apply_tsunami_fields(
        record: dict[str, Any],
        event: EventEnvelope,
    ) -> dict[str, Any]:
        """填充海啸事件专有字段。"""
        envelope = _adapt_event_envelope(event)
        data = envelope.event
        if not isinstance(data, TsunamiEvent):
            return record

        # 海啸记录当前主要补齐发布时间与预警级别，结构保持尽量精简。
        record.update(
            {
                "time": data.issued_at.isoformat() if data.issued_at else None,
                "level": data.level,
            }
        )
        return record

    @staticmethod
    def build_base_record(
        event: EventEnvelope,
        *,
        current_time: str,
        event_unique_id: str,
        description: str,
        earthquake_level: float | None = None,
    ) -> dict[str, Any]:
        """构建基础统计记录。"""
        envelope = _adapt_event_envelope(event)
        source_id = envelope.source_id or resolve_source_id(event)
        record: dict[str, Any] = {
            "subtitle": "",
            "weather_detail": "",
        }
        # 先填充全部事件共享字段，再按事件类型补专有字段。
        EventRecordFactory.apply_common_fields(
            record,
            event,
            current_time=current_time,
            event_unique_id=event_unique_id,
            description=description,
            source_id=source_id,
            update_count=1,
        )

        if isinstance(envelope.event, EarthquakeEvent):
            # 地震事件需要补齐震级、深度、位置和报次等摘要字段。
            EventRecordFactory.apply_earthquake_fields(
                record,
                event,
                earthquake_level=earthquake_level,
            )
        elif isinstance(envelope.event, WeatherEvent):
            # 气象事件重点补充副标题、详细说明、颜色级别和类型编码。
            EventRecordFactory.apply_weather_fields(record, event)
        elif isinstance(envelope.event, TsunamiEvent):
            # 海啸事件则补充发布时间与等级字段即可。
            EventRecordFactory.apply_tsunami_fields(record, event)

        return record
