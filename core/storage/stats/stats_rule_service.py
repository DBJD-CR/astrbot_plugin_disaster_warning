"""
统计规则服务。
负责重大事件判定、地震/气象详细统计与时间序列分桶更新，
减少 StatisticsManager 中残留的领域规则实现。
"""

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)
from ...message.presenters.weather_constants import (
    COLOR_LEVEL_EMOJI,
    SORTED_WEATHER_TYPES,
)
from ...services.identity.event_classifier import is_major_event


class StatsRuleService:
    """统计规则服务。"""

    def __init__(self, manager):
        self.manager = manager

    def is_major_event(self, event: EventEnvelope) -> bool:
        """判断是否为重大事件。"""
        # 统计侧复用身份分类服务的重大事件规则，确保运行时、入库与统计口径一致。
        return is_major_event(event)

    def record_earthquake_stats(self, event: EventEnvelope) -> None:
        """记录地震详细统计。"""
        # 地震统计既包含震级分布，也负责维护“最大地震”和国内区域统计等派生指标。
        envelope = event
        data = envelope.event
        if not isinstance(data, EarthquakeEvent):
            return

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
            info_type = str(
                getattr(data, "jma_issue_type", "")
                or getattr(data, "info_type", "")
                or ""
            )
            if info_type:
                # 只有较可靠的正式报、审定报或完整参数报，才参与最大地震等派生统计。
                info_lower = info_type.lower()
                if "正式" in info_type:
                    is_reliable = True
                    is_cenc_official = True
                elif "reviewed" in info_lower:
                    is_reliable = True
                elif info_type in [
                    "Destination",
                    "ScaleAndDestination",
                    "DetailScale",
                ]:
                    is_reliable = True
                elif "震源" in info_type or "各地" in info_type:
                    is_reliable = True

            if is_reliable:
                # 最大地震摘要只接受可信事件，避免临时报文把峰值统计刷乱。
                current_max = self.manager.stats["earthquake_stats"].get(
                    "max_magnitude"
                )
                source_id = envelope.source_id or ""
                event_time = self.manager.normalize_utc_datetime(
                    getattr(data, "occurred_at", None),
                    source_id=source_id,
                )
                event_id = str(envelope.identity.event_id or envelope.id or "").strip()
                if current_max is None or mag > current_max.get("value", 0):
                    self.manager.stats["earthquake_stats"]["max_magnitude"] = {
                        "value": mag,
                        "event_id": event_id,
                        "place_name": data.place_name,
                        "time": event_time.isoformat(),
                        "source": source_id,
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
                                    "event_id": event_id,
                                    "place_name": data.place_name,
                                    "time": event_time.isoformat(),
                                    "source": source_id,
                                }
                        except Exception:
                            pass

            if is_cenc_official:
                # 国内地区分布只统计中国地震台网正式结果，减少来源口径差异带来的偏差。
                region = self.manager.event_support_service.extract_region(
                    data.place_name,
                    strict=True,
                )
                if region:
                    self.manager.stats["earthquake_stats"]["by_region"][region] += 1

    async def record_weather_stats(self, data) -> bool:
        """记录气象预警详细统计。"""
        # 气象统计依赖地区解析成功，否则只保留总量，不把不可靠地区写入分布统计。
        title_text = getattr(data, "title", "") or getattr(data, "headline", "") or ""
        headline_text = getattr(data, "headline", "") or ""

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
        # 颜色级别通过标题关键词匹配，统一映射成带符号的展示文本。
        for color, emoji in COLOR_LEVEL_EMOJI.items():
            if color in title_text:
                level = f"{emoji}{color}"
                break
        self.manager.stats["weather_stats"]["by_level"][level] += 1

        w_type = "其他"
        # 类型按预设顺序匹配，优先命中更具体、排序更靠前的灾种名称。
        for name in SORTED_WEATHER_TYPES:
            if name in title_text:
                w_type = name
                break
        self.manager.stats["weather_stats"]["by_type"][w_type] += 1
        self.manager.stats["weather_stats"]["by_region"][region] += 1
        return True

    def record_time_series(self, event: EventEnvelope) -> None:
        """记录时间序列统计。"""
        from ...domain.event_models import EarthquakeEvent

        envelope = event
        domain_event = envelope.event
        source_id = envelope.source_id or ""

        event_time = None
        if isinstance(domain_event, EarthquakeEvent):
            event_time = domain_event.occurred_at
        elif isinstance(domain_event, TsunamiEvent):
            event_time = domain_event.issued_at
        elif isinstance(domain_event, WeatherEvent):
            event_time = domain_event.effective_at

        # 各类事件时间字段名称不同，这里统一归一为 UTC 时间后再写入时间序列桶。
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
