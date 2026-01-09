"""
关键词过滤器
支持按关键词白名单过滤地震信息（支持地名、地区等任意关键词），适用于所有地震数据源
"""

from typing import Any

from astrbot.api import logger

from ...models.models import EarthquakeData


class KeywordFilter:
    """关键词白名单过滤器"""

    def __init__(self, config: dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.keywords = config.get("keywords", [])

        if self.enabled and self.keywords:
            logger.info(
                f"[灾害预警] 关键词过滤器已启用，关键词白名单: {', '.join(self.keywords)}"
            )
        elif self.enabled:
            logger.info(
                "[灾害预警] 关键词过滤器已启用，但关键词列表为空，将推送所有地震"
            )

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """
        判断是否应过滤该地震事件
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）
        """
        # 未启用过滤或关键词列表为空，不过滤任何地震
        if not self.enabled or not self.keywords:
            return False

        # 检查地震地名中是否包含任意一个关键词
        place_name = earthquake.place_name or ""
        if not place_name:
            return False

        place_name_lower = place_name.lower()
        for keyword in self.keywords:
            if keyword.lower() in place_name_lower:
                return False  # 匹配到关键词，不过滤（推送）

        # 未匹配到关键词，过滤（不推送）
        logger.debug(
            f"[灾害预警] 地震被关键词过滤器过滤: 地名中未包含任何关键词（地名: {place_name[:50]}...）"
        )
        return True
