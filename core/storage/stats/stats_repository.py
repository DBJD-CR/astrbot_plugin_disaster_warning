"""
统计持久化仓储。
负责统计数据的序列化与 JSON 文件保存，为后续继续承接加载、迁移与数据库协同打基础。
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from astrbot.api import logger


class StatsRepository:
    """统计持久化仓储。"""

    def __init__(self, data_dir, stats_file):
        self.data_dir = data_dir
        self.stats_file = stats_file

    def save_stats(self, stats: dict[str, Any]):
        """保存统计数据到 JSON 文件。"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            # 持久化前先把 defaultdict 递归转换为普通 dict，避免 JSON 序列化失败。
            serializable_stats = self.prepare_for_serialization(stats)
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump(serializable_stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[灾害预警] 保存统计文件失败: {e}")

    def load_stats_file(self) -> dict[str, Any]:
        """从 JSON 文件加载统计数据，不存在时返回空字典。"""
        try:
            if not self.stats_file.exists():
                return {}
            with open(self.stats_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"[灾害预警] 读取统计文件失败: {e}")
            return {}

    def write_stats_file(self, stats: dict[str, Any]) -> None:
        """兼容旧调用名，写回完整统计文件。"""
        self.save_stats(stats)

    def prepare_for_serialization(self, data: Any) -> Any:
        """递归将 defaultdict 转换为 dict。"""
        # 统计状态里广泛使用 defaultdict 简化计数逻辑，但落盘前必须全部还原为普通 dict。
        if isinstance(data, defaultdict):
            return {k: self.prepare_for_serialization(v) for k, v in data.items()}
        if isinstance(data, dict):
            return {k: self.prepare_for_serialization(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.prepare_for_serialization(i) for i in data]
        return data

    def merge_stats(self, current: dict[str, Any], saved: dict[str, Any]):
        """递归合并统计数据。"""
        # 合并时优先保留 current 的结构骨架，只把 saved 中已有值回填进去，
        # 这样新版本新增的字段也能自然保留默认结构。
        for key, value in saved.items():
            if key in current:
                if isinstance(current[key], defaultdict) and isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        current[key][sub_key] = sub_value
                elif isinstance(current[key], dict) and isinstance(value, dict):
                    self.merge_stats(current[key], value)
                else:
                    current[key] = value
            else:
                current[key] = value
