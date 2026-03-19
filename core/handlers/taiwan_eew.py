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

            raw_shock_time = msg_data.get("shockTime", "")
            shock_time = self._parse_datetime(raw_shock_time)
            latitude = safe_float_convert(msg_data.get("latitude")) or 0.0
            longitude = safe_float_convert(msg_data.get("longitude")) or 0.0

            # 组装受影响区域描述
            place_name = msg_data.get("placeName", "")
            location_desc_list = msg_data.get("locationDesc", [])
            if location_desc_list and isinstance(location_desc_list, list):
                # 如果有影响区域列表，将其附加到地名后或单独处理
                # 这里简单处理，追加到 place_name 后面，格式如 "高雄市桃源區 (影响: 嘉義縣, 嘉義市)"
                # 或者由上层 UI 决定如何显示。为了兼容性，这里尽量保持 place_name 简洁
                pass

            # 关键修复：同源合并优先依赖稳定 event_id，避免回退到可能每报变化的 id
            event_id = str(
                msg_data.get("eventId") or msg_data.get("eventID") or ""
            ).strip()
            if not event_id:
                shock_key = str(raw_shock_time or "").strip()
                place_key = str(place_name or "").strip()
                event_id = (
                    f"cwa_fan_{shock_key}_{latitude:.3f}_{longitude:.3f}_{place_key}"
                )
                logger.debug(
                    f"[灾害预警] {self.source_id} 缺少 eventId，已使用稳定回退ID: {event_id}"
                )

            earthquake = EarthquakeData(
                id=str(msg_data.get("id", "")),
                event_id=event_id,
                source=DataSource.FAN_STUDIO_CWA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=shock_time,
                create_time=self._parse_datetime(
                    msg_data.get("createTime", "")
                ),  # 某些版本可能没有 createTime
                latitude=latitude,
                longitude=longitude,
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

            raw_origin_time = data.get("OriginTime", "")
            shock_time = self._parse_datetime(raw_origin_time)
            latitude = safe_float_convert(data.get("Latitude")) or 0.0
            longitude = safe_float_convert(data.get("Longitude")) or 0.0
            place_name = data.get("HypoCenter", "")

            # Wolfx 影响区域提取（优先 WarnArea.Chiiki）
            impact_area = ""
            warn_area = data.get("WarnArea")
            if isinstance(warn_area, dict):
                impact_area = str(warn_area.get("Chiiki") or "").strip()

            if not impact_area:
                for key in [
                    "locationDesc",
                    "impactArea",
                    "ImpactArea",
                    "affectedArea",
                    "AffectedArea",
                    "Area",
                    "area",
                ]:
                    value = data.get(key)
                    if isinstance(value, list):
                        value = "、".join(
                            str(x).strip() for x in value if str(x).strip()
                        )
                    elif not isinstance(value, str):
                        value = ""
                    value = value.strip()
                    if value:
                        impact_area = value
                        break

            # 关键修复：优先 EventID；缺失时生成稳定回退ID，避免同源拆分
            event_id = str(data.get("EventID") or data.get("eventId") or "").strip()
            if not event_id:
                shock_key = str(raw_origin_time or "").strip()
                place_key = str(place_name or "").strip()
                event_id = (
                    f"cwa_wolfx_{shock_key}_{latitude:.3f}_{longitude:.3f}_{place_key}"
                )
                logger.debug(
                    f"[灾害预警] {self.source_id} 缺少 EventID，已使用稳定回退ID: {event_id}"
                )

            earthquake = EarthquakeData(
                id=str(data.get("ID", "")),
                event_id=event_id,
                source=DataSource.WOLFX_CWA_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=shock_time,
                latitude=latitude,
                longitude=longitude,
                depth=safe_float_convert(data.get("Depth")),
                magnitude=safe_float_convert(
                    data.get("Magunitude") or data.get("Magnitude")
                ),
                scale=ScaleConverter.parse_jma_cwa_scale(data.get("MaxIntensity", "")),
                place_name=place_name,
                updates=data.get("ReportNum", 1),
                is_final=data.get("isFinal", False),
                province=impact_area or None,
                raw_data={**data, "wolfx_impact_area": impact_area}
                if impact_area
                else data,
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
