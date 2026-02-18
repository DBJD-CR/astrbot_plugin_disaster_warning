"""
全球及其他地震资源处理器
包含 USGS 和 GlobalQuake 相关处理器
"""

import json
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from ...models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
)
from ...models.websocket_message_pb2 import WsMessage, MessageType
from ...utils.converters import ScaleConverter, safe_float_convert
from ...utils.fe_regions import translate_place_name
from .base import BaseDataHandler


class GlobalQuakeHandler(BaseDataHandler):
    """Global Quake处理器 - 适配 Protocol Buffers 格式"""

    def __init__(self, message_logger=None):
        super().__init__("global_quake", message_logger)

    def parse_message(self, message: str | bytes) -> DisasterEvent | None:
        """解析Global Quake消息 - 支持 JSON 和 Protobuf 格式"""
        try:
            # 检测消息类型：二进制 (protobuf) 或文本 (JSON)
            if isinstance(message, bytes):
                return self._parse_protobuf_message(message)
            else:
                return self._parse_json_message(message)

        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 消息处理失败: {e}")
            return None

    def _parse_protobuf_message(self, message: bytes) -> DisasterEvent | None:
        """解析 Protocol Buffers 格式消息"""
        try:
            # 反序列化 protobuf 消息
            ws_msg = WsMessage()
            ws_msg.ParseFromString(message)

            # 检查消息类型
            if ws_msg.type == MessageType.EARTHQUAKE:
                logger.debug(
                    f"[灾害预警] {self.source_id} 收到地震消息 (Protobuf)"
                )
                return self._parse_earthquake_protobuf(ws_msg)
            elif ws_msg.type == MessageType.HEARTBEAT:
                logger.debug(f"[灾害预警] {self.source_id} 心跳消息")
                return None
            elif ws_msg.type == MessageType.STATUS:
                logger.debug(
                    f"[灾害预警] {self.source_id} 状态消息: {ws_msg.status_data.server_status}"
                )
                return None
            else:
                logger.debug(f"[灾害预警] {self.source_id} 未知消息类型: {ws_msg.type}")
                return None

        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} Protobuf 解析失败: {e}")
            return None

    def _parse_json_message(self, message: str) -> DisasterEvent | None:
        """解析 JSON 格式消息（向后兼容）"""
        try:
            data = json.loads(message)

            # 检查消息类型
            msg_type = data.get("type")
            action = data.get("action")

            if msg_type == "earthquake":
                logger.debug(
                    f"[灾害预警] {self.source_id} 收到地震消息 (JSON)，action: {action}"
                )
                return self._parse_earthquake_data(data)
            else:
                logger.debug(f"[灾害预警] {self.source_id} 忽略消息类型: {msg_type}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] {self.source_id} JSON解析失败: {e}")
            return None

    def _parse_earthquake_protobuf(self, ws_msg: WsMessage) -> DisasterEvent | None:
        """解析 Protobuf 地震数据"""
        try:
            eq_data = ws_msg.earthquake_data

            # 解析震源时间
            shock_time = None
            if eq_data.origin_time_iso:
                shock_time = self._parse_datetime(eq_data.origin_time_iso)
            elif eq_data.origin_time_ms:
                shock_time = datetime.fromtimestamp(
                    eq_data.origin_time_ms / 1000, tz=timezone.utc
                )

            # 解析烈度（从罗马数字转换）
            intensity = ScaleConverter.convert_roman_intensity(eq_data.intensity)

            # 格式化震级和深度
            magnitude = round(eq_data.magnitude, 1) if eq_data.magnitude else None
            depth = round(eq_data.depth, 1) if eq_data.depth else None

            # 翻译地名
            place_name = translate_place_name(
                eq_data.region, eq_data.latitude, eq_data.longitude, fallback_to_original=True
            )

            # 提取台站信息
            station_count = None
            if eq_data.HasField("station_count"):
                station_count = {
                    "total": eq_data.station_count.total,
                    "selected": eq_data.station_count.selected,
                    "used": eq_data.station_count.used,
                    "matching": eq_data.station_count.matching,
                }

            # 提取质量信息
            quality_data = None
            if eq_data.HasField("quality"):
                quality_data = {
                    "err_origin": eq_data.quality.err_origin,
                    "err_depth": eq_data.quality.err_depth,
                    "err_ns": eq_data.quality.err_ns,
                    "err_ew": eq_data.quality.err_ew,
                    "pct": eq_data.quality.pct,
                    "stations": eq_data.quality.stations,
                }

            # 构建 raw_data，包含必要的质量信息
            raw_data = {
                "protobuf": True,
                "id": eq_data.id,
                "data": {
                    "quality": quality_data
                } if quality_data else {}
            }

            # 创建地震数据对象
            earthquake = EarthquakeData(
                id=eq_data.id,
                event_id=eq_data.id,
                source=DataSource.GLOBAL_QUAKE,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=shock_time or datetime.now(timezone.utc),
                latitude=eq_data.latitude,
                longitude=eq_data.longitude,
                depth=depth,
                magnitude=magnitude,
                intensity=intensity,
                place_name=place_name,
                updates=eq_data.revision_id,
                raw_data=raw_data,
                max_pga=eq_data.max_pga if eq_data.max_pga else None,
                stations=station_count,
            )

            logger.info(
                f"[灾害预警] Global Quake地震解析成功 (Protobuf): {earthquake.place_name} "
                f"(M {earthquake.magnitude or 0.0:.1f}), 烈度: {eq_data.intensity}, "
                f"时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析 Protobuf 地震数据失败: {e}")
            return None

    def _parse_earthquake_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析地震数据 - 适配新的GlobalQuake Monitor格式"""
        try:
            # 获取实际地震数据
            eq_data = self._extract_data(data)
            if not eq_data:
                logger.warning(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 解析震源时间
            shock_time = None
            origin_time_iso = eq_data.get("originTimeIso")
            if origin_time_iso:
                shock_time = self._parse_datetime(origin_time_iso)
            elif eq_data.get("originTimeMs"):
                # 从毫秒时间戳解析
                shock_time = datetime.fromtimestamp(
                    eq_data["originTimeMs"] / 1000, tz=timezone.utc
                )

            # 解析烈度（从罗马数字转换）
            intensity_str = eq_data.get("intensity", "")
            intensity = ScaleConverter.convert_roman_intensity(intensity_str)

            # 获取坐标
            latitude = eq_data.get("latitude", 0)
            longitude = eq_data.get("longitude", 0)

            # 格式化震级和深度 - 保留1位小数，与其他数据源保持一致
            magnitude_raw = eq_data.get("magnitude")
            magnitude = safe_float_convert(magnitude_raw)
            if magnitude is not None:
                magnitude = round(magnitude, 1)

            depth_raw = eq_data.get("depth")
            depth = safe_float_convert(depth_raw)
            if depth is not None:
                depth = round(depth, 1)

            # 翻译地名（使用FE Regions，类似USGS处理）
            original_region = eq_data.get("region", "未知地点")
            place_name = translate_place_name(
                original_region, latitude, longitude, fallback_to_original=True
            )

            # 获取最大加速度和测站信息
            max_pga = eq_data.get("maxPGA")
            station_count = eq_data.get("stationCount")

            # 创建地震数据对象
            earthquake = EarthquakeData(
                id=eq_data.get("id", ""),
                event_id=eq_data.get("id", ""),
                source=DataSource.GLOBAL_QUAKE,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=shock_time or datetime.now(timezone.utc),
                latitude=latitude,
                longitude=longitude,
                depth=depth,
                magnitude=magnitude,
                intensity=intensity,
                place_name=place_name,
                updates=eq_data.get("revisionId", 1),
                raw_data=data,
                max_pga=max_pga,
                stations=station_count,
            )

            logger.info(
                f"[灾害预警] Global Quake地震解析成功: {earthquake.place_name} "
                f"(M {earthquake.magnitude or 0.0:.1f}), 烈度: {intensity_str}, "
                f"时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] {self.source_id} 解析地震数据失败: {e}")
            return None

    def _parse_text_message(self, message: str) -> DisasterEvent | None:
        """解析文本消息 - 保留向后兼容"""
        logger.debug(f"[灾害预警] {self.source_id} 文本消息: {message}")
        return None

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """实现基类抽象方法 - JSON 格式"""
        return self._parse_earthquake_data(data)


class USGSEarthquakeHandler(BaseDataHandler):
    """美国地质调查局地震情报处理器"""

    def __init__(self, message_logger=None):
        super().__init__("usgs_fanstudio", message_logger)

    def _parse_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析USGS地震数据"""
        try:
            # 获取实际数据
            msg_data = self._extract_data(data)
            if not msg_data:
                logger.debug(f"[灾害预警] {self.source_id} 消息中没有有效数据")
                return None

            # 心跳包检测 - 在详细处理前进行快速过滤
            if self._is_heartbeat_message(msg_data):
                return None

            # 检查关键字段 - 兼容大小写（仅记录警告，不阻止处理）
            required_fields = ["id", "magnitude", "latitude", "longitude", "shockTime"]
            missing_fields = []
            for field in required_fields:
                # 检查小写和大写版本
                if field not in msg_data and field.capitalize() not in msg_data:
                    missing_fields.append(field)
                elif field in msg_data and msg_data[field] is None:
                    missing_fields.append(field)
                elif (
                    field.capitalize() in msg_data
                    and msg_data[field.capitalize()] is None
                ):
                    missing_fields.append(field)

            if missing_fields:
                logger.debug(
                    f"[灾害预警] {self.source_id} 数据缺少部分字段: {missing_fields}，继续处理..."
                )

            # 优化USGS数据精度 - 四舍五入到1位小数
            def get_field(data, field_name):
                """获取字段值，兼容大小写"""
                return data.get(field_name) or data.get(field_name.capitalize())

            magnitude_raw = get_field(msg_data, "magnitude")
            magnitude = safe_float_convert(magnitude_raw)
            if magnitude is not None:
                magnitude = round(magnitude, 1)

            depth_raw = get_field(msg_data, "depth")
            depth = safe_float_convert(depth_raw)
            if depth is not None:
                depth = round(depth, 1)

            # 验证关键字段 - 如果缺少关键信息，不创建地震对象
            usgs_id = get_field(msg_data, "id") or ""
            usgs_latitude = safe_float_convert(get_field(msg_data, "latitude")) or 0.0
            usgs_longitude = safe_float_convert(get_field(msg_data, "longitude")) or 0.0
            usgs_place_name_en = get_field(msg_data, "placeName") or ""

            if not usgs_id:
                # 只有在非心跳包情况下才记录警告，且避免重复警告
                if not self._is_heartbeat_message(msg_data):
                    warning_msg = f"[灾害预警] {self.source_id} 缺少地震ID，跳过处理"
                    if self._should_log_warning("missing_usgs_id", warning_msg):
                        logger.warning(warning_msg)
                return None

            if usgs_latitude == 0 and usgs_longitude == 0:
                # 心跳包检测已经处理了这种情况，这里不再重复记录
                return None

            if not usgs_place_name_en and not magnitude:
                # 只有在非心跳包情况下才记录警告，且避免重复警告
                if not self._is_heartbeat_message(msg_data):
                    warning_msg = (
                        f"[灾害预警] {self.source_id} 缺少地点名称和震级信息，跳过处理"
                    )
                    if self._should_log_warning(
                        "missing_usgs_place_magnitude", warning_msg
                    ):
                        logger.warning(warning_msg)
                return None

            # 🌏 FE Regions 中文翻译
            # 将 USGS 英文地名翻译为中文（基于 F-E 地震区划）
            usgs_place_name = translate_place_name(
                usgs_place_name_en,
                usgs_latitude,
                usgs_longitude,
                fallback_to_original=True,  # 翻译失败时保留英文
            )

            # 记录翻译结果（仅在翻译成功时）
            if usgs_place_name != usgs_place_name_en:
                logger.debug(
                    f"[灾害预警] {self.source_id} FE翻译: '{usgs_place_name_en}' → '{usgs_place_name}'"
                )

            earthquake = EarthquakeData(
                id=usgs_id,
                event_id=usgs_id,
                source=DataSource.FAN_STUDIO_USGS,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(get_field(msg_data, "shockTime")),
                update_time=self._parse_datetime(get_field(msg_data, "updateTime")),
                latitude=usgs_latitude,
                longitude=usgs_longitude,
                depth=depth,
                magnitude=magnitude,
                place_name=usgs_place_name,
                info_type=get_field(msg_data, "infoTypeName") or "",
                raw_data=msg_data,
            )

            logger.info(
                f"[灾害预警] 地震数据解析成功: {earthquake.place_name} (M {earthquake.magnitude or 0.0}), 时间: {earthquake.shock_time}"
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
