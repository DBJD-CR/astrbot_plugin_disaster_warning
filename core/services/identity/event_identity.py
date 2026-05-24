"""
事件身份与时间归一化服务。
统一承接事件唯一键、来源解析、报数解析与时间标准化逻辑，
用于替代旧 support 层中混合的运行时/领域身份职责。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ....utils.time_converter import TimeConverter
from ...domain.event_identity import EventIdentity
from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)
from ...sources.source_catalog import get_source_entry


class EventIdentityService:
    """统一事件身份与时间辅助服务。

    负责集中处理来源标识、事件唯一键、报次与时间归一化，降低上层业务分散判断的复杂度。
    """

    @staticmethod
    def resolve_source_id(event: EventEnvelope) -> str:
        """从统一事件中解析数据源标识。"""
        identity = getattr(event, "identity", None)
        source_id = ""
        # 优先从身份对象中抽取
        if isinstance(identity, EventIdentity):
            source_id = identity.source_id
        # 若未成功获取，则直接从信封顶级属性中索取
        if not source_id:
            source_id = getattr(event, "source_id", "")
        if isinstance(source_id, str) and source_id.strip():
            return source_id.strip()
        return ""

    @classmethod
    def get_source_entry(cls, source_id: str):
        """获取统一数据源目录项。"""
        normalized = (source_id or "").strip()
        if not normalized:
            return None
        return get_source_entry(normalized)

    @classmethod
    def get_source_entry_for_event(cls, event: EventEnvelope):
        """按事件解析统一数据源目录项。"""
        return cls.get_source_entry(cls.resolve_source_id(event))

    @classmethod
    def resolve_report_num(cls, event: EventEnvelope) -> int | None:
        """统一解析地震报次。

        优先读取领域身份中的显式报次，缺失时再回退到目录字段与常见兼容键名。
        """
        identity = getattr(event, "identity", None)
        if isinstance(identity, EventIdentity) and identity.report_num is not None:
            try:
                value = int(identity.report_num)
            except (TypeError, ValueError):
                value = None
            if isinstance(value, int) and value > 0:
                return value

        source_entry = cls.get_source_entry_for_event(event)
        # 获取源数据解析时绑定的物理报数定义键名
        report_field_name = (
            source_entry.resolve_metadata_field("report_num_field")
            if source_entry is not None
            else ""
        )

        domain_metadata = getattr(getattr(event, "event", None), "metadata", None)
        envelope_metadata = getattr(event, "metadata", None)
        payload = getattr(event, "payload", None)
        payload_raw = getattr(payload, "raw", None)
        payload_attributes = getattr(payload, "attributes", None)

        candidates: list[Any] = []
        field_names: list[str] = []
        if report_field_name:
            field_names.append(str(report_field_name))
        # 通用兜底后备搜索键列表
        for fallback_name in (
            "report_num",
            "ReportNum",
            "updates",
            "serial",
            "Serial",
            "serialNo",
        ):
            if fallback_name not in field_names:
                field_names.append(fallback_name)

        # 依次从不同数据嵌套层中尝试取回候选报数值，保证鲁棒性
        for field_name in field_names:
            if isinstance(domain_metadata, dict):
                candidates.append(domain_metadata.get(field_name))
            if isinstance(envelope_metadata, dict):
                candidates.append(envelope_metadata.get(field_name))
            if isinstance(payload_attributes, dict):
                candidates.append(payload_attributes.get(field_name))
            if isinstance(payload_raw, dict):
                candidates.append(payload_raw.get(field_name))

        for candidate in candidates:
            try:
                value = int(candidate)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return None

    @classmethod
    def infer_source_timezone(cls, source_id: str):
        """根据统一数据源目录推断默认时区。"""
        source_entry = cls.get_source_entry(source_id)
        timezone_name = (
            source_entry.timezone_name if source_entry is not None else "Asia/Shanghai"
        )
        if timezone_name.upper() == "UTC":
            return timezone.utc
        return TimeConverter._get_timezone(timezone_name)

    @classmethod
    def ensure_aware_datetime(cls, value: Any, source_id: str = "") -> datetime | None:
        """将任意时间值规范为带时区信息的时间对象。"""
        dt = TimeConverter.parse_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt
        # 补全缺省时区信息
        inferred_tz = cls.infer_source_timezone(source_id)
        return dt.replace(tzinfo=inferred_tz)

    @classmethod
    def ensure_utc_datetime(cls, value: Any, source_id: str = "") -> datetime | None:
        """将任意时间值规范为 UTC 时区时间对象。"""
        dt = cls.ensure_aware_datetime(value, source_id=source_id)
        if dt is None:
            return None
        return dt.astimezone(timezone.utc)

    @classmethod
    def resolve_event_time_aware(
        cls,
        event: EventEnvelope,
    ) -> datetime | None:
        """获取事件发生时间并补齐时区信息。"""
        envelope = event
        raw_time = None
        # 根据领域事件的具体业务形态提取主时间字段
        if isinstance(envelope.event, EarthquakeEvent):
            raw_time = envelope.event.occurred_at
        elif isinstance(envelope.event, TsunamiEvent):
            raw_time = envelope.event.issued_at
        elif isinstance(envelope.event, WeatherEvent):
            raw_time = envelope.event.effective_at

        if raw_time is None:
            return None
        return cls.ensure_aware_datetime(raw_time, cls.resolve_source_id(event))

    @classmethod
    def resolve_event_time_utc(
        cls,
        event: EventEnvelope,
    ) -> datetime | None:
        """获取事件发生时间并统一归一化为 UTC。"""
        event_time = cls.resolve_event_time_aware(event)
        if event_time is None:
            return None
        return event_time.astimezone(timezone.utc)

    @classmethod
    def resolve_event_publish_time_utc(
        cls,
        event: EventEnvelope,
    ) -> datetime:
        """解析事件发布时间并归一化为 UTC。

        若缺少显式发布时间，则按事件类型退回到发生时间、生效时间或接收时间。
        """
        envelope = event
        identity = getattr(envelope, "identity", None)
        source_id = cls.resolve_source_id(event)
        source_entry = cls.get_source_entry(source_id)
        candidate = (
            getattr(identity, "published_at", None)
            if isinstance(identity, EventIdentity)
            else None
        )

        if candidate is None and isinstance(envelope.event, EarthquakeEvent):
            publish_field_name = (
                source_entry.resolve_metadata_field("publish_time_field")
                if source_entry is not None
                else ""
            )
            domain_metadata = (
                envelope.event.metadata
                if isinstance(envelope.event.metadata, dict)
                else {}
            )
            envelope_metadata = (
                envelope.metadata if isinstance(envelope.metadata, dict) else {}
            )
            if publish_field_name:
                candidate = domain_metadata.get(
                    publish_field_name
                ) or envelope_metadata.get(publish_field_name)
            if candidate is None:
                candidate = envelope.event.occurred_at
        elif candidate is None and isinstance(envelope.event, TsunamiEvent):
            candidate = envelope.event.issued_at
        elif candidate is None and isinstance(envelope.event, WeatherEvent):
            candidate = envelope.event.effective_at

        if candidate is None:
            candidate = getattr(envelope, "received_at", None)

        resolved = cls.ensure_utc_datetime(candidate, source_id)
        return resolved or datetime.now(timezone.utc)

    @classmethod
    def resolve_event_unique_key(self, event: EventEnvelope) -> str:
        """统一解析事件唯一键。

        优先使用稳定事件标识，缺失时再按事件类型拼接具备业务意义的回退键。
        """
        envelope = event
        identity = getattr(event, "identity", None)
        domain_event = envelope.event
        source_id = envelope.source_id or self.resolve_source_id(event)

        # 优先读取由信源解析层显式映射封装出的 EventIdentity 稳定事件 ID
        if isinstance(identity, EventIdentity):
            stable_event_id = str(identity.event_id or "").strip()
            if stable_event_id:
                return "|".join([source_id, stable_event_id])

        # 无稳定身份 ID 时的保底唯一键策略，按时空属性合并以区分不同实体
        if isinstance(domain_event, EarthquakeEvent):
            place_name = (getattr(domain_event, "place_name", None) or "").strip()
            shock_time = self.resolve_event_time_utc(event)
            shock_time_text = shock_time.isoformat() if shock_time else ""
            return "|".join([source_id, shock_time_text, place_name])

        if isinstance(domain_event, WeatherEvent):
            effective_time = self.resolve_event_time_utc(event)
            effective_time_text = effective_time.isoformat() if effective_time else ""
            title_text = (
                getattr(domain_event, "title", None)
                or getattr(domain_event, "headline", None)
                or ""
            ).strip()
            return "|".join([source_id, effective_time_text, title_text])

        if isinstance(domain_event, TsunamiEvent):
            issue_time = self.resolve_event_time_utc(event)
            issue_time_text = issue_time.isoformat() if issue_time else ""
            title_text = (getattr(domain_event, "title", None) or "").strip()
            return "|".join([source_id, issue_time_text, title_text])

        receive_time = self.ensure_utc_datetime(
            getattr(envelope, "received_at", None), source_id
        )
        receive_time_text = receive_time.isoformat() if receive_time else ""
        return "|".join([source_id, str(envelope.id), receive_time_text])


_event_identity_service = EventIdentityService()

resolve_source_id = _event_identity_service.resolve_source_id
resolve_report_num = _event_identity_service.resolve_report_num
infer_source_timezone = _event_identity_service.infer_source_timezone
ensure_aware_datetime = _event_identity_service.ensure_aware_datetime
ensure_utc_datetime = _event_identity_service.ensure_utc_datetime
resolve_event_time_aware = _event_identity_service.resolve_event_time_aware
resolve_event_time_utc = _event_identity_service.resolve_event_time_utc
resolve_event_publish_time_utc = _event_identity_service.resolve_event_publish_time_utc
resolve_event_unique_key = _event_identity_service.resolve_event_unique_key

__all__ = [
    "EventIdentityService",
    "resolve_source_id",
    "resolve_report_num",
    "infer_source_timezone",
    "ensure_aware_datetime",
    "ensure_utc_datetime",
    "resolve_event_time_aware",
    "resolve_event_time_utc",
    "resolve_event_publish_time_utc",
    "resolve_event_unique_key",
]
