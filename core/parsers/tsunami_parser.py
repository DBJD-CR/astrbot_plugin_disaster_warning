"""
海啸解析器。
负责把中国海啸预警与日本海啸预报数据统一转换为领域事件。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from ..domain.event_identity import EventIdentity
from ..domain.event_models import EventEnvelope, TsunamiEvent
from ..domain.event_payload import SourcePayload
from ..sources.source_catalog import get_source_entry
from .base_parser import BaseParser


class TsunamiParser(BaseParser):
    """中国海啸预警解析器。"""

    def __init__(self, message_logger=None):
        """初始化中国海啸预警解析器。"""
        super().__init__("china_tsunami_fanstudio", message_logger)

    def _build_envelope(self, tsunami_data: dict[str, Any]) -> EventEnvelope | None:
        """把海啸原始字典封装为统一事件包裹体。"""
        # 兼容各不同子属性块
        warning_info = tsunami_data.get("warningInfo", {}) or {}
        time_info = tsunami_data.get("timeInfo", {}) or {}
        default_shock_info = tsunami_data.get("shockInfo")
        # 兼容无嵌套属性的直接取值
        shock_info = default_shock_info if isinstance(default_shock_info, dict) else {}
        details = tsunami_data.get("details", {}) or {}

        # 兼容三种不同的发震、更新与发布时间键名
        issue_time_str = (
            time_info.get("alarmDate")
            or time_info.get("issueTime")
            or time_info.get("publishTime")
            or time_info.get("updateDate")
            or ""
        )
        update_time_str = time_info.get("updateDate") or ""
        shock_time_str = shock_info.get("shockTime") or ""

        # 解析时间字符串为日期对象
        issue_time = (
            self._parse_datetime(issue_time_str)
            if issue_time_str
            else datetime.now(timezone.utc)
        )
        update_time = self._parse_datetime(update_time_str) if update_time_str else None
        shock_time = self._parse_datetime(shock_time_str) if shock_time_str else None

        level = (warning_info.get("level") or tsunami_data.get("level") or "").strip()
        title = (warning_info.get("title") or tsunami_data.get("title") or "").strip()

        # 根据海啸警报级别自动归纳缺省的展示标题
        if not title and level:
            if level == "信息":
                title = "海啸信息"
            elif level == "解除":
                title = "海啸解除通告"
            else:
                title = f"海啸{level}警报"

        # 若依然缺失标题，视为无法解析，打印节流警告后返回 None
        if not title:
            warning_msg = f"[灾害预警] {self.source_id} 海啸消息缺少标题，跳过处理"
            if self._should_log_warning("missing_tsunami_title", warning_msg):
                logger.debug(warning_msg)
            return None

        # 收集预报地区列表、海啸波位水位监测站及分布图附件
        forecasts = tsunami_data.get("forecasts", []) or []
        monitoring_stations = (
            tsunami_data.get("waterLevelMonitoring")
            or tsunami_data.get("monitoringStations")
            or []
        )
        maps = details.get("maps", {}) or {}

        event_id = str(tsunami_data.get("id", "") or "").strip()
        # 缺失 Event ID 时根据海啸报文特征（编号、批次、发布时间等）拼合出回退 ID
        if not event_id:
            stable_parts = [
                str(tsunami_data.get("code", "") or "").strip(),
                str(details.get("batch") or tsunami_data.get("batch") or "").strip(),
                str(title or "").strip(),
                str(issue_time_str or "").strip(),
            ]
            stable_parts = [part for part in stable_parts if part]
            event_id = (
                "tsunami_" + "|".join(stable_parts)
                if stable_parts
                else "tsunami_unknown"
            )
            logger.debug(
                f"[灾害预警] {self.source_id} 海啸消息缺少稳定id，已使用回退事件ID: {event_id}"
            )

        # 整理副标题与发布机构名称
        subtitle = (
            warning_info.get("subtitle")
            or warning_info.get("caption")
            or shock_info.get("placeName")
            or tsunami_data.get("placeName")
            or ""
        )
        org_unit = (
            warning_info.get("orgUnit")
            or tsunami_data.get("publishInfo", {}).get("unitName")
            or "中国自然资源部海啸预警中心"
        )

        normalized_level = level.replace("级", "") if level else ""
        message_type = "info"
        if normalized_level and normalized_level not in {"信息"}:
            message_type = "warning"
        if "警报" in title or "预警" in title:
            message_type = "warning"

        source_entry = get_source_entry(self.source_id)
        metadata = {
            "code": tsunami_data.get("code", ""),
            "subtitle": subtitle,
            "org_unit": org_unit,
            "update_time": update_time,
            "shock_time": shock_time,
            "message_type": message_type,
            "place_name": shock_info.get("placeName") or tsunami_data.get("placeName"),
            "latitude": shock_info.get("latitude") or tsunami_data.get("latitude"),
            "longitude": shock_info.get("longitude") or tsunami_data.get("longitude"),
            "depth": shock_info.get("depth") or tsunami_data.get("depth"),
            "magnitude": shock_info.get("magnitude") or tsunami_data.get("magnitude"),
            "batch": details.get("batch") or tsunami_data.get("batch"),
            "forecasts": forecasts,
            "monitoring_stations": monitoring_stations,
            "estimated_arrival_time": tsunami_data.get("estimatedArrivalTime"),
            "max_wave_height": tsunami_data.get("maxWaveHeight"),
            "details_url": details.get("htmlUrl") or tsunami_data.get("htmlUrl"),
            "map_urls": {
                "earthquake": maps.get("earthquakeMapUrl", ""),
                "amplitude": maps.get("amplitudeMapUrl", ""),
                "coastal": maps.get("coastalMapUrl", ""),
            },
            "source_family": "fan_studio",
            "source_enum": source_entry.source_enum if source_entry else "",
            "source_type": source_entry.source_type.value
            if source_entry
            else "tsunami",
        }

        # 实例化海啸领域模型
        domain_event = TsunamiEvent(
            title=title,
            level=level,
            issued_at=issue_time,
            metadata=dict(metadata),
        )

        # 构造事件身份对象
        identity = EventIdentity(
            event_id=event_id,
            source_id=self.source_id,
            event_type="tsunami",
            provider_family=source_entry.provider_family.value
            if source_entry
            else "fan_studio",
            source_enum=source_entry.source_enum if source_entry else "",
            published_at=issue_time,
            aliases=tuple(
                item
                for item in (str(tsunami_data.get("id", "") or "").strip(),)
                if item
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
                message_type=str(tsunami_data.get("type") or message_type).strip(),
                raw=dict(tsunami_data),
                attributes=dict(metadata),
            ),
            metadata=metadata,
        )

    def _parse_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析中国海啸预警数据。"""
        try:
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            if self._is_heartbeat_message(msg_data):
                return None

            # 支持列表和单对象两种封装形态
            events = []
            if isinstance(msg_data, dict):
                events = [msg_data]
            elif isinstance(msg_data, list):
                events = msg_data

            if not events:
                return None

            envelope = self._build_envelope(events[0])
            if envelope is None:
                return None

            logger.info(
                f"[灾害预警] 海啸预警解析成功: {getattr(envelope.event, 'title', '')} ({getattr(envelope.event, 'level', '')}), 发布时间: {getattr(envelope.event, 'issued_at', None)}"
            )
            return envelope
        except Exception as exc:
            logger.error(
                f"[灾害预警] {self.source_id} 解析海啸预警数据失败: {exc}, 数据内容: {data}"
            )
            return None


