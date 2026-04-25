"""
事件统计聚合器。
负责处理 StatisticsManager 中的写模型聚合逻辑，
包括接收计数、唯一事件识别、按源统计、类型统计与时间序列更新。
"""

from __future__ import annotations

from datetime import datetime, timezone

from ...domain.event_models import EarthquakeEvent, EventEnvelope, WeatherEvent


class EventStatsAggregator:
    """事件统计聚合器。"""

    def __init__(self, manager):
        self.manager = manager

    async def aggregate_event(self, event: EventEnvelope) -> dict[str, object]:
        """聚合一次事件写入前的统计状态。"""
        current_time = datetime.now(timezone.utc).isoformat()
        stats = self.manager.stats
        # 每次接收到事件都刷新最后更新时间，便于外部观察统计状态的新鲜度。
        stats["last_updated"] = current_time

        if "total_received" not in stats:
            # 兼容旧版本字段名，首次运行时把旧计数字段平滑迁移过来。
            stats["total_received"] = stats.get("total_pushes", 0)
        stats["total_received"] += 1

        envelope = event
        source_id = envelope.source_id or "unknown"
        source_for_display = source_id

        event_unique_id = self.manager.get_unique_event_id(event)
        # 源内唯一键用于统计同一来源下是否重复收到同一事件。
        source_event_unique_id = f"{source_id}:{event_unique_id}"

        if source_event_unique_id not in self.manager._recorded_source_event_ids:
            # 只有来源内首次出现时，才累加来源维度统计。
            stats["by_source"][source_id] += 1
            self.manager._recorded_source_event_ids.add(source_event_unique_id)
            stats["recent_source_event_ids"].append(source_event_unique_id)
            if len(stats["recent_source_event_ids"]) > 2000:
                stats["recent_source_event_ids"] = stats["recent_source_event_ids"][
                    -2000:
                ]

        is_new_event = event_unique_id not in self.manager._recorded_event_ids
        if is_new_event:
            # 全局首次出现时才更新总事件数、类型统计和详细聚合指标。
            stats["total_events"] += 1
            self.manager._recorded_event_ids.add(event_unique_id)
            stats["recent_event_ids"].append(event_unique_id)
            if len(stats["recent_event_ids"]) > 500:
                stats["recent_event_ids"] = stats["recent_event_ids"][-500:]

            event_type = envelope.event_type or "unknown"
            stats["by_type"][event_type] += 1

            if isinstance(envelope.event, EarthquakeEvent):
                # 地震事件直接进入地震统计分桶与最大震级更新流程。
                self.manager.rule_service.record_earthquake_stats(event)
            elif isinstance(envelope.event, WeatherEvent):
                # 气象事件需要先完成地区解析，成功后才写入详细气象统计。
                weather_stats_recorded = (
                    await self.manager.rule_service.record_weather_stats(envelope.event)
                )
                if not weather_stats_recorded:
                    self.manager.rule_service.log_weather_stats_skip()

            self.manager.rule_service.record_time_series(event)

        return {
            "current_time": current_time,
            "source_id": source_id,
            "source_for_display": source_for_display,
            "event_unique_id": event_unique_id,
            "is_new_event": is_new_event,
        }
