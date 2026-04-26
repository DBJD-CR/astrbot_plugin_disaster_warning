"""
统计查询服务。
负责从内存统计结构中生成摘要文本、趋势数据与热力图数据，避免查询职责继续堆积在 StatisticsManager 中。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ....utils.time_converter import TimeConverter
from ..source_compat import format_source_name


class StatsQueryService:
    """统计查询服务。"""

    def __init__(self, stats: dict[str, Any], display_timezone: str = "UTC+8"):
        """初始化统计查询服务。"""
        self.stats = stats
        self.display_timezone = display_timezone

    def get_summary(self) -> str:
        """获取统计摘要文本。"""
        s = self.stats

        total = s.get("total_received", s.get("total_pushes", 0))
        # 摘要文本按“总览—分类—地震—气象—来源—会话”顺序拼装，便于直接发送到聊天场景。
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
            # 未在映射表中的类型保持原值，避免新增事件类型时被直接丢失显示。
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
            # 按预设震级顺序输出，避免字典遍历顺序影响阅读体验。
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
            # 最大地震摘要会额外补充来源，便于区分同震级事件来自哪个数据源。
            source_val = max_mag.get("source")
            formatted_source = (
                format_source_name(str(source_val or "")) if source_val else ""
            )
            source_info = f" ({formatted_source})" if formatted_source else ""
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
        # 类型与地区都按数量倒序输出，优先展示最常见的统计项。
        sorted_types = sorted(weather_type.items(), key=lambda x: x[1], reverse=True)
        if sorted_types:
            text.append("类型Top10:")
            for weather_type_name, count in sorted_types[:10]:
                text.append(f"{weather_type_name}: {count}")

        weather_regions = s["weather_stats"].get("by_region", {})
        if weather_regions:
            # 地区榜单与类型榜单分开输出，避免信息混杂在同一段文本中。
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
            text.append(f"{format_source_name(str(source or ''))}: {count}")

        session_stats = s.get("session_stats", {})
        # 会话统计是可选块，缺失时保持静默，避免旧数据结构下报错。
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
        result = []
        now = datetime.now(timezone.utc)
        target_tz = TimeConverter._get_timezone(self.display_timezone)

        for i in range(hours):
            # 逐小时回溯生成连续时间轴，即使某些时段没有事件也会保留空桶。
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
        result = []
        target_tz = TimeConverter._get_timezone(self.display_timezone)
        now = datetime.now(timezone.utc)

        if year:
            # 指定年份时按整年日历范围生成热力图，但仍会截断未来日期。
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
                # 未指定年份时，则按最近若干天生成滚动窗口视图。
                date_point = now - timedelta(days=days - i - 1)
                day_key_utc = date_point.strftime("%Y-%m-%d")
                date_point_local = date_point.astimezone(target_tz)
                display_date = date_point_local.strftime("%Y-%m-%d")
                count = self.stats["daily_counts"].get(day_key_utc, 0)
                result.append({"date": display_date, "count": count})

        return result
