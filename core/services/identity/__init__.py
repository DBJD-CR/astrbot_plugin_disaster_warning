"""
身份与去重子系统导出。
统一导出事件分类、事件身份解析与运行时去重相关服务。
"""

from .event_classifier import is_major_event, is_major_record
from .event_deduplication_service import EventDeduplicationService
from .event_identity import (
    EventIdentityService,
    ensure_aware_datetime,
    ensure_utc_datetime,
    infer_source_timezone,
    resolve_event_publish_time_utc,
    resolve_event_time_aware,
    resolve_event_time_utc,
    resolve_event_unique_key,
    resolve_report_num,
    resolve_source_id,
)

__all__ = [
    "EventIdentityService",
    "EventDeduplicationService",
    "resolve_source_id",
    "resolve_report_num",
    "infer_source_timezone",
    "ensure_aware_datetime",
    "ensure_utc_datetime",
    "resolve_event_time_aware",
    "resolve_event_time_utc",
    "resolve_event_publish_time_utc",
    "resolve_event_unique_key",
    "is_major_event",
    "is_major_record",
]
