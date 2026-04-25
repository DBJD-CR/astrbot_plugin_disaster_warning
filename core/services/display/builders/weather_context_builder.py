"""
气象展示上下文构建器。
负责把统一投影输入整理为气象展示上下文，供文本展示与管理端视图复用。
"""

from __future__ import annotations

from ....domain.display_models import WeatherDisplayModel
from ....domain.event_context import WeatherDisplayContext
from .common import build_projection_view, coerce_dict, first_non_empty


def _extract_weather_projection_details(
    metadata, domain_metadata, title: str, headline: str
):
    """提取气象事件展示所需的投影细节。"""
    projection_view = build_projection_view(
        domain_metadata=domain_metadata,
        metadata=metadata,
    )
    description = first_non_empty(
        projection_view.get("description"),
        projection_view.get("summary"),
        "",
    )
    return {
        "headline": str(
            first_non_empty(headline, projection_view.get("headline"), "")
        ).strip(),
        "description": description,
        "severity_color": str(
            first_non_empty(
                projection_view.get("severity_color"),
                projection_view.get("level"),
                projection_view.get("alert_level"),
                "",
            )
        ).strip(),
        "weather_type": str(
            first_non_empty(
                projection_view.get("weather_type"),
                projection_view.get("type"),
                projection_view.get("weatherType"),
                title,
                headline,
                "",
            )
        ).strip(),
    }


def build_weather_display_context(projection: dict, options: dict | None = None):
    """构建气象展示上下文主入口。"""
    envelope = projection["envelope"]
    resolved_source_id = projection["resolved_source_id"]
    source_descriptor = projection["source_descriptor"]
    source_payload = projection["source_payload"]
    metadata = projection["metadata"]
    title = projection["title"]
    domain_event = envelope.event

    # 标题、头条与说明字段可能散落在领域对象和元数据中，这里先统一归并。
    domain_metadata = coerce_dict(getattr(domain_event, "metadata", None))
    headline = str(
        first_non_empty(
            getattr(domain_event, "headline", None),
            domain_metadata.get("headline"),
            metadata.get("headline"),
            "",
        )
    )
    payload_details = _extract_weather_projection_details(
        metadata,
        domain_metadata,
        title,
        headline,
    )
    display_metadata = {
        **metadata,
        "event_id": envelope.id,
        "source_id": resolved_source_id,
        "event_type": envelope.event_type or getattr(envelope, "event_type", "weather"),
        "description": payload_details["description"],
    }
    return WeatherDisplayContext(
        event_id=envelope.id,
        source_id=resolved_source_id,
        title=title,
        headline=payload_details["headline"],
        description=payload_details["description"],
        effective_at=(
            getattr(domain_event, "effective_at", None)
            or getattr(domain_event, "issued_at", None)
            or getattr(domain_event, "occurred_at", None)
        ),
        severity_color=str(payload_details["severity_color"] or ""),
        weather_type=str(payload_details["weather_type"] or ""),
        metadata=display_metadata,
        options=dict(options or {}),
        display_model=WeatherDisplayModel(
            title=title,
            extras=dict(display_metadata),
        ),
        source_descriptor=source_descriptor,
        payload=source_payload,
    )


__all__ = ["build_weather_display_context"]
