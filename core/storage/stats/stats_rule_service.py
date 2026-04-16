"""
统计规则服务。
负责重大事件判定、地震/气象详细统计与时间序列分桶更新，
减少 StatisticsManager 中残留的领域规则实现。
"""

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ....models.models import (
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ....utils.formatters.weather import COLOR_LEVEL_EMOJI, SORTED_WEATHER_TYPES


class StatsRuleService:
    """统计规则服务。"""

    def __init__(self, manager):
        self.manager = manager

    def is_major_event(self, event: DisasterEvent) -> bool:
        """判断是否为重大事件。"""
        # 当前规则偏保守：地震按 M5.0+，海啸默认重大，气象按红/橙色预警认定。
        if isinstance(event.data, EarthquakeData):
            return event.data.magnitude is not None and event.data.magnitude >= 5.0
        if isinstance(event.data, TsunamiData):
            return True
        if isinstance(event.data, WeatherAlarmData):
            level = event.data.alert_level or ""
            title_text = event.data.title or event.data.headline or ""
            if "红" in level or "橙" in level:
                return True
            if "红" in title_text or "橙" in title_text:
                return True
        return False

    def record_earthquake_stats(self, data: EarthquakeData) -> None:
        """记录地震详细统计。"""
        # 地震统计既包含震级分布，也负责维护“最大地震”和国内区域统计等派生指标。
        mag = data.magnitude
        if mag is not None:
            if mag < 3.0:
                key = "< M3.0"
            elif 3.0 <= mag < 4.0:
                key = "M3.0 - M3.9"
            elif 4.0 <= mag < 5.0:
                key = "M4.0 - M4.9"
            elif 5.0 <= mag < 6.0:
                key = "M5.0 - M5.9"
            elif 6.0 <= mag < 7.0:
                key = "M6.0 - M6.9"
            elif 7.0 <= mag < 8.0:
                key = "M7.0 - M7.9"
            else:
                key = ">= M8.0"
            self.manager.stats["earthquake_stats"]["by_magnitude"][key] += 1

            is_reliable = False
            is_cenc_official = False
            if data.disaster_type == DisasterType.EARTHQUAKE and data.info_type:
                info_lower = data.info_type.lower()
                if "正式" in data.info_type:
                    is_reliable = True
                    is_cenc_official = True
                elif "reviewed" in info_lower:
                    is_reliable = True
                elif data.info_type in [
                    "Destination",
                    "ScaleAndDestination",
                    "DetailScale",
                ]:
                    is_reliable = True
                elif "震源" in data.info_type or "各地" in data.info_type:
                    is_reliable = True

            if is_reliable:
                current_max = self.manager.stats["earthquake_stats"].get(
                    "max_magnitude"
                )
                event_time = self.manager.normalize_utc_datetime(
                    data.shock_time,
                    source_id=getattr(data, "source_id", "") or data.source.value,
                )
                if current_max is None or mag > current_max.get("value", 0):
                    self.manager.stats["earthquake_stats"]["max_magnitude"] = {
                        "value": mag,
                        "event_id": data.id,
                        "place_name": data.place_name,
                        "time": event_time.isoformat(),
                        "source": data.source.value,
                    }
                elif mag == current_max.get("value", 0):
                    current_time_str = current_max.get("time")
                    if current_time_str:
                        try:
                            current_time = datetime.fromisoformat(current_time_str)
                            if event_time > current_time:
                                self.manager.stats["earthquake_stats"][
                                    "max_magnitude"
                                ] = {
                                    "value": mag,
                                    "event_id": data.id,
                                    "place_name": data.place_name,
                                    "time": event_time.isoformat(),
                                    "source": data.source.value,
                                }
                        except Exception:
                            pass

            if is_cenc_official:
                region = self.manager.event_support_service.extract_region(
                    data.place_name,
                    strict=True,
                )
                if region:
                    self.manager.stats["earthquake_stats"]["by_region"][region] += 1

    async def record_weather_stats(self, data: WeatherAlarmData) -> bool:
        """记录气象预警详细统计。"""
        # 气象统计依赖地区解析成功，否则只保留总量，不把不可靠地区写入分布统计。
        title_text = data.title or data.headline or ""
        headline_text = data.headline or ""

        direct_region = self.manager._weather_region_resolver.extract_province(
            title_text
        )
        if direct_region:
            region = direct_region
        else:
            region = await self.manager._weather_region_resolver.extract_province_with_fallback(
                title_text, headline_text
            )
            if not region:
                return False

        level = "未知"
        for color, emoji in COLOR_LEVEL_EMOJI.items():
            if color in title_text:
                level = f"{emoji}{color}"
                break
        self.manager.stats["weather_stats"]["by_level"][level] += 1

        w_type = "其他"
        for name in SORTED_WEATHER_TYPES:
            if name in title_text:
                w_type = name
                break
        self.manager.stats["weather_stats"]["by_type"][w_type] += 1
        self.manager.stats["weather_stats"]["by_region"][region] += 1
        return True

    def record_time_series(self, event: DisasterEvent) -> None:
        """记录时间序列统计。"""
        event_time = None
        source_id = getattr(event, "source_id", "") or getattr(
            event.source, "value", ""
        )
        if isinstance(event.data, EarthquakeData):
            event_time = event.data.shock_time
        elif isinstance(event.data, (WeatherAlarmData, TsunamiData)):
            event_time = event.data.issue_time

        event_time = self.manager.normalize_utc_datetime(
            event_time, source_id=source_id
        )
        hour_key = event_time.strftime("%Y-%m-%d %H:00")
        self.manager.stats["hourly_counts"][hour_key] += 1

        day_key = event_time.strftime("%Y-%m-%d")
        self.manager.stats["daily_counts"][day_key] += 1

    def log_weather_stats_skip(self) -> None:
        """记录气象统计被跳过的日志。"""
        logger.warning("[灾害预警] 气象预警地区信息无效或缺失，已跳过该次气象详细统计")
