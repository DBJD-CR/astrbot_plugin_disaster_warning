"""
原始日志摘要服务。
负责统计日志条目数量、来源、时间范围、容量占用等信息，
减少 MessageLogger 中的查询/汇总职责。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from astrbot.api import logger


class LogSummaryService:
    """原始日志摘要服务。"""

    def build_summary(
        self,
        *,
        enabled: bool,
        log_file_path: Path,
        max_files: int,
        max_size_mb: int,
        filter_stats: dict[str, int],
    ) -> dict[str, Any]:
        """构建日志摘要信息。"""
        try:
            # 日志摘要面向命令与 Web 管理端展示，因此尽量返回统计概览而非原始日志内容。
            if not log_file_path.exists():
                return {"enabled": enabled, "log_exists": False}

            entry_count = 0
            sources: set[str] = set()
            date_range = {"start": None, "end": None}
            current_size_mb = log_file_path.stat().st_size / (1024 * 1024)
            file_size_mb = current_size_mb
            file_count = 1
            max_capacity_mb = max_size_mb * (max_files + 1)
            usage_percent = (
                (file_size_mb / max_capacity_mb) * 100 if max_capacity_mb > 0 else 0
            )

            def update_date_range(content_to_parse: str):
                # 通过扫描统一日志头部格式来提取时间范围，避免依赖具体消息内容结构。
                try:
                    timestamps = re.findall(
                        r"🕐 日志写入时间: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
                        content_to_parse,
                    )
                    if timestamps:
                        first_ts = timestamps[0]
                        last_ts = timestamps[-1]
                        dt_first = datetime.strptime(first_ts, "%Y-%m-%d %H:%M:%S")
                        dt_last = datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")

                        if date_range["start"] is None or dt_first < datetime.strptime(
                            date_range["start"], "%Y-%m-%d %H:%M:%S"
                        ):
                            date_range["start"] = first_ts

                        if date_range["end"] is None or dt_last > datetime.strptime(
                            date_range["end"], "%Y-%m-%d %H:%M:%S"
                        ):
                            date_range["end"] = last_ts
                except Exception as e:
                    logger.debug(f"[灾害预警] 解析日志时间范围失败: {e}")

            for i in range(1, max_files + 1):
                old_file = log_file_path.with_suffix(f".log.{i}")
                if old_file.exists():
                    file_count += 1
                    file_size_mb += old_file.stat().st_size / (1024 * 1024)
                    try:
                        with open(old_file, encoding="utf-8") as f:
                            old_content = f.read()
                            entry_count += old_content.count("🕐 日志写入时间:")
                            update_date_range(old_content)
                    except Exception as e:
                        logger.debug(f"[灾害预警] 读取旧日志文件 {old_file} 失败: {e}")

            if not log_file_path.exists():
                return {
                    "enabled": enabled,
                    "log_exists": file_count > 1,
                    "log_file": str(log_file_path),
                    "total_entries": entry_count,
                    "data_sources": list(sources),
                    "date_range": date_range,
                    "file_size_mb": file_size_mb,
                    "file_count": file_count,
                    "max_files_limit": max_files,
                    "max_single_file_size_mb": max_size_mb,
                    "max_total_capacity_mb": max_capacity_mb,
                    "usage_percent": usage_percent,
                    "filter_stats": filter_stats.copy(),
                    "format_version": "3.0",
                }

            with open(log_file_path, encoding="utf-8") as f:
                content = f.read()

            entry_count += content.count("🕐 日志写入时间:")
            entries = content.split(f"\n{'=' * 35}\n")
            update_date_range(content)

            for entry in entries:
                entry = entry.strip()
                if not entry or not entry.startswith("🕐 日志写入时间:"):
                    continue
                try:
                    lines = entry.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("📡 来源:"):
                            source = line.replace("📡 来源:", "").strip()
                            sources.add(source)
                except Exception as e:
                    logger.debug(f"[灾害预警] 解析日志条目失败: {e}")
                    continue

            usage_percent = (
                (file_size_mb / max_capacity_mb) * 100 if max_capacity_mb > 0 else 0
            )

            return {
                "enabled": enabled,
                "log_exists": True,
                "log_file": str(log_file_path),
                "total_entries": entry_count,
                "data_sources": list(sources),
                "date_range": date_range,
                "file_size_mb": file_size_mb,
                "file_count": file_count,
                "max_files_limit": max_files,
                "max_single_file_size_mb": max_size_mb,
                "max_total_capacity_mb": max_capacity_mb,
                "usage_percent": usage_percent,
                "filter_stats": filter_stats.copy(),
                "format_version": "3.0",
            }
        except Exception as e:
            logger.error(f"[灾害预警] 获取日志统计失败: {e}")
            return {"enabled": enabled, "log_exists": False, "error": str(e)}
