"""
统计状态工厂。
统一构建 StatisticsManager 使用的默认统计数据结构，
避免初始化与重置逻辑重复维护。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


class StatsStateFactory:
    """统计状态工厂。"""

    @staticmethod
    def build_initial_stats(now: datetime | None = None) -> dict[str, Any]:
        """构建默认统计状态。"""
        current_time = (now or datetime.now(timezone.utc)).isoformat()
        # 这里定义的是 StatisticsManager 的完整内存基线结构，reset 与初始启动都应复用这一份工厂输出。
        return {
            "total_received": 0,
            "total_events": 0,
            "start_time": current_time,
            "last_updated": current_time,
            "by_type": defaultdict(int),
            "by_source": defaultdict(int),
            "earthquake_stats": {
                "by_magnitude": defaultdict(int),
                "by_region": defaultdict(int),
                "max_magnitude": None,
            },
            "weather_stats": {
                "by_level": defaultdict(int),
                "by_type": defaultdict(int),
                "by_region": defaultdict(int),
            },
            "recent_pushes": [],
            "major_events": [],
            "recent_event_ids": [],
            "recent_source_event_ids": [],
            "hourly_counts": defaultdict(int),
            "daily_counts": defaultdict(int),
            "session_stats": {
                "by_session": defaultdict(
                    lambda: {
                        "received": 0,
                        "pushed": 0,
                        "last_push_time": None,
                    }
                ),
                "top_sessions": [],
            },
        }
