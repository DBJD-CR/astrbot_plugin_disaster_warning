"""
气象预警处理器
包含中国气象局相关处理器
"""

from collections import deque
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    WeatherAlarmData,
)
from .base import BaseDataHandler


class WeatherAlarmHandler(BaseDataHandler):
    """中国气象局气象预警处理器"""

    def __init__(self, message_logger=None):
        super().__init__("china_weather_fanstudio", message_logger)
        # 缓存最近处理过的预警ID，防止重连后重复推送
        # 使用deque自动维护固定长度，maxlen=10应该足够覆盖短时间内的重复
        self._processed_weather_ids = deque(maxlen=10)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国气象局气象预警数据"""
        try:
            # 获取实际数据 - 兼容多种格式
            msg_data = data.get("Data", {}) or data.get("data", {}) or data
            if not msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 记录数据获取情况用于调试
            if "Data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用Data字段获取数据")
            elif "data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用data字段获取数据")
            else:
                logger.debug(f"[灾害预警] {self.source_id} 使用整个消息作为数据")

            # 心跳包检测 - 在详细处理前进行快速过滤
            if self._is_heartbeat_message(msg_data):
                return None

            # 去重检查
            weather_id = msg_data.get("id")
            if weather_id and weather_id in self._processed_weather_ids:
                logger.debug(
                    f"[灾害预警] {self.source_id} 检测到重复的气象预警ID: {weather_id}，忽略"
                )
                return None

            # 检查关键字段
            required_fields = ["id", "headline", "effective", "description"]
            missing_fields = [
                field
                for field in required_fields
                if field not in msg_data or msg_data[field] is None
            ]
            if missing_fields:
                logger.debug(
                    f"[灾害预警] {self.source_id} 气象预警数据缺少关键字段: {missing_fields}"
                )

            # 提取真实的生效时间
            effective_time = self._parse_datetime(msg_data.get("effective", ""))

            # 尝试从ID中提取生效时间
            issue_time = None
            id_str = msg_data.get("id", "")
            if "_" in id_str:
                time_part = id_str.split("_")[-1]
                if len(time_part) >= 12:
                    try:
                        year = int(time_part[0:4])
                        month = int(time_part[4:6])
                        day = int(time_part[6:8])
                        hour = int(time_part[8:10])
                        minute = int(time_part[10:12])
                        second = int(time_part[12:14]) if len(time_part) >= 14 else 0
                        issue_time = datetime(year, month, day, hour, minute, second)
                    except (ValueError, IndexError):
                        issue_time = effective_time
                else:
                    issue_time = effective_time
            else:
                issue_time = effective_time

            # 验证关键字段，防止空信息推送
            headline = msg_data.get("headline", "")
            title = msg_data.get("title", "")
            description = msg_data.get("description", "")

            if not headline and not title and not description:
                # 只有在非心跳包情况下才记录
                if not self._is_heartbeat_message(msg_data):
                    warning_msg = f"[灾害预警] {self.source_id} 气象预警缺少标题、名称和描述信息，跳过处理"
                    if self._should_log_warning("missing_weather_fields", warning_msg):
                        logger.debug(warning_msg)
                return None

            weather = WeatherAlarmData(
                id=msg_data.get("id", ""),
                source=DataSource.FAN_STUDIO_WEATHER,
                headline=headline,
                title=title,
                description=description,
                type=msg_data.get("type", ""),
                effective_time=effective_time,
                issue_time=issue_time,
                longitude=msg_data.get("longitude"),
                latitude=msg_data.get("latitude"),
                raw_data=msg_data,
            )

            # 记录ID到缓存
            if weather.id:
                self._processed_weather_ids.append(weather.id)

            logger.debug(
                f"[灾害预警] 气象预警解析成功: {weather.headline}, 生效时间: {weather.issue_time}"
            )

            return DisasterEvent(
                id=weather.id,
                data=weather,
                source=weather.source,
                disaster_type=weather.disaster_type,
            )
        except Exception as e:
            logger.error(
                f"[灾害预警] {self.source_id} 解析气象预警数据失败: {e}, 数据内容: {data}"
            )
            return None
