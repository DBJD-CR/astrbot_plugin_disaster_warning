"""
各数据源处理器
"""

import json
import re
import traceback
from datetime import datetime
from typing import Any

from astrbot.api import logger

from .models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)


class BaseDataHandler:
    """基础数据处理器"""

    def __init__(self, source: DataSource, message_logger=None):
        self.source = source
        self.message_logger = message_logger

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析消息"""
        # 记录原始消息
        if self.message_logger:
            self.message_logger.log_raw_message(
                source=self.source.value, message_type="raw_message", raw_data=message
            )
        raise NotImplementedError

    def _parse_datetime(self, time_str: str) -> datetime:
        """解析时间字符串"""
        try:
            # 尝试多种时间格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y/%m/%d %H:%M:%S.%f",
                "%Y/%m/%d %H:%M",  # ✅ 新增：气象预警格式
                "%Y-%m-%d %H:%M",  # ✅ 新增：备用格式
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue

            # 如果都失败了，返回当前时间
            return datetime.now()
        except Exception as e:
            logger.warning(f"[灾害预警] 时间解析失败: {time_str}, 错误: {e}")
            return datetime.now()


class FanStudioHandler(BaseDataHandler):
    """FAN Studio数据处理器"""

    def __init__(self, message_logger=None):
        super().__init__(DataSource.FAN_STUDIO_CENC, message_logger)

    def parse_message(self, message: str, connection_name=None) -> DisasterEvent | None:
        """解析FAN Studio消息 - 支持连接名称参数"""
        # 记录原始消息 - 使用连接名称作为数据源
        if self.message_logger:
            # 使用连接名称作为更精确的数据源标识
            log_source = connection_name or "fan_studio"
            self.message_logger.log_raw_message(
                source=log_source, message_type="websocket_message", raw_data=message
            )

        try:
            data = json.loads(message)

            # 添加详细日志用于调试
            logger.debug(
                f"[灾害预警] FAN Studio收到消息，类型: {data.get('type')}, 连接: {connection_name}, 消息长度: {len(message)}"
            )

            # 检查消息类型
            msg_type = data.get("type")
            if msg_type == "heartbeat":
                logger.debug("[灾害预警] 收到心跳消息，忽略")
                return None

            # 获取实际数据 - 注意FAN Studio使用大写D的Data字段
            msg_data = data.get("Data", {}) or data.get("data", {})
            if not msg_data:
                logger.warning("[灾害预警] 消息中没有Data/data字段")
                return None

            # 根据连接名称判断数据源 - 这是关键修复！
            logger.debug(
                f"[灾害预警] 连接名称: {connection_name}, 消息内容包含关键词检查"
            )

            # 添加详细的关键词检查日志
            keyword_checks = {
                "usgs": "usgs" in message,
                "cenc": "cenc" in message,
                "cea": "cea" in message,
                "cwa": "cwa" in message,
                "weatheralarm": "weatheralarm" in message,
                "weather": "weather" in message,
                "tsunami": "tsunami" in message,
            }
            logger.debug(f"[灾害预警] 关键词检查结果: {keyword_checks}")

            # 优先使用连接名称判断，其次使用消息内容关键词
            if connection_name:
                if "fan_studio_usgs" in connection_name or "usgs" in connection_name:
                    logger.info("[灾害预警] 根据连接名称识别为USGS数据，开始解析...")
                    return self._parse_usgs_data(msg_data)
                elif "fan_studio_cenc" in connection_name or "cenc" in connection_name:
                    logger.info("[灾害预警] 根据连接名称识别为CENC数据，开始解析...")
                    return self._parse_cenc_data(msg_data)
                elif "fan_studio_cea" in connection_name or "cea" in connection_name:
                    logger.info("[灾害预警] 根据连接名称识别为CEA数据，开始解析...")
                    return self._parse_cea_data(msg_data)
                elif "fan_studio_cwa" in connection_name or "cwa" in connection_name:
                    logger.info("[灾害预警] 根据连接名称识别为CWA数据，开始解析...")
                    return self._parse_cwa_data(msg_data)
                elif (
                    "fan_studio_weather" in connection_name
                    or "weather" in connection_name
                ):
                    logger.info(
                        "[灾害预警] 根据连接名称识别为气象预警数据，开始解析..."
                    )
                    return self._parse_weather_data(msg_data)
                elif (
                    "fan_studio_tsunami" in connection_name
                    or "tsunami" in connection_name
                ):
                    logger.info(
                        "[灾害预警] 根据连接名称识别为海啸预警数据，开始解析..."
                    )
                    return self._parse_tsunami_data(msg_data)

            # 回退到消息内容关键词检查 - 增强版本
            logger.debug(
                f"[灾害预警] 开始消息内容关键词检查，消息前256字符: {message[:256]}"
            )

            # 检查具体的数据字段特征，而不仅仅是连接名称
            if (
                "infoTypeName" in message and "[正式测定]" in message
            ):  # 中国地震台网正式测定
                logger.info(
                    "[灾害预警] 根据infoTypeName识别为CENC正式测定数据，开始解析..."
                )
                return self._parse_cenc_data(msg_data)
            elif (
                "infoTypeName" in message and "[自动测定]" in message
            ):  # 中国地震台网自动测定
                logger.info(
                    "[灾害预警] 根据infoTypeName识别为CENC自动测定数据，开始解析..."
                )
                return self._parse_cenc_data(msg_data)
            elif "eventId" in message and "CD." in message:  # 中国地震台网格式
                logger.info("[灾害预警] 根据eventId格式识别为CENC数据，开始解析...")
                return self._parse_cenc_data(msg_data)
            elif "epiIntensity" in message:  # 中国地震预警网格式
                logger.info("[灾害预警] 根据epiIntensity识别为CEA预警数据，开始解析...")
                return self._parse_cea_data(msg_data)
            elif (
                "maxIntensity" in message and "createTime" in message
            ):  # 台湾中央气象署格式
                logger.info("[灾害预警] 根据字段特征识别为CWA数据，开始解析...")
                return self._parse_cwa_data(msg_data)
            elif "headline" in message and "预警信号" in message:  # 气象预警
                logger.info("[灾害预警] 根据headline识别为气象预警数据，开始解析...")
                return self._parse_weather_data(msg_data)
            elif "warningInfo" in message and "title" in message:  # 海啸预警
                logger.info("[灾害预警] 根据warningInfo识别为海啸预警数据，开始解析...")
                return self._parse_tsunami_data(msg_data)
            elif (
                "usgs" in message or "placeName" in message and "updateTime" in message
            ):  # USGS
                logger.info("[灾害预警] 根据消息内容识别为USGS数据，开始解析...")
                return self._parse_usgs_data(msg_data)

            logger.warning(
                f"[灾害预警] 无法识别的数据源，连接: {connection_name}, 消息: {message[:256]}..."
            )

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] FAN Studio JSON解析失败: {e}")
        except Exception as e:
            logger.error(f"[灾害预警] FAN Studio消息处理失败: {e}")

        return None

    def _parse_cenc_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国地震台网数据"""
        try:
            earthquake = EarthquakeData(
                id=str(data.get("id", "")),
                event_id=data.get("eventId", ""),
                source=DataSource.FAN_STUDIO_CENC,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(data.get("shockTime", "")),
                latitude=float(data.get("latitude", 0)),
                longitude=float(data.get("longitude", 0)),
                depth=data.get("depth"),
                magnitude=data.get("magnitude"),
                place_name=data.get("placeName", ""),
                info_type=data.get("infoTypeName", ""),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析CENC数据失败: {e}")
            return None

    def _parse_cea_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国地震预警网数据"""
        try:
            earthquake = EarthquakeData(
                id=data.get("id", ""),
                event_id=data.get("eventId", ""),
                source=DataSource.FAN_STUDIO_CEA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("shockTime", "")),
                latitude=float(data.get("latitude", 0)),
                longitude=float(data.get("longitude", 0)),
                depth=data.get("depth"),
                magnitude=data.get("magnitude"),
                intensity=data.get("epiIntensity"),
                place_name=data.get("placeName", ""),
                province=data.get("province"),
                updates=data.get("updates", 1),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析CEA数据失败: {e}")
            return None

    def _parse_cwa_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析台湾中央气象署数据"""
        try:
            earthquake = EarthquakeData(
                id=str(data.get("id", "")),
                event_id=data.get("eventId", ""),
                source=DataSource.FAN_STUDIO_CWA,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("shockTime", "")),
                create_time=self._parse_datetime(data.get("createTime", "")),
                latitude=float(data.get("latitude", 0)),
                longitude=float(data.get("longitude", 0)),
                depth=data.get("depth"),
                magnitude=data.get("magnitude"),
                scale=_safe_float_convert(data.get("maxIntensity")),
                place_name=data.get("placeName", ""),
                updates=data.get("updates", 1),
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] FAN Studio CWA创建地震对象 - 震级: {earthquake.magnitude}, 震度: {earthquake.scale}, 位置: {earthquake.place_name}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析CWA数据失败: {e}")
            return None

    def _parse_usgs_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析USGS数据"""
        try:
            # 检查关键字段
            required_fields = ["id", "magnitude", "latitude", "longitude", "shockTime"]
            missing_fields = [
                field
                for field in required_fields
                if field not in data or data[field] is None
            ]
            if missing_fields:
                logger.warning(f"[灾害预警] USGS数据缺少关键字段: {missing_fields}")

            # 优化USGS数据精度 - 四舍五入到1位小数
            magnitude = data.get("magnitude")
            if magnitude is not None:
                try:
                    magnitude = round(float(magnitude), 1)
                except (ValueError, TypeError):
                    magnitude = None

            depth = data.get("depth")
            if depth is not None:
                try:
                    depth = round(float(depth), 1)
                except (ValueError, TypeError):
                    depth = None

            earthquake = EarthquakeData(
                id=data.get("id", ""),
                event_id=data.get("id", ""),
                source=DataSource.FAN_STUDIO_USGS,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(data.get("shockTime", "")),
                update_time=self._parse_datetime(data.get("updateTime", "")),
                latitude=float(data.get("latitude", 0)),
                longitude=float(data.get("longitude", 0)),
                depth=depth,  # 使用优化后的深度
                magnitude=magnitude,  # 使用优化后的震级
                place_name=data.get("placeName", ""),
                raw_data=data,
            )

            # 记录解析成功的地震信息
            logger.info(
                f"[灾害预警] USGS地震解析成功: 震级M{earthquake.magnitude}, 位置: {earthquake.place_name}, 时间: {earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析USGS数据失败: {e}, 数据内容: {data}")
            return None

    def _parse_weather_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析气象预警数据 - 修复时间字段提取"""
        try:
            # 检查关键字段
            required_fields = ["id", "headline", "effective", "description"]
            missing_fields = [
                field
                for field in required_fields
                if field not in data or data[field] is None
            ]
            if missing_fields:
                logger.warning(f"[灾害预警] 气象预警数据缺少关键字段: {missing_fields}")

            # 关键修复：提取真实的发布时间
            # API文档中只有effective字段（生效时间），没有发布时间
            # 使用生效时间作为发布时间，或者从ID中提取时间信息
            effective_time = self._parse_datetime(data.get("effective", ""))

            # 尝试从ID中提取发布时间（如：44170041600000_20250425123759）
            issue_time = None
            id_str = data.get("id", "")
            if "_" in id_str:
                time_part = id_str.split("_")[-1]  # 获取时间部分
                if len(time_part) >= 12:  # 期望格式：20250425123759
                    try:
                        year = int(time_part[0:4])
                        month = int(time_part[4:6])
                        day = int(time_part[6:8])
                        hour = int(time_part[8:10])
                        minute = int(time_part[10:12])
                        second = int(time_part[12:14]) if len(time_part) >= 14 else 0
                        issue_time = datetime(year, month, day, hour, minute, second)
                    except (ValueError, IndexError):
                        issue_time = effective_time  # 后备方案
                else:
                    issue_time = effective_time
            else:
                issue_time = effective_time

            weather = WeatherAlarmData(
                id=data.get("id", ""),
                source=DataSource.FAN_STUDIO_WEATHER,
                headline=data.get("headline", ""),
                title=data.get("title", ""),
                description=data.get("description", ""),
                type=data.get("type", ""),
                effective_time=effective_time,
                issue_time=issue_time,  # 关键修复：使用真实时间
                longitude=data.get("longitude"),
                latitude=data.get("latitude"),
                raw_data=data,
            )

            # 记录解析成功的气象预警信息
            logger.info(
                f"[灾害预警] 气象预警解析成功: {weather.headline}, 生效时间: {weather.effective_time}, 发布时间: {weather.issue_time}"
            )

            return DisasterEvent(
                id=weather.id,
                data=weather,
                source=weather.source,
                disaster_type=weather.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析气象预警数据失败: {e}, 数据内容: {data}")
            return None

    def _parse_tsunami_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析海啸预警数据 - 修复时间字段提取"""
        try:
            # 海啸数据可能包含多个事件
            events = []
            if isinstance(data, dict):
                # 单个事件
                events = [data]
            elif isinstance(data, list):
                # 多个事件
                events = data

            # 只处理第一个事件作为代表
            if not events:
                return None

            tsunami_data = events[0]

            # 关键修复：提取真实的时间信息
            # 从timeInfo对象中提取时间，如果没有则使用当前时间作为后备
            time_info = tsunami_data.get("timeInfo", {})
            issue_time_str = (
                time_info.get("issueTime") or time_info.get("publishTime") or ""
            )

            # 解析时间字符串，如果解析失败则使用当前时间
            if issue_time_str:
                issue_time = self._parse_datetime(issue_time_str)
            else:
                # 后备方案：尝试从其他字段提取时间
                # 从code字段提取时间信息（如：202507300724 表示2025-07-30 07:24）
                code = tsunami_data.get("code", "")
                if code and len(code) >= 10:
                    try:
                        # 假设code格式为：YYYYMMDDHHMM
                        year = int(code[0:4])
                        month = int(code[4:6])
                        day = int(code[6:8])
                        hour = int(code[8:10])
                        minute = int(code[10:12]) if len(code) >= 12 else 0
                        issue_time = datetime(year, month, day, hour, minute)
                    except (ValueError, IndexError):
                        issue_time = datetime.now()
                else:
                    issue_time = datetime.now()

            tsunami = TsunamiData(
                id=tsunami_data.get("id", ""),
                code=tsunami_data.get("code", ""),
                source=DataSource.FAN_STUDIO_TSUNAMI,
                title=tsunami_data.get("warningInfo", {}).get("title", ""),
                level=tsunami_data.get("warningInfo", {}).get("level", ""),
                subtitle=tsunami_data.get("warningInfo", {}).get("subtitle"),
                org_unit=tsunami_data.get("warningInfo", {}).get("orgUnit", ""),
                issue_time=issue_time,  # 关键修复：使用真实时间
                forecasts=tsunami_data.get("forecasts", []),
                monitoring_stations=tsunami_data.get("waterLevelMonitoring", []),
                raw_data=tsunami_data,
            )

            logger.info(
                f"[灾害预警] 海啸预警解析成功: {tsunami.title}, 级别: {tsunami.level}, 发布时间: {tsunami.issue_time}"
            )

            return DisasterEvent(
                id=tsunami.id,
                data=tsunami,
                source=tsunami.source,
                disaster_type=tsunami.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析海啸预警数据失败: {e}")
            return None


class P2PDataHandler(BaseDataHandler):
    """P2P地震情報数据处理器"""

    def __init__(self, message_logger=None):
        super().__init__(DataSource.P2P_EEW, message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析P2P消息"""
        # 记录原始消息
        if self.message_logger:
            self.message_logger.log_raw_message(
                source="p2p_earthquake",
                message_type="websocket_message",
                raw_data=message,
            )

        try:
            data = json.loads(message)

            # 根据code判断消息类型
            code = data.get("code")

            if code == 551:  # 地震情報
                logger.info("[灾害预警] P2P收到地震情報(code:551)，开始解析...")
                event = self._parse_earthquake_data(data)
                if event:
                    logger.info(f"[灾害预警] P2P地震情報解析成功，创建事件: {event.id}")
                else:
                    logger.warning("[灾害预警] P2P地震情報解析失败，返回None")
                return event

            elif code == 552:  # 津波予報
                logger.debug(f"[灾害预警] P2P收到津波予報，code: {code}")
                return self._parse_tsunami_data(data)
            elif code == 556:  # 緊急地震速報（警報）
                logger.debug(f"[灾害预警] P2P收到緊急地震速報（警報），code: {code}")
                return self._parse_eew_data(data)
            elif code == 554:  # 緊急地震速報 発表検出
                logger.debug(
                    f"[灾害预警] P2P收到緊急地震速報発表検出，忽略 - code: {code}"
                )
                return None  # 检测消息，不处理
            elif code == 555:  # 各地域ピア数
                logger.debug(f"[灾害预警] P2P收到各地域ピア数，忽略 - code: {code}")
                return None  # 节点数量，不处理
            elif code == 561:  # 地震感知情報
                logger.debug(f"[灾害预警] P2P收到地震感知情報，忽略 - code: {code}")
                return None  # 用户感知，不处理
            elif code == 9611:  # 地震感知情報 評価結果
                logger.debug(
                    f"[灾害预警] P2P收到地震感知情報評価結果，忽略 - code: {code}"
                )
                return None  # 评估结果，不处理
            else:
                logger.warning(
                    f"[灾害预警] P2P收到未知code类型: {code}，消息: {message[:128]}..."
                )
                return None

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] P2P JSON解析失败: {e}")
            logger.error(f"[灾害预警] 失败的消息内容: {message[:256]}...")
        except Exception as e:
            logger.error(f"[灾害预警] P2P消息处理失败: {e}")
            logger.error(f"[灾害预警] 异常时的消息内容: {message[:256]}...")
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

        logger.warning(
            "[灾害预警] P2P消息处理完成，返回None - 可能是解析失败或不符合处理条件"
        )
        return None

    def _parse_earthquake_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析地震情報 - 精准调试版本"""
        try:
            # 获取基础数据 - 使用英文键名（实际数据格式）
            earthquake_info = data.get("earthquake", {})
            hypocenter = earthquake_info.get("hypocenter", {})

            # 关键字段检查
            magnitude_raw = hypocenter.get("magnitude")
            place_name = hypocenter.get("name")
            latitude = hypocenter.get("latitude")
            longitude = hypocenter.get("longitude")

            logger.info(
                f"[灾害预警] P2P关键字段检查 - 震级: {magnitude_raw}, 地点: {place_name}, 纬度: {latitude}, 经度: {longitude}"
            )

            # 震级解析
            magnitude = _safe_float_convert(magnitude_raw)
            if magnitude is None:
                logger.error(f"[灾害预警] P2P震级解析失败: {magnitude_raw}")
                return None

            # 经纬度解析
            lat = _safe_float_convert(latitude)
            lon = _safe_float_convert(longitude)
            if lat is None or lon is None:
                logger.error(
                    f"[灾害预警] P2P经纬度解析失败: lat={latitude}, lon={longitude}"
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
            depth = _safe_float_convert(depth_raw)

            # 时间解析
            time_raw = earthquake_info.get("time", "")
            shock_time = self._parse_datetime(time_raw)

            logger.info(
                f"[灾害预警] P2P解析成功 - 震级: {magnitude}, 位置: {place_name}, 时间: {shock_time}"
            )

            earthquake = EarthquakeData(
                id=data.get("数据库ID", ""),  # P2P使用"数据库ID"字段
                event_id=data.get("数据库ID", ""),  # 同样用作event_id
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
                f"[灾害预警] P2P创建地震对象成功: {earthquake.magnitude}级, {earthquake.place_name}"
            )
            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )

        except Exception as e:
            logger.error(f"[灾害预警] P2P地震情報解析异常: {e}")
            logger.error(f"[灾害预警] 异常数据: {str(data)[:256]}...")
            return None

    def _convert_p2p_scale_to_standard(self, p2p_scale: int) -> float | None:
        """将P2P震度值转换为标准震度"""
        # P2P震度值映射表 (根据API文档)
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
            -1: None,  # 震度情報不存在
        }
        return scale_mapping.get(p2p_scale, None)

    def _parse_tsunami_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析津波予報 - 基于API文档修复时间字段"""
        try:
            issue_info = data.get("issue", {})
            areas = data.get("areas", [])

            # 基于API文档：P2P海啸预警使用issue.time作为发布时间
            # issue.time格式： "2019/06/18 22:24:00"（无秒数）
            issue_time_str = issue_info.get("time", "") or data.get("time", "")

            # 解析时间字符串，如果解析失败则使用当前时间作为后备
            if issue_time_str:
                issue_time = self._parse_datetime(issue_time_str)
            else:
                # 后备方案：使用根级别的time字段
                root_time = data.get("time", "")
                issue_time = (
                    self._parse_datetime(root_time) if root_time else datetime.now()
                )

            tsunami = TsunamiData(
                id=data.get("id", ""),
                code=str(data.get("code", "")),
                source=DataSource.P2P_EARTHQUAKE,  # P2P的津波也用这个源
                title=f"津波予報 - {issue_info.get('type', '')}",
                level="Warning"
                if any(area.get("grade") == "Warning" for area in areas)
                else "Watch",
                org_unit=issue_info.get("source", "気象庁"),
                issue_time=issue_time,  # ✅ 基于API文档添加正确的时间字段
                forecasts=[
                    {
                        "name": area.get("name", ""),
                        "grade": area.get("grade", ""),
                        "immediate": area.get("immediate", False),
                    }
                    for area in areas
                ],
                raw_data=data,
            )

            return DisasterEvent(
                id=tsunami.id,
                data=tsunami,
                source=tsunami.source,
                disaster_type=DisasterType.TSUNAMI,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析P2P津波予報失败: {e}")
            return None

    def _parse_eew_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析緊急地震速報（警報）"""
        try:
            earthquake_info = data.get("earthquake", {})
            hypocenter = earthquake_info.get("hypocenter", {})
            issue_info = data.get("issue", {})
            areas = data.get("areas", [])

            # 计算最大震度 - 需要检查scaleTo的格式
            raw_scales = [
                area.get("scaleTo", 0) for area in areas if area.get("scaleTo", 0) > 0
            ]
            if raw_scales:
                max_scale_raw = max(raw_scales)
                logger.debug(
                    f"[灾害预警] P2P EEW原始震度值: {raw_scales}, 最大: {max_scale_raw}"
                )
                # scaleTo很可能也是P2P震度编码，需要转换
                if max_scale_raw in [10, 20, 30, 40, 45, 50, 55, 60, 70]:
                    scale = self._convert_p2p_scale_to_standard(max_scale_raw)
                    logger.info(
                        f"[灾害预警] P2P EEW震度转换: {max_scale_raw} -> {scale}"
                    )
                else:
                    scale = max_scale_raw
                    logger.info(f"[灾害预警] P2P EEW震度无需转换: {scale}")
            else:
                scale = None
                max_scale_raw = 0

            earthquake = EarthquakeData(
                id=data.get("id", ""),
                event_id=issue_info.get("eventId", ""),
                source=DataSource.P2P_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(earthquake_info.get("originTime", "")),
                latitude=hypocenter.get("latitude", 0),
                longitude=hypocenter.get("longitude", 0),
                depth=hypocenter.get("depth"),
                magnitude=hypocenter.get("magnitude"),
                place_name=hypocenter.get("name", ""),
                scale=scale if scale is not None and scale > 0 else None,
                is_final=data.get("is_final", False),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析P2P緊急地震速報失败: {e}")
            return None


class WolfxDataHandler(BaseDataHandler):
    """Wolfx数据处理器"""

    def __init__(self, message_logger=None):
        super().__init__(DataSource.WOLFX_JMA_EEW, message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析Wolfx消息"""
        # 记录原始消息
        if self.message_logger:
            self.message_logger.log_raw_message(
                source="wolfx", message_type="websocket_message", raw_data=message
            )

        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            # 添加详细日志用于调试JMA问题
            logger.debug(f"[灾害预警] Wolfx收到消息，类型: {msg_type}, 数据: {data}")

            if msg_type == "jma_eew":
                logger.info(f"[灾害预警] 收到JMA紧急地震速报，类型: {msg_type}")
                return self._parse_jma_eew(data)
            elif msg_type == "cenc_eew":
                return self._parse_cenc_eew(data)
            elif msg_type == "cwa_eew":
                return self._parse_cwa_eew(data)
            elif msg_type == "cenc_eqlist":
                return self._parse_cenc_eqlist(data)
            elif msg_type == "jma_eqlist":
                return self._parse_jma_eqlist(data)
            else:
                logger.debug(f"[灾害预警] Wolfx收到未知类型消息: {msg_type}")

        except json.JSONDecodeError as e:
            logger.error(f"[灾害预警] Wolfx JSON解析失败: {e}")
        except Exception as e:
            logger.error(f"[灾害预警] Wolfx消息处理失败: {e}")

        return None

    def _parse_jma_eew(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析日本气象厅紧急地震速报"""
        try:
            # 详细记录JMA EEW数据内容，用于调试
            logger.info(
                f"[灾害预警] 开始解析JMA EEW数据: {json.dumps(data, ensure_ascii=False, indent=2)}"
            )

            # 检查关键字段是否存在
            required_fields = [
                "EventID",
                "OriginTime",
                "Latitude",
                "Longitude",
                "Magnitude",
            ]
            missing_fields = [
                field
                for field in required_fields
                if field not in data or data[field] is None
            ]
            if missing_fields:
                logger.warning(f"[灾害预警] JMA EEW数据缺少关键字段: {missing_fields}")

            earthquake = EarthquakeData(
                id=data.get("EventID", ""),
                event_id=data.get("EventID", ""),
                source=DataSource.WOLFX_JMA_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("OriginTime", "")),
                latitude=data.get("Latitude", 0),
                longitude=data.get("Longitude", 0),
                depth=data.get("Depth"),
                magnitude=data.get("Magnitude"),
                place_name=data.get("Hypocenter", ""),
                scale=self._parse_jma_scale(data.get("MaxIntensity", "")),
                is_final=data.get("isFinal", False),
                is_cancel=data.get("isCancel", False),
                is_training=data.get("isTraining", False),
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] Wolfx JMA创建地震对象 - 震级: {earthquake.magnitude}, 震度: {earthquake.scale}, 位置: {earthquake.place_name}"
            )

            # 记录解析后的地震数据
            logger.info(
                f"[灾害预警] JMA EEW解析成功: 震级={earthquake.magnitude}, 位置={earthquake.place_name}, 时间={earthquake.shock_time}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Wolfx JMA EEW失败: {e}, 数据: {data}")
            return None

    def _parse_cenc_eew(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国地震台网预警"""
        try:
            earthquake = EarthquakeData(
                id=data.get("ID", ""),
                event_id=data.get("EventID", ""),
                source=DataSource.WOLFX_CENC_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("OriginTime", "")),
                latitude=data.get("Latitude", 0),
                longitude=data.get("Longitude", 0),
                depth=data.get("Depth"),
                magnitude=data.get("Magnitude"),
                intensity=data.get("MaxIntensity"),
                place_name=data.get("HypoCenter", ""),
                updates=data.get("ReportNum", 1),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Wolfx CENC EEW失败: {e}")
            return None

    def _parse_cwa_eew(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析台湾地震预警"""
        try:
            earthquake = EarthquakeData(
                id=str(data.get("ID", "")),
                event_id=data.get("EventID", ""),
                source=DataSource.WOLFX_CWA_EEW,
                disaster_type=DisasterType.EARTHQUAKE_WARNING,
                shock_time=self._parse_datetime(data.get("OriginTime", "")),
                latitude=data.get("Latitude", 0),
                longitude=data.get("Longitude", 0),
                depth=data.get("Depth"),
                magnitude=data.get("Magnitude"),
                scale=self._parse_cwa_scale(data.get("MaxIntensity", "")),
                place_name=data.get("HypoCenter", ""),
                updates=data.get("ReportNum", 1),
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] Wolfx CWA创建地震对象 - 震级: {earthquake.magnitude}, 震度: {earthquake.scale}, 位置: {earthquake.place_name}"
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Wolfx CWA EEW失败: {e}")
            return None

    def _parse_cenc_eqlist(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析中国地震台网地震列表"""
        try:
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
                source=DataSource.WOLFX_CENC_EEW,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(eq_info.get("time", "")),
                latitude=float(eq_info.get("latitude", 0)),
                longitude=float(eq_info.get("longitude", 0)),
                depth=float(eq_info.get("depth", 0)) if eq_info.get("depth") else None,
                magnitude=float(eq_info.get("magnitude", 0))
                if eq_info.get("magnitude")
                else None,
                intensity=float(eq_info.get("intensity", 0))
                if eq_info.get("intensity")
                else None,
                place_name=eq_info.get("location", ""),
                info_type=eq_info.get("type", ""),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Wolfx CENC地震列表失败: {e}")
            return None

    def _parse_jma_eqlist(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析日本气象厅地震列表 - 修复深度字符串格式"""
        try:
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
                        logger.info(
                            f"[灾害预警] Wolfx JMA深度解析: {depth_raw} -> {depth}"
                        )
                    except (ValueError, TypeError) as e:
                        logger.error(
                            f"[灾害预警] Wolfx JMA深度解析失败: {depth_raw}, 错误: {e}"
                        )
                        depth = None
                else:
                    depth = _safe_float_convert(depth_raw)

            # 修复震级字段格式
            magnitude_raw = eq_info.get("magnitude")
            magnitude = _safe_float_convert(magnitude_raw)

            earthquake = EarthquakeData(
                id=eq_info.get("md5", ""),
                event_id=eq_info.get("md5", ""),
                source=DataSource.WOLFX_JMA_EEW,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(eq_info.get("time", "")),
                latitude=_safe_float_convert(eq_info.get("latitude")),
                longitude=_safe_float_convert(eq_info.get("longitude")),
                depth=depth,
                magnitude=magnitude,
                scale=self._parse_jma_scale(eq_info.get("shindo", "")),
                place_name=eq_info.get("location", ""),
                raw_data=data,
            )

            logger.info(
                f"[灾害预警] Wolfx JMA地震列表解析成功: {earthquake.magnitude}级, {earthquake.place_name}"
            )
            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Wolfx JMA地震列表失败: {e}")
            logger.error(f"[灾害预警] 异常数据: {str(data)[:256]}...")
            return None

    def _parse_jma_scale(self, scale_str: str) -> float | None:
        """解析日本震度"""
        if not scale_str:
            return None

        # 解析如 "5弱", "6強", "7" 等格式
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

    def _parse_cwa_scale(self, scale_str: str) -> float | None:
        """解析台湾震度"""
        if not scale_str:
            return None

        try:
            # 尝试直接解析数字
            return float(scale_str)
        except ValueError:
            return None


class GlobalQuakeHandler(BaseDataHandler):
    """Global Quake数据处理器"""

    def __init__(self, message_logger=None):
        super().__init__(DataSource.GLOBAL_QUAKE, message_logger)

    def parse_message(self, message: str) -> DisasterEvent | None:
        """解析Global Quake消息"""
        try:
            # Global Quake的消息格式需要根据实际情况调整
            # 这里假设是JSON格式
            data = json.loads(message)

            # 根据消息内容判断类型
            if "earthquake" in data or "magnitude" in data:
                return self._parse_earthquake_data(data)

        except json.JSONDecodeError:
            # 如果不是JSON，尝试其他格式
            return self._parse_text_message(message)
        except Exception as e:
            logger.error(f"[灾害预警] Global Quake消息处理失败: {e}")

        return None

    def _parse_earthquake_data(self, data: dict[str, Any]) -> DisasterEvent | None:
        """解析地震数据"""
        try:
            earthquake = EarthquakeData(
                id=data.get("id", ""),
                event_id=data.get("event_id", ""),
                source=DataSource.GLOBAL_QUAKE,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=self._parse_datetime(data.get("time", "")),
                latitude=data.get("latitude", 0),
                longitude=data.get("longitude", 0),
                depth=data.get("depth"),
                magnitude=data.get("magnitude"),
                intensity=data.get("intensity"),
                place_name=data.get("location", ""),
                raw_data=data,
            )

            return DisasterEvent(
                id=earthquake.id,
                data=earthquake,
                source=earthquake.source,
                disaster_type=earthquake.disaster_type,
            )
        except Exception as e:
            logger.error(f"[灾害预警] 解析Global Quake地震数据失败: {e}")
            return None

    def _parse_text_message(self, message: str) -> DisasterEvent | None:
        """解析文本消息"""
        # 这里可以实现文本解析逻辑
        # 根据Global Quake的实际消息格式来解析
        logger.debug(f"[灾害预警] Global Quake文本消息: {message}")
        return None


# 处理器映射
DATA_HANDLERS = {
    "fan_studio": FanStudioHandler,
    "p2p": P2PDataHandler,
    "wolfx": WolfxDataHandler,
    "global_quake": GlobalQuakeHandler,
}


# 安全浮点数转换函数（模块级别）
def _safe_float_convert(value) -> float | None:
    """安全地将值转换为浮点数"""
    if value is None:
        return None
    try:
        # 处理字符串情况
        if isinstance(value, str):
            value = value.strip()
            if not value or value == "":
                return None
        return float(value)
    except (ValueError, TypeError):
        return None


def get_data_handler(handler_type: str) -> BaseDataHandler:
    """获取数据处理器"""
    handler_class = DATA_HANDLERS.get(handler_type)
    if handler_class:
        return handler_class()
    return None