class JmaTsunamiP2PParser(BaseParser):
    """日本气象厅海啸预报解析器，处理 P2P 来源数据。"""

    def __init__(self, message_logger=None):
        """初始化 P2P 日本海啸预报解析器。"""
        super().__init__("jma_tsunami_p2p", message_logger)

    def parse_message(self, message: str) -> EventEnvelope | None:
        """解析 P2P 海啸消息。"""
        try:
            data = json.loads(message)
            code = data.get("code")

            # P2P 中 552 业务码专指日本津波予報（海啸警报），其余直接跳过
            if code == 552:
                logger.debug(f"[灾害预警] {self.source_id} 收到津波予報(code:552)")
                return self._parse_tsunami_data(data)

            logger.debug(f"[灾害预警] {self.source_id} 非海啸数据，code: {code}")
            return None
        except json.JSONDecodeError as exc:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {exc}")
            return None

    def _parse_tsunami_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析 P2P 海啸数据。"""
        try:
            issue = data.get("issue", {})
            areas = data.get("areas", [])
            cancelled = data.get("cancelled", False)

            # 日本海啸按等级高低依次划分为：MajorWarning（大津波警报）、Warning（津波警报）、Watch（注意报）、None、Unknown
            max_grade = "Unknown"
            if cancelled:
                max_grade = "解除"
                title = "津波予報（解除）"
            else:
                grades = ["None", "Unknown", "Watch", "Warning", "MajorWarning"]
                max_grade_idx = 0
                for area in areas:
                    grade = area.get("grade", "Unknown")
                    if grade in grades:
                        idx = grades.index(grade)
                        # 在所有受影响的海域中找出最严重的警报类型作为主标题
                        if idx > max_grade_idx:
                            max_grade_idx = idx
                            max_grade = grade

                title_map = {
                    "MajorWarning": "大津波警報",
                    "Warning": "津波警報",
                    "Watch": "津波注意報",
                    "Unknown": "津波予報",
                }
                title = title_map.get(max_grade, "津波予報")

            issue_time_raw = issue.get("time") or data.get("time") or ""
            issue_time = self._parse_datetime(issue_time_raw)
            source_entry = get_source_entry(self.source_id)
            metadata = {
                "source_family": "p2p",
                "source_enum": source_entry.source_enum if source_entry else "",
                "source_type": source_entry.source_type.value
                if source_entry
                else "tsunami",
                "code": str(data.get("code", 552)),
                "org_unit": "日本气象厅",
                "forecasts": areas,
            }

            # 使用发布时间、标题等构造回退 ID
            event_id = str(data.get("id", "") or data.get("_id", "") or "").strip()
            if not event_id:
                stable_parts = [
                    str(data.get("code", "") or "").strip(),
                    str(title or "").strip(),
                    str(issue_time_raw or "").strip(),
                ]
                stable_parts = [part for part in stable_parts if part]
                event_id = (
                    "jma_tsunami_" + "|".join(stable_parts)
                    if stable_parts
                    else "jma_tsunami_unknown"
                )

            # 构造海啸领域模型
            domain_event = TsunamiEvent(
                title=title,
                level=max_grade,
                issued_at=issue_time,
                metadata=dict(metadata),
            )

            # 构建唯一的身份标识
            identity = EventIdentity(
                event_id=event_id,
                source_id=self.source_id,
                event_type="tsunami",
                provider_family=source_entry.provider_family.value
                if source_entry
                else "p2p",
                source_enum=source_entry.source_enum if source_entry else "",
                published_at=issue_time,
                attributes={
                    "parser_name": self.source_entry.parser_name
                    if self.source_entry
                    else "",
                    "config_key": source_entry.config_key if source_entry else "",
                },
            )

            # 包装并返回统一包裹层
            envelope = EventEnvelope(
                identity=identity,
                event=domain_event,
                received_at=datetime.now(timezone.utc),
                payload=SourcePayload(
                    source_id=self.source_id,
                    provider_family=source_entry.provider_family.value
                    if source_entry
                    else "p2p",
                    message_type=str(data.get("code", 552)),
                    raw=dict(data),
                    attributes=dict(metadata),
                ),
                metadata=metadata,
            )

            logger.info(
                f"[灾害预警] JMA海啸预报解析成功: {domain_event.title}, 时间: {domain_event.issued_at}"
            )

            return envelope
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 解析海啸数据失败: {exc}")
            return None
