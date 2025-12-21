"""
日本地震情报处理器
包含 JMA (日本气象厅) 地震情报相关处理器
"""

import json
from typing import Any

from astrbot.api import logger

from .base import BaseDataHandler, _safe_float_convert
from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)


class JMAEarthquakeP2PHandler(BaseDataHandler):
    """日本气象厅地震情报处理器 - P2P"""

    def __init__(self, message_logger=None):
        super().__init__("jma_p2p_info", message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析P2P地震情報"""
        # 不再重复记录原始消息，WebSocket管理器已记录详细信息
        try:
            data = json.loads(message)

            # 根据code判断消息类型
            code = data.get("code")

            if code == 551:  # 地震情報
                logger.debug(f"[灾害预警] {self.source_id} 收到地震情報(code:551)")
                return self._parse_earthquake_data(data)
            else:
                logger.debug(
                    f"[灾害预警] {self.source_id} 非地震情報数据，code: {code}"
                )
                return None

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {e}")
            return None

    def _safe_float_convert(self, value) -> float | None:
        """安全地将值转换为浮点数 - 为JMAEarthquakeP2PHandler提供此方法"""
        return _safe_float_convert(value)

    def _parse_earthquake_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析地震情報"""
        try:
            # 获取基础数据 - 使用英文键名（实际数据格式）
            earthquake_info = data.get("earthquake", {})
            hypocenter = earthquake_info.get("hypocenter", {})
            # issue_info = data.get("issue", {})  # 未使用，注释掉以避免未使用变量警告

            # 关键字段检查
            magnitude_raw = hypocenter.get("magnitude")
            place_name = hypocenter.get("name")
            latitude = hypocenter.get("latitude")
            longitude = hypocenter.get("longitude")

            # 震级解析
            magnitude = self._safe_float_convert(magnitude_raw)
            if magnitude is None:
                logger.error(
                    f"[灾害预警] {self.source_id} 震级解析失败: {magnitude_raw}"
                )
                return None

            # 经纬度解析
            lat = self._safe_float_convert(latitude)
            lon = self._safe_float_convert(longitude)
            if lat is None or lon is None:
                logger.error(
                    f"[灾害预警] {self.source_id} 经纬度解析失败: lat={latitude}, lon={longitude}"
                )
                return None

            # 震度转换
            max_scale_raw = earthquake_info.get("maxScale", -1)
            scale = (
                self._convert_p2p_scale_to_standard(max_scale_raw)
                if max_scale_raw != -1
                else None
            )

            # 深度解析
            depth_raw = hypocenter.get("depth")
            depth = self._safe_float_convert(depth_raw)

            # 时间解析
            time_raw = earthquake_info.get("time", "")
            shock_time = self._parse_datetime(time_raw)

            earthquake = EarthquakeData(
                id=data.get("id", ""),  # P2P使用"id"字段
                event_id=data.get("id", ""),  # 同样用作event_id
                source=DataSource.P2P_EARTHQUAKE,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=shock_time,
                latitude=lat,
                longitude=lon,
                depth=depth,
                magnitude=magnitude,
                place_name=place_name or "未知地点",
                scale=scale,
                max_scale=max_scale_raw,
                domestic_tsunami=earthquake_info.get("domesticTsunami"),
                foreign_tsunami=earthquake_info.get("foreignTsunami"),
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
            logger.error(f"[灾害预警] {self.source_id} 解析地震情報失败: {e}")
            return None

    def _convert_p2p_scale_to_standard(self, p2p_scale: int) -> float | None:
        """将P2P震度值转换为标准震度 - 补充完整枚举值"""
        scale_mapping = {
            -1: None,  # 震度情報不存在
            0: 0.0,  # 震度0
            10: 1.0,  # 震度1
            20: 2.0,  # 震度2
            30: 3.0,  # 震度3
            40: 4.0,  # 震度4
            45: 4.5,  # 震度5弱
            46: 4.6,  # 震度5弱以上と推定されるが震度情報を入手していない（推测震度为5弱以上，但尚未获取震级信息）
            50: 5.0,  # 震度5強
            55: 5.5,  # 震度6弱
            60: 6.0,  # 震度6強
            70: 7.0,  # 震度7
        }

        if p2p_scale not in scale_mapping:
            logger.warning(f"[灾害预警] {self.source_id} 未知的P2P震度值: {p2p_scale}")
            return None

        return scale_mapping.get(p2p_scale)


class JMAEarthquakeWolfxHandler(BaseDataHandler):
    """日本气象厅地震情报处理器 - Wolfx"""

    def __init__(self, message_logger=None):
        super().__init__("jma_wolfx_info", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析Wolfx日本气象厅地震列表"""
        try:
            # 检查消息类型
            if data.get("type") != "jma_eqlist":
                logger.debug(f"[灾害预警] {self.source_id} 非JMA地震列表数据，跳过")
                return None

            # 只处理最新的地震
            eq_info = None
            for key, value in data.items():
                if key.startswith("No") and isinstance(value, dict):
                    eq_info = value
                    break

            if not eq_info:
                return None

            # 修复深度字段格式 - 处理"20km"字符串格式
            depth_raw = eq_info.get("depth")
            depth = None
            if depth_raw:
                if isinstance(depth_raw, str) and depth_raw.endswith("km"):
                    try:
                        depth = float(depth_raw[:-2])  # 去掉"km"后缀
                    except (ValueError, TypeError):
                        depth = None
                else:
                    depth = self._safe_float_convert(depth_raw)

            # 修复震级字段格式
            magnitude_raw = eq_info.get("magnitude")
            magnitude = self._safe_float_convert(magnitude_raw)

            earthquake = EarthquakeData(
                id=eq_info.get("md5", ""),
                event_id=eq_info.get("md5", ""),
                source=DataSource.WOLFX_JMA_EQ,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(eq_info.get("time", "")),
                latitude=self._safe_float_convert(eq_info.get("latitude")),
                longitude=self._safe_float_convert(eq_info.get("longitude")),
                depth=depth,
                magnitude=magnitude,
                scale=self._parse_jma_scale(eq_info.get("shindo", "")),
                place_name=eq_info.get("location", ""),
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

    def _safe_float_convert(self, value) -> float | None:
        """安全地将值转换为浮点数 - 为JMAEarthquakeWolfxHandler提供此方法"""
        return _safe_float_convert(value)

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
