"""
台湾地震预警处理器
包含 CWA (中央气象署) 相关处理器
"""

import re
from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)
from .base import BaseDataHandler, _safe_float_convert


class CWAEEWHandler(BaseDataHandler):
    """台湾中央气象署地震预警处理器 - FAN Studio"""

    def __init__(self, message_logger=None):
        super().__init__("cwa_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析台湾中央气象署地震预警数据"""
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

            # 检查是否为CWA地震预警数据
            # 兼容新旧字段：maxIntensity -> epiIntensity
            intensity = msg_data.get("maxIntensity")
            if intensity is None:
                intensity = msg_data.get("epiIntensity")

            if intensity is None or "createTime" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非CWA地震预警数据，跳过")
                return None

            earthquake = EarthquakeData(
                id=str(msg_data.get("id", "")),
                event_id=msg_data.get("eventId", ""),
                source=DataSource.FAN_STUDIO_CWA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(msg_data.get("shockTime", "")),
                create_time=self._parse_datetime(msg_data.get("createTime", "")),
                latitude=float(msg_data.get("latitude", 0)),
                longitude=float(msg_data.get("longitude", 0)),
                depth=msg_data.get("depth"),
                magnitude=msg_data.get("magnitude"),
                scale=_safe_float_convert(intensity),
                place_name=msg_data.get("placeName", ""),
                updates=msg_data.get("updates", 1),
                is_final=msg_data.get("isFinal", False),
                raw_data=msg_data,
            )

            logger.debug(
                f"[灾害预警] 地震预警解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
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


class CWAEEWWolfxHandler(BaseDataHandler):
    """台湾中央气象署地震预警处理器 - Wolfx"""

    def __init__(self, message_logger=None):
        super().__init__("cwa_wolfx", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析Wolfx台湾地震预警数据"""
        try:
            # 检查消息类型
            if data.get("type") != "cwa_eew":
                logger.debug(f"[灾害预警] {self.source_id} 非CWA EEW数据，跳过")
                return None

            earthquake = EarthquakeData(
                id=str(data.get("ID", "")),
                event_id=data.get("EventID", ""),
                source=DataSource.WOLFX_CWA_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("OriginTime", "")),
                latitude=data.get("Latitude", 0),
                longitude=data.get("Longitude", 0),
                depth=data.get("Depth"),
                magnitude=data.get("Magunitude") or data.get("Magnitude"),
                scale=self._parse_cwa_scale(data.get("MaxIntensity", "")),
                place_name=data.get("HypoCenter", ""),
                updates=data.get("ReportNum", 1),
                is_final=data.get("isFinal", False),
                raw_data=data,
            )

            logger.debug(
                f"[灾害预警] 地震预警解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
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

    def _parse_cwa_scale(self, scale_str: str) -> float | None:
        """解析台湾震度"""
        if not scale_str:
            return None

        match = re.search(r"(\d+)(弱|強)?", scale_str)
        if match:
            base = int(match.group(1))
            suffix = match.group(2)

            if suffix == "弱":
                return base - 0.5
            elif suffix == "強":
                return base + 0.5
            else:
                return float(base)

        return None
