"""
展示投影子系统。
统一导出展示投影公共工具、各类上下文构建器与摘要视图构建入口。
"""

from .builders.common import (
    build_projection_payload,
    normalize_projection_metadata,
    prepare_display_projection,
    resolve_projection_source_id,
    resolve_projection_title,
)
from .builders.earthquake_context_builder import build_earthquake_display_context
from .builders.tsunami_context_builder import build_tsunami_display_context
from .builders.weather_context_builder import build_weather_display_context
from .service import (
    build_admin_statistics_projection,
    build_display_context,
    build_earthquake_summary_view,
    build_earthquake_views_from_stats,
    build_event_summary_view,
    build_event_summary_views,
    build_recent_earthquake_views,
)

__all__ = [
    "build_projection_payload",
    "normalize_projection_metadata",
    "prepare_display_projection",
    "resolve_projection_source_id",
    "resolve_projection_title",
    "build_earthquake_display_context",
    "build_tsunami_display_context",
    "build_weather_display_context",
    "build_display_context",
    "build_event_summary_view",
    "build_event_summary_views",
    "build_earthquake_summary_view",
    "build_recent_earthquake_views",
    "build_earthquake_views_from_stats",
    "build_admin_statistics_projection",
]
