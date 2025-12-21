"""
基础数据处理器
提供所有数据处理器的基类和通用功能
"""

import json
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ...models.data_source_config import get_data_source_config
from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)


def _safe_float_convert(value) -> float | None:
    """安全地将值转换为浮点数"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            return None
    return None


class BaseDataHandler:
    """基础数据处理器 - 重构版本"""

    def __init__(self, source_id: str, message_logger=None):
        self.source_id = source_id
        self.source_config = get_data_source_config(source_id)
        self.message_logger = message_logger
        # 添加心跳包检测缓存
        self._last_heartbeat_check = {}
        self._heartbeat_patterns = {
            "empty_coordinates": {"latitude": 0, "longitude": 0},
            "empty_fields": ["", None, {}],
        }
        # 添加重复警告检测缓存
        self._warning_cache = {}
        self._warning_cache_timeout = 3600  # 1小时内不重复相同的警告

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析消息 - 基础方法"""
        # 仅使用AstrBot logger进行调试日志，不再重复记录到消息记录器
        # WebSocket管理器已经记录了原始消息，包含更详细的连接信息
        logger.debug(f"[{self.source_id}] 收到原始消息，长度: {len(message)}")

        try:
            data = json.loads(message)
            return self._parse_data(data)
        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {e}")
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")
            return None

    def _is_heartbeat_message(self, msg_data: dict[str, Any]) -> bool:
        """检测是否为心跳包或无效数据，msg_data 是提取后的实际数据。"""

        current_time = time.time()
        cache_key = f"{self.source_id}_last_check"

        # 检查是否在短时间内重复检测
        if cache_key in self._last_heartbeat_check:
            if (
                current_time - self._last_heartbeat_check[cache_key] < 30
            ):  # 30秒内不重复检测
                return False

        self._last_heartbeat_check[cache_key] = current_time

        # 检测空坐标数据
        if "latitude" in msg_data and "longitude" in msg_data:
            lat = msg_data.get("latitude")
            lon = msg_data.get("longitude")
            if lat == 0 and lon == 0:
                logger.debug(
                    f"[灾害预警] {self.source_id} 检测到空坐标心跳包，静默过滤"
                )
                return True

        # 检测缺少关键字段的空数据
        critical_fields = {
            "usgs_fanstudio": ["id", "magnitude", "placeName"],
            "china_tsunami_fanstudio": ["warningInfo", "title", "level"],
            "china_weather_fanstudio": ["headline", "description"],
        }

        if self.source_id in critical_fields:
            required_fields = critical_fields[self.source_id]
            missing_count = 0

            for field in required_fields:
                field_value = msg_data.get(field)
                if field_value in self._heartbeat_patterns["empty_fields"]:
                    missing_count += 1

            # 如果超过一半的关键字段为空，认为是心跳包
            if missing_count >= len(required_fields) / 2:
                logger.debug(
                    f"[灾害预警] {self.source_id} 检测到空数据心跳包，静默过滤"
                )
                return True

        return False

    def _should_log_warning(self, warning_type: str, message: str) -> bool:
        """判断是否应该记录警告（避免重复警告）"""

        current_time = time.time()
        cache_key = f"{self.source_id}_{warning_type}"

        if cache_key in self._warning_cache:
            last_time, last_message = self._warning_cache[cache_key]
            # 如果在缓存时间内且消息相同，不记录
            if (
                current_time - last_time < self._warning_cache_timeout
                and last_message == message
            ):
                return False

        # 更新缓存
        self._warning_cache[cache_key] = (current_time, message)
        return True

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析数据 - 子类实现"""
        raise NotImplementedError

    def _parse_datetime(self, time_str: str) -> datetime | None:
        """解析时间字符串"""
        if not time_str or not isinstance(time_str, str):
            return None

        # 首先尝试ISO 8601格式（带T分隔符和Z时区）
        if "T" in time_str:
            try:
                # 处理 '2025-12-20T16:36:55.629Z' 格式
                clean_str = time_str.replace("Z", "+00:00")
                return datetime.fromisoformat(clean_str)
            except ValueError:
                pass

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str.strip(), fmt)
            except ValueError:
                continue

        logger.warning(f"[灾害预警] 时间解析失败，返回None: '{time_str}'")
        return None

    def _safe_float_convert(self, value) -> float | None:
        """安全地将值转换为浮点数"""
        return _safe_float_convert(value)
