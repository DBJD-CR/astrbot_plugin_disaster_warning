"""
统一解析器抽象定义。
负责提供原始消息解码、心跳识别、告警去重与时间解析等通用能力，
避免各具体解析器重复实现相同基础逻辑。
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ...utils.time_converter import TimeConverter
from ..sources.source_catalog import get_source_entry


class BaseParser:
    """统一解析器基类。"""

    def __init__(self, source_id: str, message_logger=None):
        """初始化解析器共享状态与运行时缓存。"""
        self.source_id = source_id
        self.source_entry = get_source_entry(source_id)
        self.source_config = self.source_entry
        self.message_logger = message_logger
        self._last_heartbeat_check: dict[str, float] = {}
        self._heartbeat_patterns = {
            "empty_coordinates": {"latitude": 0, "longitude": 0},
            "empty_fields": ["", None, {}],
        }
        self._warning_cache: dict[str, tuple[float, str]] = {}
        self._warning_cache_timeout = 3600

    def parse_message(self, message: str | bytes) -> Any | None:
        """解析原始消息。"""
        try:
            # 统一先做解码，再交给领域事件构建入口，便于子类按需覆写其中某一步。
            payload = self.decode_message(message)
            return self.build_event(payload)
        except json.JSONDecodeError as exc:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {exc}")
            return None
        except Exception as exc:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {exc}")
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")
            return None

    def decode_message(self, message: str | bytes) -> Any:
        """解码原始消息。"""
        if isinstance(message, bytes):
            return message
        return json.loads(message)

    def parse_payload(self, payload: Any):
        """将原始载荷解析为领域事件。"""
        if isinstance(payload, bytes):
            return self._parse_binary_data(payload)
        if not isinstance(payload, dict):
            return None
        return self._parse_data(payload)

    def build_event(self, payload: Any):
        """统一事件构建入口。"""
        return self.parse_payload(payload)

    def _parse_binary_data(self, payload: bytes) -> Any | None:
        """解析二进制载荷，基类默认不支持。"""
        return None

    def _extract_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """提取实际业务数据，兼容多种外层包装格式。"""
        if "Data" in data:
            logger.debug(f"[灾害预警] {self.source_id} 使用 Data 字段获取数据")
            return data["Data"] or {}
        if "data" in data:
            logger.debug(f"[灾害预警] {self.source_id} 使用 data 字段获取数据")
            return data["data"] or {}
        logger.debug(f"[灾害预警] {self.source_id} 使用整个消息作为数据")
        return data

    def _is_heartbeat_message(self, msg_data: dict[str, Any]) -> bool:
        """检测是否为心跳包或空载荷。"""
        current_time = time.time()
        cache_key = f"{self.source_id}_last_check"

        # 心跳检测本身也做节流，避免在高频数据流中反复执行同类检查。
        if cache_key in self._last_heartbeat_check:
            if current_time - self._last_heartbeat_check[cache_key] < 30:
                return False

        self._last_heartbeat_check[cache_key] = current_time

        if "latitude" in msg_data and "longitude" in msg_data:
            lat = msg_data.get("latitude")
            lon = msg_data.get("longitude")
            if lat == 0 and lon == 0:
                logger.debug(
                    f"[灾害预警] {self.source_id} 检测到空坐标心跳包，静默过滤"
                )
                return True

        # 某些数据源缺少关键字段时，通常也是一种无业务意义的占位心跳。
        critical_fields = {
            "usgs_fanstudio": ["id", "magnitude", "placeName"],
            "china_tsunami_fanstudio": ["warningInfo", "code", "timeInfo"],
            "china_weather_fanstudio": ["title", "description"],
        }

        if self.source_id in critical_fields:
            required_fields = critical_fields[self.source_id]
            missing_count = 0

            for field in required_fields:
                field_value = msg_data.get(field)
                if field_value in self._heartbeat_patterns["empty_fields"]:
                    missing_count += 1

            if missing_count >= len(required_fields) / 2:
                logger.debug(
                    f"[灾害预警] {self.source_id} 检测到空数据心跳包，静默过滤"
                )
                return True

        return False

    def _should_log_warning(self, warning_type: str, message: str) -> bool:
        """判断是否应该记录警告，避免重复刷同类日志。"""
        current_time = time.time()
        cache_key = f"{self.source_id}_{warning_type}"

        if cache_key in self._warning_cache:
            last_time, last_message = self._warning_cache[cache_key]
            if (
                current_time - last_time < self._warning_cache_timeout
                and last_message == message
            ):
                return False

        self._warning_cache[cache_key] = (current_time, message)
        return True

    def _parse_data(self, data: dict[str, Any]) -> Any | None:
        """解析业务数据，具体由子类实现。"""
        raise NotImplementedError

    def _parse_datetime(self, time_str: str) -> datetime | None:
        """解析时间字符串。"""
        dt = TimeConverter.parse_datetime(time_str)
        if dt is None and time_str:
            logger.warning(f"[灾害预警] 时间解析失败: '{time_str}'")
        return dt
