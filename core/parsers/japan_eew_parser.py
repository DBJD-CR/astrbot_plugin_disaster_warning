"""
日本地震预警解析器。
负责把 FAN Studio、P2P 与 Wolfx 来源的日本地震预警数据统一转换为领域事件。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from ...utils.converters import ScaleConverter, safe_float_convert
from ..domain.event_identity import EventIdentity
from ..domain.event_models import EarthquakeEvent, EventEnvelope
from ..domain.event_payload import SourcePayload
from ..sources.source_catalog import get_source_entry
from .base_parser import BaseParser


class JmaEewFanStudioParser(BaseParser):
    """日本气象厅地震预警解析器 - FAN Studio。"""

    def __init__(self, message_logger=None):
        """初始化 FAN Studio 日本预警解析器。"""
        super().__init__("jma_fanstudio", message_logger)

    def _build_envelope(self, msg_data: dict[str, Any]) -> EventEnvelope:
        """把 FAN Studio 日本预警原始字典封装为统一事件包裹体。"""
        source_entry = get_source_entry(self.source_id)
        # FAN Studio 报次字段通常来自 updates，这里统一规整为整数。
        report_num = (
            msg_data.get("updates", 1)
            if isinstance(msg_data.get("updates"), int)
            else 1
        )
        metadata = {
            "source_family": "fan_studio",
            "source_enum": source_entry.source_enum if source_entry else "",
            "source_type": source_entry.source_type.value
            if source_entry
            else "earthquake_warning",
            "report_num": report_num,
            "is_final": bool(msg_data.get("final", False)),
            "is_cancel": bool(msg_data.get("cancel", False)),
            "info_type": msg_data.get("infoTypeName", ""),
            "create_time": self._parse_datetime(msg_data.get("createTime", "")),
            "jma_warning_areas": [],
            "jma_warning_area_ranges": [],
        }
        domain_event = EarthquakeEvent(
            occurred_at=self._parse_datetime(msg_data.get("shockTime", "")),
            latitude=safe_float_convert(msg_data.get("latitude")),
            longitude=safe_float_convert(msg_data.get("longitude")),
            place_name=str(msg_data.get("placeName", "") or ""),
            magnitude=safe_float_convert(msg_data.get("magnitude")),
            depth=safe_float_convert(msg_data.get("depth")),
            scale=ScaleConverter.parse_jma_cwa_scale(msg_data.get("epiIntensity", "")),
            metadata=dict(metadata),
        )
        created_at = self._parse_datetime(msg_data.get("createTime", ""))
        identity = EventIdentity(
            event_id=str(msg_data.get("id", "") or ""),
            source_id=self.source_id,
            event_type="earthquake_warning",
            provider_family=source_entry.provider_family.value
            if source_entry
            else "fan_studio",
            source_enum=source_entry.source_enum if source_entry else "",
            report_num=report_num,
            published_at=created_at or domain_event.occurred_at,
            is_final=bool(msg_data.get("final", False)),
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

    def _parse_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析 FAN Studio 日本气象厅地震预警数据。"""
        try:
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 预计震度与情报类型至少应命中其一，否则通常不是正式预警消息。
            if "epiIntensity" not in msg_data and "infoTypeName" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非 JMA 地震预警数据，跳过")
                return None

            # 取消报在当前推送链中不作为正式地震事件继续向后处理。
            if msg_data.get("cancel", False):
                logger.info(f"[灾害预警] {self.source_id} 收到取消报，跳过")
                return None

            envelope = self._build_envelope(msg_data)
            domain_event = envelope.event
            report_num = (
                msg_data.get("updates", 1)
                if isinstance(msg_data.get("updates"), int)
                else 1
            )
            envelope.metadata.update(
                {
                    "report_num": report_num,
                    "is_final": bool(msg_data.get("final", False)),
                    "is_cancel": bool(msg_data.get("cancel", False)),
                    "info_type": msg_data.get("infoTypeName", ""),
                    "create_time": self._parse_datetime(msg_data.get("createTime", "")),
                }
            )

            logger.info(
                f"[灾害预警] JMA地震预警解析成功: {getattr(domain_event, 'place_name', '')} (M {getattr(domain_event, 'magnitude', None)}), 时间: {getattr(domain_event, 'occurred_at', None)}"
            )
            return envelope
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {exc}")
            return None


