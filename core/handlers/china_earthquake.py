"""
中国地震情报处理器
包含 CENC (中国地震台网) 地震测定相关处理器
"""

from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)
from .base import BaseDataHandler


class CENCEarthquakeHandler(BaseDataHandler):
    """中国地震台网地震测定处理器 - FAN Studio"""

    def __init__(self, message_logger=None):
        super().__init__("cenc_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国地震台网数据"""
        try:
            # 获取实际数据 - 兼容多种格式
            msg_data = data.get("Data", {}) or data.get("data", {}) or data
            if not msg_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 记录数据获取情况用于调试
            if "Data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用Data字段获取数据")
            elif "data" in data:
                logger.debug(f"[灾害预警] {self.source_id} 使用data字段获取数据")
            else:
                logger.debug(f"[灾害预警] {self.source_id} 使用整个消息作为数据")

            # 检查是否为CENC地震测定数据
            if "infoTypeName" not in msg_data or "eventId" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非CENC地震测定数据，跳过")
                return None

            # 优化USGS数据精度 - 四舍五入到1位小数
            magnitude = self._safe_float_convert(msg_data.get("magnitude"))
            if magnitude is not None:
                magnitude = round(magnitude, 1)

            depth = self._safe_float_convert(msg_data.get("depth"))
            if depth is not None:
                depth = round(depth, 1)

            earthquake = EarthquakeData(
                id=str(msg_data.get("id", "")),
                event_id=msg_data.get("eventId", ""),
                source=DataSource.FAN_STUDIO_CENC,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(msg_data.get("shockTime", "")),
                latitude=self._safe_float_convert(msg_data.get("latitude")) or 0.0,
                longitude=self._safe_float_convert(msg_data.get("longitude")) or 0.0,
                depth=depth,
                magnitude=magnitude,
                place_name=msg_data.get("placeName", ""),
                info_type=msg_data.get("infoTypeName", ""),
                raw_data=msg_data,
            )

            logger.info(
                f"[灾害预警] 地震数据解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {e}")
            return None


class CENCEarthquakeWolfxHandler(BaseDataHandler):
    """中国地震台网地震测定处理器 - Wolfx"""

    def __init__(self, message_logger=None):
        super().__init__("cenc_wolfx", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析Wolfx中国地震台网地震列表"""
        try:
            # 检查消息类型
            if data.get("type") != "cenc_eqlist":
                logger.debug(f"[灾害预警] {self.source_id} 非CENC地震列表数据，跳过")
                return None

            # 只处理最新的地震
            eq_info = None
            for key, value in data.items():
                if key.startswith("No") and isinstance(value, dict):
                    eq_info = value
                    break

            if not eq_info:
                return None

            earthquake = EarthquakeData(
                id=eq_info.get("md5", ""),
                event_id=eq_info.get("md5", ""),
                source=DataSource.WOLFX_CENC_EQ,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(eq_info.get("time", "")),
                latitude=self._safe_float_convert(eq_info.get("latitude")) or 0.0,
                longitude=self._safe_float_convert(eq_info.get("longitude")) or 0.0,
                depth=self._safe_float_convert(eq_info.get("depth")),
                magnitude=self._safe_float_convert(eq_info.get("magnitude")),
                intensity=self._safe_float_convert(eq_info.get("intensity")),
                place_name=eq_info.get("location", ""),
                info_type=eq_info.get("type", ""),
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] 地震数据解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析数据失败: {e}")
            return None
