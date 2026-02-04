"""
台湾地震预警处理器
包含 CWA (中央气象署) 相关处理器
"""

from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)
from ...utils.converters import ScaleConverter, safe_float_convert
from .base import BaseDataHandler


class CWAEEWHandler(BaseDataHandler):
    """台湾中央气象署地震预警处理器 - FAN Studio"""

    def __init__(self, message_logger=None):
        super().__init__("cwa_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析台湾中央气象署地震预警数据"""
        try:
            # 获取实际数据
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 检查是否为CWA地震预警数据
            # 兼容新旧字段：maxIntensity -> epiIntensity
            # 新版 API 可能没有 epiIntensity/maxIntensity 字段，而是直接给 depth/magnitude/locationDesc
            # 但作为 EEW，updates 是必须的
            if "updates" not in msg_data and "eventId" not in msg_data:
                logger.debug(
                    f"[灾害预警] {self.source_id} 非CWA地震预警数据(缺少updates/eventId)，跳过"
                )
                return None

            intensity = msg_data.get("maxIntensity")
            if intensity is None:
                intensity = msg_data.get("epiIntensity")

            # 组装受影响区域描述
            place_name = msg_data.get("placeName", "")
            location_desc_list = msg_data.get("locationDesc", [])
            if location_desc_list and isinstance(location_desc_list, list):
                # 如果有影响区域列表，将其附加到地名后或单独处理
                # 这里简单处理，追加到 place_name 后面，格式如 "高雄市桃源區 (影响: 嘉義縣, 嘉義市)"
                # 或者由上层 UI 决定如何显示。为了兼容性，这里尽量保持 place_name 简洁
                pass

            earthquake = EarthquakeData(
                id=str(msg_data.get("id", "")),
                event_id=msg_data.get(
                    "eventId", msg_data.get("id", "")
                ),  # 新版可能只有id
                source=DataSource.FAN_STUDIO_CWA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(msg_data.get("shockTime", "")),
                create_time=self._parse_datetime(
                    msg_data.get("createTime", "")
                ),  # 某些版本可能没有 createTime
                latitude=safe_float_convert(msg_data.get("latitude")) or 0.0,
                longitude=safe_float_convert(msg_data.get("longitude")) or 0.0,
                depth=safe_float_convert(msg_data.get("depth")),
                magnitude=safe_float_convert(msg_data.get("magnitude")),
                scale=safe_float_convert(intensity),
                place_name=place_name,
                updates=msg_data.get("updates", 1),
                is_final=msg_data.get("isFinal", False),
                # 将 locationDesc 放入 raw_data，后续可在 message_manager 中处理
                raw_data=msg_data,
            )

            # 如果 raw_data 中有 locationDesc，可以尝试将其解析为省份/区域信息
            if location_desc_list:
                earthquake.province = ",".join(location_desc_list)

            logger.info(
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
                latitude=safe_float_convert(data.get("Latitude")) or 0.0,
                longitude=safe_float_convert(data.get("Longitude")) or 0.0,
                depth=safe_float_convert(data.get("Depth")),
                magnitude=safe_float_convert(
                    data.get("Magunitude") or data.get("Magnitude")
                ),
                scale=ScaleConverter.parse_jma_cwa_scale(data.get("MaxIntensity", "")),
                place_name=data.get("HypoCenter", ""),
                updates=data.get("ReportNum", 1),
                is_final=data.get("isFinal", False),
                raw_data=data,
            )

            logger.info(
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
