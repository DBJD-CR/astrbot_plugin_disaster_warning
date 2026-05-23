"""
台湾地震报告解析器。
负责把台湾中央气象署地震报告数据统一转换为领域事件。
"""

from __future__ import annotations

from datetime import datetime, timezone

from astrbot.api import logger

from ...utils.converters import safe_float_convert
from ..domain.event_identity import EventIdentity
from ..domain.event_models import EarthquakeEvent, EventEnvelope
from ..domain.event_payload import SourcePayload
from ..sources.source_catalog import get_source_entry
from .base_parser import BaseParser


class CwaReportParser(BaseParser):
    """台湾中央气象署地震报告解析器，处理 FAN Studio 来源数据。"""

    def __init__(self, message_logger=None):
        """初始化台湾地震报告解析器。"""
        super().__init__("cwa_fanstudio_report", message_logger)

    def _build_envelope(self, msg_data: dict[str, object]) -> EventEnvelope:
        """把台湾地震报告原始字典封装为统一事件包裹体。"""
        # 读取静态数据源配置
        source_entry = get_source_entry(self.source_id)

        # 报告图与震度图链接保留在元数据中，供后续媒体展示链复用。
        metadata = {
            "source_family": "fan_studio",
            "source_enum": source_entry.source_enum if source_entry else "",
            "source_type": source_entry.source_type.value
            if source_entry
            else "earthquake_info",
            "image_uri": msg_data.get("imageURI"),
            "shakemap_uri": msg_data.get("shakemapURI"),
        }
        event_id = str(msg_data.get("id", "") or "")

        # 实例化统一的地震数据模型，提取震级、深度、震中地点及发震时间
        domain_event = EarthquakeEvent(
            occurred_at=self._parse_datetime(msg_data.get("shockTime", "")),
            latitude=safe_float_convert(msg_data.get("latitude")),
            longitude=safe_float_convert(msg_data.get("longitude")),
            place_name=str(msg_data.get("placeName", "") or ""),
            magnitude=safe_float_convert(msg_data.get("magnitude")),
            depth=safe_float_convert(msg_data.get("depth")),
            metadata=dict(metadata),
        )

        # 构造并注入事件全局唯一的身份模型
        identity = EventIdentity(
            event_id=event_id,
            source_id=self.source_id,
            event_type="earthquake",
            provider_family=source_entry.provider_family.value
            if source_entry
            else "fan_studio",
            source_enum=source_entry.source_enum if source_entry else "",
            published_at=domain_event.occurred_at,
            aliases=tuple(
                item for item in (str(msg_data.get("id", "") or "").strip(),) if item
            ),
            attributes={
                "parser_name": self.source_entry.parser_name
                if self.source_entry
                else "",
                "config_key": source_entry.config_key if source_entry else "",
            },
        )

        # 最终组装为 EventEnvelope 返回给 Ingress 消息路由层
        return EventEnvelope(
            identity=identity,
            event=domain_event,
            received_at=datetime.now(timezone.utc),
            payload=SourcePayload(
                source_id=self.source_id,
                provider_family=source_entry.provider_family.value
                if source_entry
                else "fan_studio",
                message_type=str(msg_data.get("type") or "update").strip(),
                raw=dict(msg_data),
                attributes=dict(metadata),
            ),
            metadata=metadata,
        )

    def _parse_data(self, data: dict[str, object]) -> EventEnvelope | None:
        """解析台湾中央气象署地震报告数据。"""
        try:
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 台湾地震报告类消息至少应具备发震时间与报告图片地址，否则通常不是来自 CWA 的地震报告
            if "shockTime" not in msg_data or "imageURI" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非 CWA 地震报告数据，跳过")
                return None

            envelope = self._build_envelope(msg_data)
            # 在外层元数据中附加媒体字段，保证主流水线取值正常
            envelope.metadata.update(
                {
                    "image_uri": msg_data.get("imageURI"),
                    "shakemap_uri": msg_data.get("shakemapURI"),
                }
            )

            domain_event = envelope.event
            logger.info(
                f"[灾害预警] CWA 地震报告解析成功: {getattr(domain_event, 'place_name', '')} (M {getattr(domain_event, 'magnitude', None)}), 时间: {getattr(domain_event, 'occurred_at', None)}"
            )
            return envelope
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {exc}")
            return None
