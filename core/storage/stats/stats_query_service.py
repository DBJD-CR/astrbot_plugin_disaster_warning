"""
统计查询服务。
负责从内存统计结构中生成摘要文本、趋势数据与热力图数据，避免查询职责继续堆积在 StatisticsManager 中。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ....utils.time_converter import TimeConverter
from ...support.event_view_factory import EventViewFactory


class StatsQueryService:
    """统计查询服务。"""

    def __init__(self, stats: dict[str, Any], display_timezone: str = "UTC+8"):
        self.stats = stats
        self.display_timezone = display_timezone

    def get_summary(self) -> str:
        """获取统计摘要文本。"""
        # 该摘要面向命令输出，因此组织为人类可直接阅读的分段文本而非结构化 JSON。
        s = self.stats

        total = s.get("total_received", s.get("total_pushes", 0))
        text = [
            "📊 灾害预警统计报告",
            f"📅 统计开始时间: {s['start_time'][:19].replace('T', ' ')}",
            f"🔢 记录到的事件总数: {total}",
            f"🚨 去重后的事件总数: {s['total_events']}",
            "",
            "📈 分类统计:",
        ]

        type_map = {
            "earthquake": "地震",
            "earthquake_warning": "地震预警",
            "tsunami": "海啸",
            "weather_alarm": "气象",
        }
        for type_key, count in s["by_type"].items():
            type_name = type_map.get(type_key, type_key)
            text.append(f"{type_name}: {count}")

        text.extend(["", "🌍 地震震级分布:"])
        eq_stats = s["earthquake_stats"]["by_magnitude"]
        order = [
            "< M3.0",
            "M3.0 - M3.9",
            "M4.0 - M4.9",
            "M5.0 - M5.9",
            "M6.0 - M6.9",
            "M7.0 - M7.9",
            ">= M8.0",
        ]
        has_eq = False
        for key in order:
            count = eq_stats.get(key, 0)
            if count > 0:
                text.append(f"{key}: {count}")
                has_eq = True
        if not has_eq:
            text.append("(暂无数据)")

        eq_regions = s["earthquake_stats"].get("by_region", {})
        if eq_regions:
            sorted_eq_regions = sorted(
                eq_regions.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_eq_regions:
                text.append("")
                text.append("📍 地震高发地区 (国内Top 10):")
                for region, count in sorted_eq_regions[:10]:
                    text.append(f"{region}: {count}")

        max_mag = s["earthquake_stats"].get("max_magnitude")
        if max_mag:
            source_val = max_mag.get("source")
            source_info = f" ({source_val})" if source_val else ""
            text.extend(
                [
                    "",
                    f"🔥 最大地震: M{max_mag['value']} {max_mag['place_name']}{source_info}",
                    "",
                ]
            )

        text.append("☁️ 气象预警分布:")
        text.append("")
        weather_level = s["weather_stats"]["by_level"]
        level_order = ["🔴红色", "🟠橙色", "🟡黄色", "🔵蓝色", "⚪白色", "未知"]
        has_weather = False

        weather_type = s["weather_stats"]["by_type"]
        sorted_types = sorted(weather_type.items(), key=lambda x: x[1], reverse=True)
        if sorted_types:
            text.append("类型Top10:")
            for weather_type_name, count in sorted_types[:10]:
                text.append(f"{weather_type_name}: {count}")

        weather_regions = s["weather_stats"].get("by_region", {})
        if weather_regions:
            sorted_w_regions = sorted(
                weather_regions.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_w_regions:
                text.append("\n地区Top10:")
                for region, count in sorted_w_regions[:10]:
                    text.append(f"{region}: {count}")

        text.append("\n级别分布:")
        for level in level_order:
            count = weather_level.get(level, 0)
            if count > 0:
                text.append(f"{level}: {count}")
                has_weather = True

        if not has_weather and not sorted_types:
            text.append("(暂无数据)")

        text.extend(["", "📡 数据源事件统计:"])
        sorted_sources = sorted(
            s["by_source"].items(), key=lambda x: x[1], reverse=True
        )
        for source, count in sorted_sources[:10]:
            text.append(f"{source}: {count}")

        session_stats = s.get("session_stats", {})
        top_sessions = (
            session_stats.get("top_sessions", [])
            if isinstance(session_stats, dict)
            else []
        )
        if top_sessions:
            text.extend(["", "👥 会话推送统计 Top10:"])
            for item in top_sessions[:10]:
                text.append(
                    f"{item.get('session')}: pushed={item.get('pushed', 0)}, received={item.get('received', 0)}"
                )

        return "\n".join(text)

    def get_trend_data(self, hours: int = 24) -> list[dict[str, Any]]:
        """获取趋势数据（最近 N 小时）。"""
        # 统计桶按 UTC 存储，但展示时转换到配置时区，避免前端自行处理时区换算。
        result = []
        now = datetime.now(timezone.utc)
        target_tz = TimeConverter._get_timezone(self.display_timezone)

        for i in range(hours):
            time_point = now - timedelta(hours=hours - i - 1)
            hour_key_utc = time_point.strftime("%Y-%m-%d %H:00")
            time_point_local = time_point.astimezone(target_tz)
            display_time = time_point_local.strftime("%m-%d %H:00")
            count = self.stats["hourly_counts"].get(hour_key_utc, 0)
            result.append({"time": display_time, "count": count})

        return result

    def get_heatmap_data(
        self, days: int = 180, year: int | None = None
    ) -> list[dict[str, Any]]:
        """获取日历热力图数据。"""
        # 支持“最近 N 天”与“指定年份”两种模式，方便前端切换短期/年度视图。
        result = []
        target_tz = TimeConverter._get_timezone(self.display_timezone)
        now = datetime.now(timezone.utc)

        if year:
            start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)

            if start_date > now:
                return []

            if end_date > now:
                end_date = now

            delta = (end_date - start_date).days + 1

            for i in range(delta):
                date_point = start_date + timedelta(days=i)
                day_key_utc = date_point.strftime("%Y-%m-%d")
                display_date = day_key_utc
                count = self.stats["daily_counts"].get(day_key_utc, 0)
                result.append({"date": display_date, "count": count})
        else:
            for i in range(days):
                date_point = now - timedelta(days=days - i - 1)
                day_key_utc = date_point.strftime("%Y-%m-%d")
                date_point_local = date_point.astimezone(target_tz)
                display_date = date_point_local.strftime("%Y-%m-%d")
                count = self.stats["daily_counts"].get(day_key_utc, 0)
                result.append({"date": display_date, "count": count})

        return result

    def get_realtime_statistics_payload(self) -> dict[str, Any]:
        """获取供 WebSocket / 实时面板使用的统计投影。"""
        earthquake_stats = self.stats.get("earthquake_stats", {})
        weather_stats = self.stats.get("weather_stats", {})
        # recent_pushes 保留原始记录，同时额外提供 recent_push_views 供前端直接消费。
        recent_pushes = self.stats.get("recent_pushes", [])[:250]
        recent_push_views = EventViewFactory.build_recent_push_views(recent_pushes)
        return {
            "total_events": self.stats.get("total_events", 0),
            "by_type": dict(self.stats.get("by_type", {})),
            "by_source": dict(self.stats.get("by_source", {})),
            "earthquake_stats": {
                "by_magnitude": dict(earthquake_stats.get("by_magnitude", {})),
                "by_region": dict(earthquake_stats.get("by_region", {})),
                "max_magnitude": earthquake_stats.get("max_magnitude"),
            },
            "weather_stats": {
                "by_level": dict(weather_stats.get("by_level", {})),
                "by_type": dict(weather_stats.get("by_type", {})),
                "by_region": dict(weather_stats.get("by_region", {})),
            },
            "recent_pushes": recent_pushes,
            "recent_push_views": recent_push_views,
            "session_stats": self.stats.get("session_stats", {}),
        }
