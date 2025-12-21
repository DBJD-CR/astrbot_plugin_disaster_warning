"""
日本地震预警处理器
包含 JMA (日本气象厅) EEW 相关处理器
"""

import json
from typing import Any

from astrbot.api import logger

from .base import BaseDataHandler
from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)


class JMAEEWFanStudioHandler(BaseDataHandler):
    """日本气象厅地震预警处理器 - FAN Studio"""

    def __init__(self, message_logger=None):
        super().__init__("jma_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析FAN Studio日本气象厅地震预警数据"""
        try:
            # 获取实际数据 - FAN Studio使用大写D的Data字段
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

            # 检查是否为地震预警数据 - JMA数据也有epiIntensity字段
            if "epiIntensity" not in msg_data and "infoTypeName" not in msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 非JMA地震预警数据，跳过")
                return None

            # 检查是否为取消报
            if msg_data.get("cancel", False):
                logger.info(f"[灾害预警] {self.source_id} 收到取消报，跳过")
                return None

            earthquake = EarthquakeData(
                id=msg_data.get("id", ""),
                event_id=msg_data.get("id", ""),  # JMA使用id作为event_id
                source=DataSource.FAN_STUDIO_JMA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(msg_data.get("shockTime", "")),
                latitude=float(msg_data.get("latitude", 0)),
                longitude=float(msg_data.get("longitude", 0)),
                depth=msg_data.get("depth"),
                magnitude=msg_data.get("magnitude"),
                intensity=msg_data.get("epiIntensity"),  # 预估最大震度
                place_name=msg_data.get("placeName", ""),
                updates=msg_data.get("updates", 1),
                is_final=msg_data.get("final", False),
                is_cancel=msg_data.get("cancel", False),
                info_type=msg_data.get("infoTypeName", ""),  # 予報/警報
                create_time=self._parse_datetime(msg_data.get("createTime", "")),
                raw_data=msg_data,
            )

            logger.info(
                f"[灾害预警] JMA地震预警解析成功: {earthquake.place_name} (M {earthquake.magnitude}), 时间: {earthquake.shock_time}"
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


class JMAEEWP2PHandler(BaseDataHandler):
    """日本气象厅紧急地震速报处理器 - P2P"""

    def __init__(self, message_logger=None):
        super().__init__("jma_p2p", message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析P2P消息"""
        # 不再重复记录原始消息，WebSocket管理器已记录详细信息
        try:
            data = json.loads(message)

            # 根据code判断消息类型
            code = data.get("code")

            if code == 556:  # 緊急地震速報（警報）
                logger.debug(f"[灾害预警] {self.source_id} 收到緊急地震速報（警報）")
                return self._parse_eew_data(data)
            elif code == 554:  # 緊急地震速報 発表検出
                logger.debug(
                    f"[灾害预警] {self.source_id} 收到緊急地震速報発表検出，忽略"
                )
                return None
            else:
                logger.debug(f"[灾害预警] {self.source_id} 非EEW数据，code: {code}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {e}")
            return None

    def _parse_eew_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析緊急地震速報数据"""
        try:
            earthquake_info = data.get("earthquake", {})
            hypocenter = earthquake_info.get("hypocenter", {})
            issue_info = data.get("issue", {})
            areas = data.get("areas", [])

            # 兼容性处理：优先检查maxScale字段
            max_scale_raw = -1
            if "maxScale" in earthquake_info:
                max_scale_raw = earthquake_info.get("maxScale", -1)
            elif "max_scale" in earthquake_info:
                max_scale_raw = earthquake_info.get("max_scale", -1)
            else:
                # 从areas中计算最大震度作为后备
                # P2P API中可能是scaleFrom或scaleTo，两者都尝试
                raw_scales = []
                for area in areas:
                    scale = area.get("scaleFrom", 0)
                    if scale <= 0:
                        scale = area.get("scaleTo", 0)
                    if scale > 0:
                        raw_scales.append(scale)

                max_scale_raw = max(raw_scales) if raw_scales else -1
                if max_scale_raw > 0:
                    logger.warning(
                        f"[灾害预警] {self.source_id} 使用areas计算maxScale: {max_scale_raw}"
                    )

            scale = (
                self._convert_p2p_scale_to_standard(max_scale_raw)
                if max_scale_raw != -1
                else None
            )

            # 兼容性处理：优先检查time字段
            shock_time = None
            if "time" in earthquake_info:
                shock_time = self._parse_datetime(earthquake_info.get("time", ""))
            elif "originTime" in earthquake_info:
                shock_time = self._parse_datetime(earthquake_info.get("originTime", ""))
            else:
                logger.warning(f"[灾害预警] {self.source_id} 缺少地震时间信息")

            # 必填字段验证 - 记录warning但继续处理
            required_hypocenter_fields = ["latitude", "longitude", "name"]
            missing_fields = []
            for field in required_hypocenter_fields:
                if field not in hypocenter or hypocenter[field] is None:
                    missing_fields.append(field)

            if missing_fields:
                logger.warning(
                    f"[灾害预警] {self.source_id} 缺少震源必填字段: {missing_fields}，继续处理..."
                )

            # 检查cancelled字段
            is_cancelled = data.get("cancelled", False)
            if is_cancelled:
                logger.info(f"[灾害预警] {self.source_id} 收到取消的EEW事件")

            # 检查test字段
            is_test = data.get("test", False)
            if is_test:
                logger.info(f"[灾害预警] {self.source_id} 收到测试模式的EEW事件")

            earthquake = EarthquakeData(
                id=data.get("id", ""),
                event_id=issue_info.get("eventId", ""),
                source=DataSource.P2P_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=shock_time,
                latitude=hypocenter.get("latitude", 0),
                longitude=hypocenter.get("longitude", 0),
                depth=hypocenter.get("depth"),
                magnitude=hypocenter.get("magnitude"),
                place_name=hypocenter.get("name", "未知地点"),
                scale=scale,
                is_final=data.get("is_final", False),
                is_cancel=is_cancelled,
                is_training=is_test,
                serial=issue_info.get("serial", ""),
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
            logger.error(f"[灾害预警] {self.source_id} 解析EEW数据失败: {e}")
            return None

    def _convert_p2p_scale_to_standard(self, p2p_scale: int) -> float | None:
        """将P2P震度值转换为标准震度"""
        scale_mapping = {
            10: 1.0,  # 震度1
            20: 2.0,  # 震度2
            30: 3.0,  # 震度3
            40: 4.0,  # 震度4
            45: 4.5,  # 震度5弱
            50: 5.0,  # 震度5強
            55: 5.5,  # 震度6弱
            60: 6.0,  # 震度6強
            70: 7.0,  # 震度7
        }
        return scale_mapping.get(p2p_scale)


class JMAEEWWolfxHandler(BaseDataHandler):
    """日本气象厅紧急地震速报处理器 - Wolfx"""

    def __init__(self, message_logger=None):
        super().__init__("jma_wolfx", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析Wolfx JMA EEW数据"""
        try:
            # 检查消息类型
            if data.get("type") != "jma_eew":
                logger.debug(f"[灾害预警] {self.source_id} 非JMA EEW数据，跳过")
                return None

            earthquake = EarthquakeData(
                id=data.get("EventID", ""),
                event_id=data.get("EventID", ""),
                source=DataSource.WOLFX_JMA_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("OriginTime", "")),
                latitude=data.get("Latitude", 0),
                longitude=data.get("Longitude", 0),
                depth=data.get("Depth"),
                magnitude=data.get("Magunitude") or data.get("Magnitude"),
                place_name=data.get("Hypocenter", ""),
                scale=self._parse_jma_scale(data.get("MaxIntensity", "")),
                is_final=data.get("isFinal", False),
                is_cancel=data.get("isCancel", False),
                is_training=data.get("isTraining", False),
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

    def _parse_jma_scale(self, scale_str: str) -> float | None:
        """解析日本震度"""
        if not scale_str:
            return None

        import re

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
