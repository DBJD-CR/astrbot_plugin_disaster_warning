"""
消息推送管理器
实现优化的报数控制、拆分过滤器和改进的去重逻辑
"""

import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import MessageChain

from ..models.data_source_config import (
    get_intensity_based_sources,
    get_scale_based_sources,
)
from ..models.models import (
    DataSource,
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ..utils.formatters import (
    BaseMessageFormatter,
    format_earthquake_message,
    format_tsunami_message,
    format_weather_message,
)



from .filters import (
    IntensityFilter,
    ScaleFilter,
    USGSFilter,
    LocalIntensityFilter,
    ReportCountController,
)
from .event_deduplicator import EventDeduplicator


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
            enabled=intensity_filter_config.get("enabled", True),
            min_magnitude=intensity_filter_config.get("min_magnitude", 2.0),
            min_intensity=intensity_filter_config.get("min_intensity", 4.0),
        )

        # 震度过滤器配置
        scale_filter_config = earthquake_filters.get("scale_filter", {})
        self.scale_filter = ScaleFilter(
            enabled=scale_filter_config.get("enabled", True),
            min_magnitude=scale_filter_config.get("min_magnitude", 2.0),
            min_scale=scale_filter_config.get("min_scale", 1.0),
        )

        # USGS过滤器配置
        magnitude_only_filter_config = earthquake_filters.get(
            "magnitude_only_filter", {}
        )
        self.usgs_filter = USGSFilter(
            enabled=magnitude_only_filter_config.get("enabled", True),
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
        # 获取带时区的事件时间
        event_time_aware = self._get_event_time(event)

        if event_time_aware:
            # 使用UTC当前时间进行比较，确保时区无关性
            current_time_utc = datetime.now(timezone.utc)
            time_diff = (
                current_time_utc - event_time_aware
            ).total_seconds() / 3600  # 小时

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
            "intensity": intensity,
            "place_name": self.local_monitor.place_name,
        }

        return True

    def _get_event_time(self, event: DisasterEvent) -> datetime | None:
        """获取灾害事件的带时区时间 (Aware Datetime)"""
        raw_time = None
        if isinstance(event.data, EarthquakeData):
            raw_time = event.data.shock_time
        elif isinstance(event.data, TsunamiData):
            raw_time = event.data.issue_time
        elif isinstance(event.data, WeatherAlarmData):
            raw_time = event.data.effective_time or event.data.issue_time

        if not raw_time:
            return None

        # 如果已经是Aware时间，直接返回
        if raw_time.tzinfo is not None:
            return raw_time

        # 根据数据源ID确定时区
        source_id = event.source_id or self._get_source_id(event)

        # 定义时区
        # JST (UTC+9)
        tz_jst = timezone(timedelta(hours=9))
        # CST (UTC+8)
        tz_cst = timezone(timedelta(hours=8))
        # UTC
        tz_utc = timezone.utc

        # 1. UTC+9 数据源
        # - Fan Studio JMA
        # - P2P Quake (所有)
        # - Wolfx JMA
        if (
            "jma" in source_id
            or "p2p" in source_id
            or source_id == "wolfx_jma_eew"
            or source_id == "wolfx_jma_eq"
        ):
            return raw_time.replace(tzinfo=tz_jst)

        # 2. UTC 数据源
        # - Global Quake
        if "global_quake" in source_id:
            return raw_time.replace(tzinfo=tz_utc)

        # 3. UTC+8 数据源 (默认)
        # - Fan Studio (除了 JMA, USGS已转为UTC+8)
        # - Wolfx (除了 JMA)
        # - China Weather/Tsunami
        return raw_time.replace(tzinfo=tz_cst)

    def _get_source_id(self, event: DisasterEvent) -> str:
        """获取事件的数据源ID"""
        source_mapping = {
            # EEW预警数据源
            DataSource.FAN_STUDIO_CEA.value: "cea_fanstudio",
            DataSource.WOLFX_CENC_EEW.value: "cea_wolfx",
            DataSource.FAN_STUDIO_CWA.value: "cwa_fanstudio",
            DataSource.WOLFX_CWA_EEW.value: "cwa_wolfx",
            DataSource.FAN_STUDIO_JMA.value: "jma_fanstudio",
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
        detailed_jma = message_format_config.get("detailed_jma_intensity", False)

        logger.debug(
            f"[灾害预警] 消息配置: provider={map_provider}, zoom={map_zoom_level}, detailed_jma={detailed_jma}"
        )

        if isinstance(event.data, WeatherAlarmData):
            message_text = format_weather_message(source_id, event.data)
        elif isinstance(event.data, TsunamiData):
            message_text = format_tsunami_message(source_id, event.data)
        elif isinstance(event.data, EarthquakeData):
            # 传递配置选项
            options = {"detailed_jma_intensity": detailed_jma}
            message_text = format_earthquake_message(source_id, event.data, options)
        else:
            # 未知事件类型，使用基础格式化
            logger.warning(f"[灾害预警] 未知事件类型: {type(event.data)}")
            message_text = f"🚨[未知事件]\n📋事件ID：{event.id}\n⏰时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # 构建消息链
        if include_map and isinstance(event.data, EarthquakeData):
            if event.data.latitude is not None and event.data.longitude is not None:
                # 使用消息格式化器中的优化地图链接生成
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
