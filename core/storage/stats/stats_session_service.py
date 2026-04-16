"""
统计会话维度服务。
负责维护会话推送计数、最近推送时间与 Top 会话视图，
减少 StatisticsManager 中会话统计写模型逻辑。
"""

from __future__ import annotations

from collections import defaultdict

from astrbot.api import logger


class StatsSessionService:
    """会话统计服务。"""

    def __init__(self, manager):
        self.manager = manager

    def record_session_stats(
        self, pushed_sessions: list[str], current_time: str
    ) -> None:
        """记录会话维度统计。"""
        try:
            # session_stats 可能来自旧版本 JSON，先做一次结构纠偏再写入。
            session_stats = self.manager.stats.get("session_stats")
            if not isinstance(session_stats, dict):
                session_stats = {
                    "by_session": defaultdict(
                        lambda: {
                            "received": 0,
                            "pushed": 0,
                            "last_push_time": None,
                        }
                    ),
                    "top_sessions": [],
                }
                self.manager.stats["session_stats"] = session_stats

            by_session = session_stats.get("by_session")
            if not isinstance(by_session, defaultdict):
                by_session = defaultdict(
                    lambda: {
                        "received": 0,
                        "pushed": 0,
                        "last_push_time": None,
                    },
                    by_session if isinstance(by_session, dict) else {},
                )
                session_stats["by_session"] = by_session

            for session in pushed_sessions:
                if not session:
                    continue
                info = by_session[session]
                info["received"] = int(info.get("received", 0)) + 1
                info["pushed"] = int(info.get("pushed", 0)) + 1
                info["last_push_time"] = current_time

            # top_sessions 作为展示投影缓存，避免每次查询状态时都重新全量排序。
            sorted_sessions = sorted(
                by_session.items(),
                key=lambda x: x[1].get("pushed", 0),
                reverse=True,
            )
            session_stats["top_sessions"] = [
                {
                    "session": session,
                    "received": info.get("received", 0),
                    "pushed": info.get("pushed", 0),
                    "last_push_time": info.get("last_push_time"),
                }
                for session, info in sorted_sessions[:20]
            ]

        except Exception as e:
            logger.error(f"[灾害预警] 记录会话统计失败: {e}")
