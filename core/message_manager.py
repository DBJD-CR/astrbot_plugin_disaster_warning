"""
消息推送管理器
实现优化的报数控制、拆分过滤器和改进的去重逻辑
"""

import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ..models.data_source_config import (
    get_intensity_based_sources,
    get_scale_based_sources,
    get_sources_needing_report_control,
)
from ..utils.message_formatters import (
    BaseMessageFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)
from ..models.models import (
    DataSource,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from .intensity_calculator import IntensityCalculator


class IntensityFilter:
    """烈度过滤器 - 专门处理使用烈度的数据源"""

    def __init__(self, min_magnitude: float = 0, min_intensity: float = 0):
        self.min_magnitude = min_magnitude
        self.min_intensity = min_intensity

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 检查震级
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        # 检查烈度
        if (
            earthquake.intensity is not None
            and earthquake.intensity < self.min_intensity
        ):
            logger.debug(
                f"[灾害预警] 烈度 {earthquake.intensity} < 最小烈度 {self.min_intensity}"
            )
            return True

        return False


class ScaleFilter:
    """震度过滤器 - 专门处理使用震度的数据源"""

    def __init__(self, min_magnitude: float = 0, min_scale: float = 0):
        self.min_magnitude = min_magnitude
        self.min_scale = min_scale

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 检查震级
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        # 检查震度
        if earthquake.scale is not None and earthquake.scale < self.min_scale:
            logger.debug(
                f"[灾害预警] 震度 {earthquake.scale} < 最小震度 {self.min_scale}"
            )
            return True

        return False


class USGSFilter:
    """USGS专用过滤器 - 只检查震级"""

    def __init__(self, min_magnitude: float = 0):
        self.min_magnitude = min_magnitude

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # USGS只检查震级
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        return False

class LocalIntensityFilter:
    """本地烈度过滤器"""
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.latitude = config.get("latitude", 0.0)
        self.longitude = config.get("longitude", 0.0)
        self.threshold = config.get("intensity_threshold", 2.0)
        self.strict_mode = config.get("strict_mode", False)
        self.place_name = config.get("place_name", "本地")

    def check_event(self, earthquake: EarthquakeData) -> tuple[bool, float, float]:
        """
        检查事件是否需要推送
        :return: (is_allowed, distance, intensity)
        """
        if not self.enabled:
            return True, 0.0, 0.0

        if earthquake.latitude is None or earthquake.longitude is None:
             # 如果没有坐标，严格模式下过滤，非严格模式下允许
            return not self.strict_mode, 0.0, 0.0

        distance = IntensityCalculator.calculate_distance(
            earthquake.latitude, earthquake.longitude,
            self.latitude, self.longitude
        )
        
        intensity = IntensityCalculator.calculate_estimated_intensity(
            earthquake.magnitude or 0.0,
            distance,
            earthquake.depth or 10.0,
            event_longitude=earthquake.longitude # 传入经度以区分东西部
        )
        
        if self.strict_mode:
            if intensity < self.threshold:
                logger.info(f"[灾害预警] 本地烈度 {intensity:.1f} < 阈值 {self.threshold}，严格模式已过滤")
                return False, distance, intensity
        
        return True, distance, intensity


class ReportCountController:
    """报数控制器 - 仅对EEW数据源生效"""

    def __init__(
        self,
        push_every_n_reports: int = 3,
        first_report_always_push: bool = True,
        final_report_always_push: bool = True,
    ):
        self.push_every_n_reports = push_every_n_reports
        self.first_report_always_push = first_report_always_push
        self.final_report_always_push = final_report_always_push
        # 记录每个事件的报数推送情况
        self.event_report_counts: dict[str, int] = defaultdict(int)

    def should_push_report(self, event: DisasterEvent) -> bool:
        """判断是否推送该报数"""
        if not isinstance(event.data, EarthquakeData):
            return True  # 非地震事件直接推送

        earthquake = event.data
        source_id = self._get_source_id(event)

        # 只对需要报数控制的数据源生效
        if source_id not in get_sources_needing_report_control():
            return True

        event_id = earthquake.event_id or earthquake.id
        current_report = getattr(earthquake, "updates", 1)
        is_final = getattr(earthquake, "is_final", False)

        # 最终报总是推送
        if is_final and self.final_report_always_push:
            logger.debug(f"[灾害预警] 事件 {event_id} 是最终报，允许推送")
            return True

        # 第1报总是推送
        if current_report == 1 and self.first_report_always_push:
            logger.debug(f"[灾害预警] 事件 {event_id} 是第1报，允许推送")
            return True

        # 检查报数控制
        if current_report % self.push_every_n_reports == 0:
            logger.debug(
                f"[灾害预警] 事件 {event_id} 第 {current_report} 报，符合报数控制规则"
            )
            return True

        logger.debug(
            f"[灾害预警] 事件 {event_id} 第 {current_report} 报，被报数控制过滤"
        )
        return False

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        # 将DataSource映射到我们的source_id
        source_mapping = {
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
        }

        return source_mapping.get(event.source.value, "")


class EventDeduplicator:
    """事件去重器 - 允许多数据源推送同一事件"""

    def __init__(
        self,
        time_window_minutes: int = 1,
        location_tolerance_km: float = 20.0,
        magnitude_tolerance: float = 0.5,
    ):
        self.time_window = timedelta(minutes=time_window_minutes)
        self.location_tolerance = location_tolerance_km
        self.magnitude_tolerance = magnitude_tolerance

        # 记录每个数据源的事件：事件指纹 -> {数据源: 事件信息}
        self.recent_events: dict[str, dict[str, dict]] = {}

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件 - 允许多数据源推送同一事件"""
        if not isinstance(event.data, EarthquakeData):
            return True  # 非地震事件直接推送

        earthquake = event.data
        source_id = self._get_source_id(event)

        # 生成事件指纹
        event_fingerprint = self._generate_event_fingerprint(earthquake)

        # 关键修复：如果地震时间解析失败，使用当前时间作为后备
        current_time = (
            earthquake.shock_time
            if earthquake.shock_time is not None
            else datetime.now()
        )

        logger.debug(
            f"[灾害预警] 检查事件: {event.source.value}, 指纹: {event_fingerprint}"
        )

        # 检查是否已有相似事件
        if event_fingerprint in self.recent_events:
            source_events = self.recent_events[event_fingerprint]

            # 检查同一数据源是否已推送过
            if source_id in source_events:
                existing_event = source_events[source_id]

                # 如果在时间窗口内，检查是否允许更新
                time_diff = abs(
                    (current_time - existing_event["timestamp"]).total_seconds() / 60
                )

                if time_diff <= self.time_window.total_seconds() / 60:
                    if self._should_allow_update(earthquake, existing_event):
                        logger.info(
                            f"[灾害预警] 允许同一数据源更新: {event.source.value}"
                        )
                        # 更新记录 - 添加当前报数到已处理集合
                        current_report = getattr(earthquake, "updates", 1)
                        existing_event["processed_reports"].add(current_report)
                        existing_event["timestamp"] = current_time
                        existing_event["is_final"] = existing_event["is_final"] or getattr(earthquake, "is_final", False)
                        return True
                    else:
                        logger.info(
                            f"[灾害预警] 同一数据源重复事件，过滤: {event.source.value}"
                        )
                        return False
                else:
                    logger.debug("[灾害预警] 同一数据源事件已过期，允许推送")

            # 不同数据源，允许推送（允许多数据源推送同一事件）
            logger.info(f"[灾害预警] 不同数据源，允许推送: {event.source.value}")
            current_report = getattr(earthquake, "updates", 1)
            self.recent_events[event_fingerprint][source_id] = {
                "timestamp": current_time,
                "source": event.source.value,
                "latitude": earthquake.latitude or 0,
                "longitude": earthquake.longitude or 0,
                "magnitude": earthquake.magnitude or 0,
                "info_type": earthquake.info_type or "",
                "processed_reports": {current_report},  # 使用集合存储已处理的报数
                "is_final": getattr(earthquake, "is_final", False),
            }
            return True

        # 新事件，记录并允许推送
        current_report = getattr(earthquake, "updates", 1)
        self.recent_events[event_fingerprint] = {
            source_id: {
                "timestamp": current_time,
                "source": event.source.value,
                "latitude": earthquake.latitude or 0,
                "longitude": earthquake.longitude or 0,
                "magnitude": earthquake.magnitude or 0,
                "info_type": earthquake.info_type or "",
                "processed_reports": {current_report},  # 使用集合存储已处理的报数
                "is_final": getattr(earthquake, "is_final", False),
            }
        }

        logger.info(f"[灾害预警] 允许推送新事件: {event.source.value}")
        return True

    def _generate_event_fingerprint(self, earthquake: EarthquakeData) -> str:
        """生成事件指纹 - 基于地理位置和震级的简化指纹"""
        if not earthquake.latitude or not earthquake.longitude:
            return "unknown_location"

        # 将坐标量化到指定精度（20km网格）
        lat_grid = round(earthquake.latitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )
        lon_grid = round(earthquake.longitude * (111.0 / self.location_tolerance)) / (
            111.0 / self.location_tolerance
        )

        # 震级量化到容差级别
        mag_grid = (
            round((earthquake.magnitude or 0) / self.magnitude_tolerance)
            * self.magnitude_tolerance
        )

        # 关键修复：处理时间可能为None的情况
        if earthquake.shock_time is not None:
            time_minute = earthquake.shock_time.replace(second=0, microsecond=0)
        else:
            # 如果时间解析失败，使用当前时间但标记为特殊值
            time_minute = datetime.now().replace(second=0, microsecond=0)

        return f"{lat_grid:.3f},{lon_grid:.3f},{mag_grid:.1f},{time_minute.strftime('%Y%m%d%H%M')}"

    def _should_allow_update(
        self, current_earthquake: EarthquakeData, existing_event: dict
    ) -> bool:
        """判断是否应该允许事件更新"""
        # 获取当前报数
        current_report = getattr(current_earthquake, "updates", 1)
        
        # 获取已处理的报数集合（兼容旧格式）
        processed_reports = existing_event.get("processed_reports", set())
        if not isinstance(processed_reports, set):
            # 兼容旧的 updates 字段格式
            old_updates = existing_event.get("updates", 1)
            processed_reports = {old_updates}
        
        # 检查当前报数是否已处理过
        if current_report not in processed_reports:
            logger.info(
                f"[灾害预警] 新报数: 第{current_report}报 (已处理: {sorted(processed_reports)})"
            )
            return True

        # 最终报检查 - 即使报数已处理，如果变为最终报也允许
        if getattr(current_earthquake, "is_final", False) and not existing_event.get(
            "is_final", False
        ):
            logger.info("[灾害预警] 最终报更新: 非最终报 -> 最终报")
            return True

        # USGS状态升级
        if current_earthquake.source == DataSource.FAN_STUDIO_USGS:
            current_info_type = (current_earthquake.info_type or "").lower()
            existing_info_type = (existing_event.get("info_type", "") or "").lower()

            if existing_info_type == "automatic" and current_info_type == "reviewed":
                logger.debug("[灾害预警] 允许USGS状态升级: automatic -> reviewed")
                return True

        # 通用状态升级（针对CENC等）
        current_info_type = (current_earthquake.info_type or "").lower()
        existing_info_type = (existing_event.get("info_type", "") or "").lower()

        # 自动测定 -> 正式测定
        if "自动" in existing_info_type and "正式" in current_info_type:
            logger.info(
                f"[灾害预警] 允许状态升级: {existing_info_type} -> {current_info_type}"
            )
            return True

        logger.debug(f"[灾害预警] 报数 {current_report} 已处理过，跳过")
        return False

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        source_mapping = {
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.P2P_EARTHQUAKE.value: "jma_p2p_info",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            DataSource.FAN_STUDIO_CENC.value: "cenc_fanstudio",
            DataSource.FAN_STUDIO_USGS.value: "usgs_fanstudio",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
        }

        return source_mapping.get(event.source.value, event.source.value)

    def cleanup_old_events(self):
        """清理过期事件"""
        cutoff_time = datetime.now() - self.time_window * 2  # 保留2倍时间窗口

        old_fingerprints = []
        for fingerprint, source_events in self.recent_events.items():
            # 检查所有数据源的事件是否都过期
            all_expired = True
            for event_info in source_events.values():
                if event_info["timestamp"] >= cutoff_time:
                    all_expired = False
                    break

            if all_expired:
                old_fingerprints.append(fingerprint)

        for fingerprint in old_fingerprints:
            del self.recent_events[fingerprint]


class MessagePushManager:
    """消息推送管理器"""

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context

        # 初始化过滤器 - 使用新的配置路径
        earthquake_filters = config.get("earthquake_filters", {})

        # 烈度过滤器配置
        intensity_filter_config = earthquake_filters.get("intensity_filter", {})
        self.intensity_filter = IntensityFilter(
            min_magnitude=intensity_filter_config.get("min_magnitude", 2.0),
            min_intensity=intensity_filter_config.get("min_intensity", 4.0),
        )

        # 震度过滤器配置
        scale_filter_config = earthquake_filters.get("scale_filter", {})
        self.scale_filter = ScaleFilter(
            min_magnitude=scale_filter_config.get("min_magnitude", 2.0),
            min_scale=scale_filter_config.get("min_scale", 1.0),
        )

        # USGS过滤器配置
        magnitude_only_filter_config = earthquake_filters.get(
            "magnitude_only_filter", {}
        )
        self.usgs_filter = USGSFilter(
            min_magnitude=magnitude_only_filter_config.get("min_magnitude", 4.5)
        )

        # 初始化报数控制器
        self.report_controller = ReportCountController(
            push_every_n_reports=config.get("push_frequency_control", {}).get(
                "push_every_n_reports", 3
            ),
            first_report_always_push=config.get("push_frequency_control", {}).get(
                "first_report_always_push", True
            ),
            final_report_always_push=config.get("push_frequency_control", {}).get(
                "final_report_always_push", True
            ),
        )

        # 初始化去重器
        self.deduplicator = EventDeduplicator(
            time_window_minutes=config.get("event_deduplication", {}).get(
                "time_window_minutes", 1
            ),
            location_tolerance_km=config.get("event_deduplication", {}).get(
                "location_tolerance_km", 20.0
            ),
            magnitude_tolerance=config.get("event_deduplication", {}).get(
                "magnitude_tolerance", 0.5
            ),
        )

        # 事件推送记录
        self.event_push_records: dict[str, list[dict]] = defaultdict(list)

        # 目标会话
        self.target_sessions = self._parse_target_sessions()
        
        # 初始化本地监控过滤器
        self.local_monitor = LocalIntensityFilter(config.get("local_monitoring", {}))

    def _parse_target_sessions(self) -> list[str]:
        """解析目标会话 - 使用正确的配置键名"""
        target_groups = self.config.get("target_groups", [])
        sessions = []

        for group_id in target_groups:
            if group_id:
                # 使用正确的会话ID格式
                platform_name = self.config.get("platform_name", "aiocqhttp")
                session = f"{platform_name}:GroupMessage:{group_id}"
                sessions.append(session)

        return sessions

    def should_push_event(self, event: DisasterEvent) -> bool:
        """判断是否应该推送事件"""
        # 1. 时间检查（所有事件类型）- 这是最重要的过滤
        event_time = self._get_event_time(event)
        if event_time:
            time_diff = (datetime.now() - event_time).total_seconds() / 3600  # 小时
            if time_diff > 1:
                logger.info(f"[灾害预警] 事件时间过早（{time_diff:.1f}小时前），过滤")
                return False

        # 2. 非地震事件检查
        if not isinstance(event.data, EarthquakeData):
            # 对于海啸和气象事件，只进行时间检查，其他过滤逻辑不适用
            return True

        # 3. 地震事件专用过滤逻辑
        earthquake = event.data
        source_id = self._get_source_id(event)

        # 数据源专用过滤器
        if source_id in get_intensity_based_sources():
            # 使用烈度过滤器
            if self.intensity_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被烈度过滤器过滤: {source_id}")
                return False
        elif source_id in get_scale_based_sources():
            # 使用震度过滤器
            if self.scale_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被震度过滤器过滤: {source_id}")
                return False
        elif source_id == "usgs_fanstudio":
            # USGS专用过滤器
            if self.usgs_filter.should_filter(earthquake):
                logger.info(f"[灾害预警] 事件被USGS过滤器过滤: {source_id}")
                return False

        # 报数控制（仅EEW数据源）
        if not self.report_controller.should_push_report(event):
            logger.info(f"[灾害预警] 事件被报数控制器过滤: {source_id}")
            return False

        # 本地烈度过滤
        is_allowed, distance, intensity = self.local_monitor.check_event(earthquake)
        if not is_allowed:
            return False
            
        # 保存计算结果供消息构建使用
        event.raw_data["local_estimation"] = {
            "distance": distance,
            "intensity": intensity
        }

        return True

    def _get_event_time(self, event: DisasterEvent) -> datetime | None:
        """获取灾害事件的时间"""
        if isinstance(event.data, EarthquakeData):
            return event.data.shock_time
        elif isinstance(event.data, TsunamiData):
            return event.data.issue_time
        elif isinstance(event.data, WeatherAlarmData):
            return event.data.effective_time or event.data.issue_time
        return None

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        source_mapping = {
            # EEW预警数据源
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.P2P_EEW.value: "jma_p2p",
            DataSource.WOLFX_JMA_EEW.value: "jma_wolfx",
            # 地震情报数据源
            DataSource.FAN_STUDIO_CENC.value: "cenc_fanstudio",
            DataSource.WOLFX_CENC_EQ.value: "cenc_wolfx",
            DataSource.P2P_EARTHQUAKE.value: "jma_p2p_info",
            DataSource.WOLFX_JMA_EQ.value: "jma_wolfx_info",
            DataSource.FAN_STUDIO_USGS.value: "usgs_fanstudio",
            DataSource.GLOBAL_QUAKE.value: "global_quake",
            # 气象和海啸预警数据源
            DataSource.FAN_STUDIO_WEATHER.value: "china_weather_fanstudio",
            DataSource.FAN_STUDIO_TSUNAMI.value: "china_tsunami_fanstudio",
            DataSource.P2P_TSUNAMI.value: "jma_tsunami_p2p",
        }

        return source_mapping.get(event.source.value, event.source.value)

    async def push_event(self, event: DisasterEvent) -> bool:
        """推送事件"""
        logger.debug(f"[灾害预警] 处理事件推送: {event.id}")

        # 1. 先去重检查 - 允许多数据源推送同一事件
        if not self.deduplicator.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 被去重器过滤")
            return False

        # 2. 推送条件检查
        if not self.should_push_event(event):
            logger.debug(f"[灾害预警] 事件 {event.id} 未通过推送条件检查")
            return False

        try:
            # 3. 构建消息
            message = self._build_message(event)
            logger.debug("[灾害预警] 消息构建完成")

            # 4. 获取目标会话
            target_sessions = self.target_sessions
            if not target_sessions:
                logger.warning("[灾害预警] 没有配置目标会话，无法推送消息")
                return False

            # 5. 推送消息
            push_success_count = 0
            for session in target_sessions:
                try:
                    await self._send_message(session, message)
                    logger.info(f"[灾害预警] 消息已推送到 {session}")
                    push_success_count += 1
                except Exception as e:
                    logger.error(f"[灾害预警] 推送到 {session} 失败: {e}")

            # 6. 记录推送
            self._record_push(event)
            logger.info(
                f"[灾害预警] 事件 {event.id} 推送完成，成功推送到 {push_success_count} 个会话"
            )
            return push_success_count > 0

        except Exception as e:
            logger.error(f"[灾害预警] 推送事件失败: {e}")
            return False

    def _build_message(self, event: DisasterEvent) -> MessageChain:
        """构建消息 - 使用格式化器并应用消息格式配置"""
        source_id = self._get_source_id(event)

        # 获取消息格式配置
        message_format_config = self.config.get("message_format", {})
        include_map = message_format_config.get("include_map", True)
        map_provider = message_format_config.get("map_provider", "baidu")
        map_zoom_level = message_format_config.get("map_zoom_level", 5)

        logger.debug(
            f"[灾害预警] 地图配置: provider={map_provider}, zoom={map_zoom_level}"
        )

        if isinstance(event.data, WeatherAlarmData):
            message_text = format_weather_message(source_id, event.data)
        elif isinstance(event.data, TsunamiData):
            message_text = format_tsunami_message(source_id, event.data)
        elif isinstance(event.data, EarthquakeData):
            message_text = format_earthquake_message(source_id, event.data)
        else:
            # 未知事件类型，使用基础格式化
            logger.warning(f"[灾害预警] 未知事件类型: {type(event.data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 添加本地预估信息
        if isinstance(event.data, EarthquakeData) and self.local_monitor.enabled:
            local_est = event.raw_data.get("local_estimation")
            if local_est:
                dist = local_est["distance"]
                inte = local_est["intensity"]
                
                # 只要有计算结果就显示，即使是0
                desc, _ = IntensityCalculator.get_intensity_description(inte)
                place = self.local_monitor.place_name
                message_text += f"\n\n📍 {place}预估：\n据震中 {dist:.1f}km，预估烈度 {inte:.1f}级 ({desc})"

        # 构建消息链
        if include_map and isinstance(event.data, EarthquakeData):
            if event.data.latitude is not None and event.data.longitude is not None:
                # 使用消息格式化器中的优化地图链接生成
                from ..utils.message_formatters import BaseMessageFormatter

                map_url = BaseMessageFormatter.get_map_link(
                    event.data.latitude,
                    event.data.longitude,
                    map_provider,
                    map_zoom_level,
                    magnitude=event.data.magnitude,
                    place_name=event.data.place_name,
                )
                if map_url:
                    # 关键修复：绕过AstrBot的strip()问题
                    # 使用零宽空格保护换行，URL编码确保特殊字符处理
                    zero_width_space = "\u200b"
                    encoded_map_url = urllib.parse.quote(map_url, safe=":/?&=+")
                    
                    # 直接合并到消息文本中
                    message_text += f"{zero_width_space}\n🗺️地图链接:{zero_width_space} {encoded_map_url}"

        # 构建消息链
        chain = [Comp.Plain(message_text)]
        return MessageChain(chain)

    def _generate_map_link(
        self, latitude: float, longitude: float, provider: str, zoom: int
    ) -> str:
        """根据配置生成地图链接 - 已移至message_formatters模块"""
        # 这个方法现在由message_formatters模块处理
        return BaseMessageFormatter.get_map_link(
            latitude,
            longitude,
            provider,
            zoom,
            magnitude=None,  # 这个方法没有震级信息，使用默认值
            place_name=None,  # 这个方法没有位置信息，使用默认值
        )

    async def _send_message(self, session: str, message: MessageChain):
        """发送消息到指定会话"""
        await self.context.send_message(session, message)

    def _record_push(self, event: DisasterEvent):
        """记录推送"""
        event_id = self._get_event_id(event)

        # 记录推送信息
        push_info = {
            "timestamp": datetime.now(),
            "event_id": event_id,
            "disaster_type": event.disaster_type.value,
            "source": self._get_source_id(event),
        }

        self.event_push_records[event_id].append(push_info)

    def _get_event_id(self, event: DisasterEvent) -> str:
        """获取事件ID"""
        if isinstance(event.data, EarthquakeData):
            return event.data.event_id or event.data.id
        elif isinstance(event.data, (TsunamiData, WeatherAlarmData)):
            return event.data.id
        return event.id

    def get_push_stats(self) -> dict[str, Any]:
        """获取推送统计"""
        total_events = len(self.event_push_records)
        total_pushes = sum(len(records) for records in self.event_push_records.values())

        return {
            "total_events": total_events,
            "total_pushes": total_pushes,
            "recent_events": self._get_recent_events(),
        }

    def _get_recent_events(self, hours: int = 24) -> list[dict]:
        """获取最近的事件"""
        recent_time = datetime.now() - timedelta(hours=hours)
        recent_events = []

        for event_id, records in self.event_push_records.items():
            recent_records = [
                record for record in records if record["timestamp"] > recent_time
            ]

            if recent_records:
                recent_events.append(
                    {
                        "event_id": event_id,
                        "push_count": len(recent_records),
                        "last_push": max(
                            record["timestamp"] for record in recent_records
                        ),
                    }
                )

        return sorted(recent_events, key=lambda x: x["last_push"], reverse=True)

    def cleanup_old_records(self, days: int = 7):
        """清理旧记录"""
        cutoff_time = datetime.now() - timedelta(days=days)

        # 清理事件推送记录
        for event_id in list(self.event_push_records.keys()):
            records = self.event_push_records[event_id]
            recent_records = [
                record for record in records if record["timestamp"] > cutoff_time
            ]

            if recent_records:
                self.event_push_records[event_id] = recent_records
            else:
                del self.event_push_records[event_id]

        # 清理去重器
        self.deduplicator.cleanup_old_events()

        logger.info(f"[灾害预警] 已清理 {days} 天前的推送记录")
