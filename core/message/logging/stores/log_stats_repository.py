"""
日志统计持久化仓储。
负责 MessageLogger 的过滤统计加载与保存，
减少主记录器中的存储职责。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger


class LogStatsRepository:
    """日志统计持久化仓储。"""

    def __init__(self, stats_file: Path):
        # 统计仓储只负责一个 JSON 统计文件的读写。
        self.stats_file = stats_file

    def load(self) -> dict[str, Any]:
        """从文件加载日志统计。"""
        # 缺少统计文件时返回空字典，让上层以默认统计值继续运行。
        if not self.stats_file.exists():
            return {}

        try:
            with open(self.stats_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.error(f"[灾害预警] 加载日志统计数据失败: {e}")
        return {}

    def save(self, filter_stats: dict[str, Any]) -> None:
        """保存日志统计到文件。"""
        try:
            # 只持久化必要统计摘要，避免把运行时对象或大型上下文写入磁盘。
            data = {
                "filter_stats": filter_stats,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[灾害预警] 保存日志统计数据失败: {e}")
