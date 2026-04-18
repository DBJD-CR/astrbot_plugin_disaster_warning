"""
灾害服务缓存持久化服务。
负责地震列表缓存与 EEW 查询状态缓存的加载/保存，
减少 DisasterWarningService 中的文件持久化细节。
"""

from __future__ import annotations

import json
import os
from typing import Any

from astrbot.api import logger


class DisasterServiceCacheService:
    """灾害服务缓存持久化服务。"""

    def __init__(self, service):
        self.service = service

    def load_earthquake_lists_cache(self) -> None:
        """从文件加载地震列表缓存。"""
        try:
            if os.path.exists(self.service.cache_file):
                with open(self.service.cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "cenc" in data and "jma" in data:
                        self.service.earthquake_lists.clear()
                        self.service.earthquake_lists.update(data)
                        logger.debug("[灾害预警] 已恢复 Wolfx 地震列表本地缓存")
            else:
                logger.debug("[灾害预警] 本地缓存文件不存在，将使用空的 Wolfx 地震列表")
        except Exception as e:
            logger.warning(f"[灾害预警] 加载 Wolfx 地震列表缓存失败: {e}")

    def save_earthquake_lists_cache(self) -> None:
        """保存地震列表缓存到文件。"""
        temp_file = self.service.cache_file + ".tmp"
        try:
            if not os.path.exists(self.service.storage_dir):
                os.makedirs(self.service.storage_dir, exist_ok=True)

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.service.earthquake_lists, f, ensure_ascii=False)

            # 采用临时文件 + 原子替换，降低服务异常退出时写坏缓存文件的风险。
            if os.path.exists(self.service.cache_file):
                os.replace(temp_file, self.service.cache_file)
            else:
                os.rename(temp_file, self.service.cache_file)

            logger.info("[灾害预警] Wolfx 地震列表缓存已保存")
        except Exception as e:
            logger.error(f"[灾害预警] 保存 Wolfx 地震列表缓存失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def load_eew_query_cache(self) -> None:
        """从文件加载 EEW 查询状态缓存。"""
        try:
            if not os.path.exists(self.service.eew_query_cache_file):
                logger.debug("[灾害预警] EEW 查询缓存文件不存在，将使用空状态")
                return

            with open(self.service.eew_query_cache_file, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning("[灾害预警] EEW 查询缓存格式无效，已忽略")
                return

            restored: dict[str, dict[str, Any]] = {}
            for key, value in data.items():
                # 仅恢复当前仍受支持的机构键，避免历史版本缓存污染现有状态结构。
                if key not in self.service._EEW_QUERY_INSTITUTIONS:
                    continue
                if not isinstance(value, dict):
                    continue
                if not value.get("issued_at"):
                    continue
                restored[key] = value

            self.service.eew_query_state = restored
            if restored:
                logger.debug("[灾害预警] 已恢复 EEW 查询缓存")

        except Exception as e:
            logger.warning(f"[灾害预警] 加载 EEW 查询缓存失败: {e}")

    def save_eew_query_cache(self) -> None:
        """保存 EEW 查询状态缓存到文件。"""
        temp_file = self.service.eew_query_cache_file + ".tmp"
        try:
            if not os.path.exists(self.service.storage_dir):
                os.makedirs(self.service.storage_dir, exist_ok=True)

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.service.eew_query_state, f, ensure_ascii=False)

            # 与地震列表缓存保持一致，统一使用临时文件覆盖策略提升写入安全性。
            if os.path.exists(self.service.eew_query_cache_file):
                os.replace(temp_file, self.service.eew_query_cache_file)
            else:
                os.rename(temp_file, self.service.eew_query_cache_file)

            logger.debug("[灾害预警] EEW 查询缓存已保存")
        except Exception as e:
            logger.error(f"[灾害预警] 保存 EEW 查询缓存失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
