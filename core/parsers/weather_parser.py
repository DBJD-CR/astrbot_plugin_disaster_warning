"""
气象预警解析器。
负责把中国气象局来源的气象预警消息转换为统一领域事件。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...utils.plugin_logger import plugin_logger
from ..domain.event_identity import EventIdentity
from ..domain.event_models import EventEnvelope, WeatherEvent
from ..domain.event_payload import SourcePayload
from ..services.weather import BoundedTTLSet, normalize_weather_warning_code
from ..sources.source_catalog import get_source_entry
from .base_parser import BaseParser


def _extract_issue_time(
    event_id: object, effective_time: datetime | None
) -> datetime | None:
    """Extract the encoded issue timestamp, falling back to effective time."""
    event_id_text = str(event_id or "")
    if "_" not in event_id_text:
        return effective_time

    time_part = event_id_text.rsplit("_", 1)[-1]
    if len(time_part) < 12:
        return effective_time
    try:
        year = int(time_part[0:4])
        month = int(time_part[4:6])
        day = int(time_part[6:8])
        hour = int(time_part[8:10])
        minute = int(time_part[10:12])
        second = int(time_part[12:14]) if len(time_part) >= 14 else 0
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return effective_time


class WeatherAlarmParser(BaseParser):
    """中国气象局气象预警解析器。"""

    def __init__(self, message_logger=None):
        """初始化气象预警解析器与短期重复记录缓存。"""
        super().__init__("china_weather_fanstudio", message_logger)
        self._processed_weather_ids = BoundedTTLSet(
            ttl_seconds=86_400,
            max_entries=4_096,
        )

    def _parse_data(self, data: dict[str, Any]) -> EventEnvelope | None:
        """解析中国气象局气象预警数据。"""
        try:
            # 提取数据负载中的实际业务字段
            msg_data = self._extract_data(data)
            if not msg_data:
                plugin_logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 过滤心跳包
            if self._is_heartbeat_message(msg_data):
                return None

            # 内存中判定当前事件ID是否已被处理过，避免同一预警短时多次派发
            # 这里也属于去重阶段的日志，如果提示检测到重复，应由 plugin_logger 输出
            weather_id = msg_data.get("id")
            if weather_id and weather_id in self._processed_weather_ids:
                plugin_logger.info(
                    f"[灾害预警] {self.source_id} 检测到重复的气象预警ID: {weather_id}，忽略",
                    is_event_linked=True,
                )
                return None

            # 对数据源字段完整性做检查，缺失关键字段时记录 debug 方便诊断
            required_fields = ["id", "effective", "description"]
            missing_fields = [
                field
                for field in required_fields
                if field not in msg_data or msg_data[field] is None
            ]
            if missing_fields:
                plugin_logger.debug(
                    f"[灾害预警] {self.source_id} 气象预警数据缺少关键字段: {missing_fields}"
                )

            effective_time = self._parse_datetime(msg_data.get("effective", ""))

            # 预警发布时间优先尝试从标识尾部编码中提取，失败时回退到生效时间。
            issue_time = _extract_issue_time(msg_data.get("id"), effective_time)

            headline = msg_data.get("headline", "")
            title = msg_data.get("title", "") or headline
            description = msg_data.get("description", "")

            # 评估是否有实质展示意义：若标题、名称与具体描述全部缺失，判定为垃圾或测试消息，直接略过
            if not title and not headline and not description:
                if not self._is_heartbeat_message(msg_data):
                    warning_msg = f"[灾害预警] {self.source_id} 气象预警缺少标题、名称和描述信息，跳过处理"
                    if self._should_log_warning("missing_weather_fields", warning_msg):
                        plugin_logger.debug(warning_msg)
                return None

            source_entry = get_source_entry(self.source_id)

            # 多重回退以解析气象编码
            source_weather_code = str(
                msg_data.get("weather_type")
                or msg_data.get("weatherType")
                or msg_data.get("alertCode")
                or msg_data.get("alert_code")
                or msg_data.get("code")
                or msg_data.get("type")
                or ""
            ).strip()
            weather_code = normalize_weather_warning_code(
                source_weather_code,
                title,
                headline,
                description,
            )
            if weather_code != source_weather_code:
                plugin_logger.warning(
                    f"[灾害预警] 已纠正冲突的气象预警编码: "
                    f"{source_weather_code} -> {weather_code}",
                    is_event_linked=True,
                )

            # 整合元数据
            metadata = {
                "issue_time": issue_time,
                "weather_type": weather_code,
                "weather_code": weather_code,
                "type": weather_code,
                "alert_code": weather_code,
                "code": weather_code,
                "longitude": msg_data.get("longitude"),
                "latitude": msg_data.get("latitude"),
                "title": title,
                "headline": headline,
                "description": description,
                "source_family": "fan_studio",
                "source_enum": source_entry.source_enum if source_entry else "",
                "source_type": source_entry.source_type.value
                if source_entry
                else "weather",
            }

            # 实例化气象领域模型
            event_id = str(msg_data.get("id", "") or "")
            domain_event = WeatherEvent(
                title=title,
                headline=headline,
                effective_at=effective_time,
                metadata=dict(metadata),
            )

            # 构造身份标识
            identity = EventIdentity(
                event_id=event_id,
                source_id=self.source_id,
                event_type="weather_alarm",
                provider_family=source_entry.provider_family.value
                if source_entry
                else "fan_studio",
                source_enum=source_entry.source_enum if source_entry else "",
                published_at=issue_time or effective_time,
                attributes={
                    "parser_name": self.source_entry.parser_name
                    if self.source_entry
                    else "",
                    "config_key": source_entry.config_key if source_entry else "",
                },
            )

            # 装配统一事件包裹
            envelope = EventEnvelope(
                identity=identity,
                event=domain_event,
                payload=SourcePayload(
                    source_id=self.source_id,
                    provider_family=source_entry.provider_family.value
                    if source_entry
                    else "fan_studio",
                    message_type=str(msg_data.get("type") or "weatheralert").strip(),
                    raw=dict(msg_data),
                    attributes=dict(metadata),
                ),
                metadata=metadata,
            )

            # 加入防重去噪缓存中
            if event_id:
                self._processed_weather_ids.add(event_id)

            plugin_logger.info(
                f"[灾害预警] 气象预警解析成功: {domain_event.title or domain_event.headline}, 生效时间: {issue_time}",
                is_event_linked=True,
            )

            return envelope
        except Exception as exc:
            plugin_logger.error(
                f"[灾害预警] {self.source_id} 解析气象预警数据失败: {exc}, 数据内容: {data}"
            )
            return None
