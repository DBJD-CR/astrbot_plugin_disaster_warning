"""通知缓存仓储。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from astrbot.api import logger


class NotificationCacheRepository:
    """负责通知缓存文件的读取、校验与写入。"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.cache_file = self.data_dir / "notifications_cache.json"

    @staticmethod
    def empty_cache() -> dict[str, Any]:
        """返回统一的空缓存结构。"""
        return {
            "last_sync_at": None,
            "items": [],
            "read_map": {},
        }

    def _normalize_cache(self, payload: Any) -> dict[str, Any]:
        """将磁盘内容收敛为稳定缓存结构。"""
        if not isinstance(payload, dict):
            raise ValueError("通知缓存文件格式无效")
        return {
            "last_sync_at": payload.get("last_sync_at"),
            "items": payload.get("items")
            if isinstance(payload.get("items"), list)
            else [],
            "read_map": payload.get("read_map")
            if isinstance(payload.get("read_map"), dict)
            else {},
        }

    async def load(self) -> dict[str, Any]:
        """从磁盘读取通知缓存。"""
        if not self.cache_file.exists():
            return self.empty_cache()

        try:
            content = await asyncio.to_thread(
                self.cache_file.read_text, encoding="utf-8"
            )
            payload = await asyncio.to_thread(json.loads, content)
            return self._normalize_cache(payload)
        except Exception as e:
            logger.warning(f"[灾害预警] 读取通知缓存失败: {e}，将使用空缓存继续。")
            return self.empty_cache()

    async def save(self, cache: dict[str, Any]) -> None:
        """将通知缓存写入磁盘。"""
        try:
            await asyncio.to_thread(self.data_dir.mkdir, parents=True, exist_ok=True)
            content = await asyncio.to_thread(
                json.dumps, cache, indent=4, ensure_ascii=False
            )
            await asyncio.to_thread(
                self.cache_file.write_text, content, encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[灾害预警] 保存通知缓存失败: {e}")
            raise