class JmaEewP2PParser(BaseParser):
    """日本气象厅紧急地震速报解析器 - P2P。"""

    def __init__(self, message_logger=None):
        super().__init__("jma_p2p", message_logger)

    def parse_message(self, message: str) -> EventEnvelope | None:
        """解析 P2P 消息。"""
        try:
            data = json.loads(message)
            code = data.get("code")

            # P2P 用业务码区分不同类型，其中 556 才是正式紧急地震速报。
            if code == 556:
                logger.debug(f"[灾害预警] {self.source_id} 收到紧急地震速报（警报）")
                return self._parse_eew_data(data)
            if code == 554:
                logger.debug(
                    f"[灾害预警] {self.source_id} 收到紧急地震速报发布检测消息，忽略"
                )
                return None

            logger.debug(f"[灾害预警] {self.source_id} 非地震预警数据，code: {code}")
            return None
        except json.JSONDecodeError as exc:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {exc}")
            return None

    def _parse_eew_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析紧急地震速报数据。"""
        try:
            earthquake_info = data.get("earthquake", {})
            hypocenter = earthquake_info.get("hypocenter", {})
            issue_info = data.get("issue", {})
            areas = data.get("areas", [])

            # 最大震度可能直接给出，也可能需要从区域列表中推导。
            max_scale_raw = -1
            if "maxScale" in earthquake_info:
                max_scale_raw = earthquake_info.get("maxScale", -1)
            elif "max_scale" in earthquake_info:
                max_scale_raw = earthquake_info.get("max_scale", -1)
            else:
                raw_scales = []
                for area in areas:
                    if not isinstance(area, dict):
                        continue
                    scale = (
                        ScaleConverter.normalize_p2p_scale_value(area.get("scaleFrom"))
                        or 0
                    )
                    if scale <= 0:
                        scale = (
                            ScaleConverter.normalize_p2p_scale_value(
                                area.get("scaleTo")
                            )
                            or 0
                        )
                    if scale > 0:
                        raw_scales.append(scale)

                max_scale_raw = max(raw_scales) if raw_scales else -1
                if max_scale_raw > 0:
                    logger.warning(
                        f"[灾害预警] {self.source_id} 使用areas计算maxScale: {max_scale_raw}"
                    )

            scale = (
                ScaleConverter.convert_p2p_scale(max_scale_raw)
                if max_scale_raw != -1
                else None
            )

            shock_time = None
            if "time" in earthquake_info:
                shock_time = self._parse_datetime(earthquake_info.get("time", ""))
            elif "originTime" in earthquake_info:
                shock_time = self._parse_datetime(earthquake_info.get("originTime", ""))
            else:
                logger.warning(f"[灾害预警] {self.source_id} 缺少地震时间信息")

            required_hypocenter_fields = ["latitude", "longitude", "name"]
            missing_fields = []
            for field in required_hypocenter_fields:
                if field not in hypocenter or hypocenter[field] is None:
                    missing_fields.append(field)

            if missing_fields:
                logger.warning(
                    f"[灾害预警] {self.source_id} 缺少震源必填字段: {missing_fields}，继续处理..."
                )

            # 取消报、测试报与假定震源都作为附加元数据保留，供后续展示层使用。
            is_cancelled = data.get("cancelled", False)
            if is_cancelled:
                logger.info(f"[灾害预警] {self.source_id} 收到取消的EEW事件")

            is_test = data.get("test", False)
            if is_test:
                logger.info(f"[灾害预警] {self.source_id} 收到测试模式的EEW事件")

            is_plum = earthquake_info.get("condition") == "仮定震源要素"
            if not is_plum:
                for area in areas:
                    if isinstance(area, dict) and str(area.get("kindCode", "")) == "19":
                        is_plum = True
                        break

            report_num = (
                issue_info.get("serial", 1)
                if isinstance(issue_info.get("serial"), int)
                else 1
            )
            warning_areas: list[str] = []
            warning_area_ranges: list[str] = []
            # 日本预警区域列表会同时用于文本展示与影响范围提示，这里先归一化整理。
            for area in areas:
                if not isinstance(area, dict):
                    continue
                area_name = str(area.get("name", "") or "").strip()
                scale_from = ScaleConverter.normalize_p2p_scale_value(
                    area.get("scaleFrom")
                )
                scale_to = ScaleConverter.normalize_p2p_scale_value(area.get("scaleTo"))
                range_text = ScaleConverter.format_p2p_scale_range(scale_from, scale_to)
                emoji = ScaleConverter.get_p2p_scale_emoji(scale_from, scale_to)

                max_area_scale = (
                    max(value for value in (scale_from, scale_to) if value is not None)
                    if scale_from is not None or scale_to is not None
                    else None
                )

                if area_name and max_area_scale is not None and max_area_scale >= 45:
                    kind = str(area.get("kindCode", "") or "").strip()
                    status = "已到达" if kind == "11" else "未到达"
                    area_parts = [status]
                    if range_text:
                        area_parts.append(f"震度{range_text}")
                    warning_areas.append(f"{emoji}{area_name}({'・'.join(area_parts)})")

                if range_text and range_text not in warning_area_ranges:
                    warning_area_ranges.append(range_text)

            source_entry = get_source_entry(self.source_id)
            metadata = {
                "source_family": "p2p",
                "source_enum": source_entry.source_enum if source_entry else "",
                "source_type": source_entry.source_type.value
                if source_entry
                else "earthquake_warning",
                "serial": issue_info.get("serial", ""),
                "report_num": report_num,
                "is_final": bool(data.get("is_final", False)),
                "is_cancel": is_cancelled,
                "info_type": "警报",
                "is_training": bool(is_test),
                "is_assumption": bool(is_plum),
                "jma_warning_areas": warning_areas,
                "jma_warning_area_ranges": warning_area_ranges,
            }
            domain_event = EarthquakeEvent(
                occurred_at=shock_time,
                latitude=safe_float_convert(hypocenter.get("latitude")),
                longitude=safe_float_convert(hypocenter.get("longitude")),
                depth=safe_float_convert(hypocenter.get("depth")),
                magnitude=safe_float_convert(hypocenter.get("magnitude")),
                place_name=str(hypocenter.get("name", "未知地点") or "未知地点"),
                scale=scale,
                metadata=dict(metadata),
            )
            identity = EventIdentity(
                event_id=str(issue_info.get("eventId", "") or data.get("id", "") or ""),
                source_id=self.source_id,
                event_type="earthquake_warning",
                provider_family=source_entry.provider_family.value
                if source_entry
                else "p2p",
                source_enum=source_entry.source_enum if source_entry else "",
                report_num=report_num,
                published_at=shock_time,
                is_final=bool(metadata.get("is_final", False)),
                aliases=tuple(
                    item for item in (str(data.get("id", "") or "").strip(),) if item
                ),
                attributes={
                    "parser_name": self.source_entry.parser_name
                    if self.source_entry
                    else "",
                    "config_key": source_entry.config_key if source_entry else "",
                },
            )
            envelope = EventEnvelope(
                identity=identity,
                event=domain_event,
                received_at=datetime.now(timezone.utc),
                payload=SourcePayload(
                    source_id=self.source_id,
                    provider_family=source_entry.provider_family.value
                    if source_entry
                    else "p2p",
                    message_type=str(data.get("code") or "556").strip(),
                    raw=dict(data),
                    attributes=dict(metadata),
                ),
                metadata=metadata,
            )

            logger.info(
                f"[灾害预警] 地震预警解析成功: {domain_event.place_name} (M {domain_event.magnitude}), 时间: {domain_event.occurred_at}"
            )

            return envelope
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 解析EEW数据失败: {exc}")
            return None


class JmaEewWolfxParser(BaseParser):
    """日本气象厅紧急地震速报解析器 - Wolfx。"""

    def __init__(self, message_logger=None):
        """初始化 Wolfx 日本预警解析器。"""
        super().__init__("jma_wolfx", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析 Wolfx 日本地震预警数据。"""
        try:
            # Wolfx 会混发多类日本消息，这里只接收日本地震预警类型。
            if data.get("type") != "jma_eew":
                logger.debug(f"[灾害预警] {self.source_id} 非 JMA 地震预警数据，跳过")
                return None

            report_num = (
                data.get("Serial", 1) if isinstance(data.get("Serial"), int) else 1
            )
            warn_area = data.get("WarnArea", {})
            jma_warn_area = ""
            warning_area_ranges: list[str] = []
            if isinstance(warn_area, dict):
                jma_warn_area = str(warn_area.get("Chiiki", "") or "").strip()
                shindo1 = warn_area.get("Shindo1")
                shindo2 = warn_area.get("Shindo2")
                if shindo1:
                    range_text = f"{shindo1}"
                    if shindo2 and shindo2 != shindo1:
                        range_text += f" ～ {shindo2}"
                    warning_area_ranges.append(range_text)

            source_entry = get_source_entry(self.source_id)
            metadata = {
                "source_family": "wolfx",
                "source_enum": source_entry.source_enum if source_entry else "",
                "source_type": source_entry.source_type.value
                if source_entry
                else "earthquake_warning",
                "report_num": report_num,
                "is_final": bool(data.get("isFinal", False)),
                "is_cancel": bool(data.get("isCancel", False)),
                "info_type": data.get("WarnArea", {}).get("Type", "")
                if isinstance(data.get("WarnArea"), dict)
                else "",
                "is_training": bool(data.get("isTraining", False)),
                "is_assumption": bool(data.get("isAssumption", False)),
                "is_sea": bool(data.get("isSea", False)),
                "jma_warn_area": jma_warn_area,
                "jma_warning_areas": [jma_warn_area] if jma_warn_area else [],
                "jma_warning_area_ranges": warning_area_ranges,
            }
            domain_event = EarthquakeEvent(
                occurred_at=self._parse_datetime(data.get("OriginTime", "")),
                latitude=safe_float_convert(data.get("Latitude")),
                longitude=safe_float_convert(data.get("Longitude")),
                depth=safe_float_convert(data.get("Depth")),
                magnitude=safe_float_convert(
                    data.get("Magunitude") or data.get("Magnitude")
                ),
                place_name=str(data.get("Hypocenter", "") or ""),
                scale=ScaleConverter.parse_jma_cwa_scale(data.get("MaxIntensity", "")),
                metadata=dict(metadata),
            )
            identity = EventIdentity(
                event_id=str(data.get("EventID", "") or ""),
                source_id=self.source_id,
                event_type="earthquake_warning",
                provider_family=source_entry.provider_family.value
                if source_entry
                else "wolfx",
                source_enum=source_entry.source_enum if source_entry else "",
                report_num=report_num,
                published_at=domain_event.occurred_at,
                is_final=bool(metadata.get("is_final", False)),
                aliases=tuple(
                    item
                    for item in (str(data.get("EventID", "") or "").strip(),)
                    if item
                ),
                attributes={
                    "parser_name": self.source_entry.parser_name
                    if self.source_entry
                    else "",
                    "config_key": source_entry.config_key if source_entry else "",
                },
            )
            envelope = EventEnvelope(
                identity=identity,
                event=domain_event,
                received_at=datetime.now(timezone.utc),
                payload=SourcePayload(
                    source_id=self.source_id,
                    provider_family=source_entry.provider_family.value
                    if source_entry
                    else "wolfx",
                    message_type=str(data.get("type") or "jma_eew").strip(),
                    raw=dict(data),
                    attributes=dict(metadata),
                ),
                metadata=metadata,
            )

            logger.info(
                f"[灾害预警] 地震预警解析成功: {domain_event.place_name} (M {domain_event.magnitude}), 时间: {domain_event.occurred_at}"
            )

            return envelope
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {exc}")
            return None
