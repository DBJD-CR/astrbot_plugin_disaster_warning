"""
气象预警过滤器
支持按省份白名单、地级市白名单和颜色级别过滤气象预警
"""

import re
from typing import Any

from astrbot.api import logger

from ...models.models import CHINA_PROVINCES, CHINA_CITIES, CITY_TO_PROVINCE

# 颜色级别映射
COLOR_LEVELS = {
    "白色": 0,
    "蓝色": 1,
    "黄色": 2,
    "橙色": 3,
    "红色": 4,
}


class WeatherFilter:
    """气象预警过滤器"""

    def __init__(self, config: dict[str, Any], emit_enable_log: bool = True):
        self.enabled = config.get("enabled", False)
        self.provinces = config.get("provinces", [])
        self.min_color_level = config.get("min_color_level", "白色")
        self.min_level_value = COLOR_LEVELS.get(self.min_color_level, 0)

        # 将白名单中的地级市和省份分开
        self.whitelist_cities = []  # 用户白名单中的地级市
        self.whitelist_provinces = []  # 用户白名单中的省份

        if self.provinces:
            for item in self.provinces:
                if item in CITY_TO_PROVINCE:
                    self.whitelist_cities.append(item)
                elif item in CHINA_PROVINCES:
                    self.whitelist_provinces.append(item)

        if self.enabled and emit_enable_log:
            filter_info = []
            if self.whitelist_cities:
                filter_info.append(f"地级市白名单: {', '.join(self.whitelist_cities)}")
            if self.whitelist_provinces:
                filter_info.append(f"省份白名单: {', '.join(self.whitelist_provinces)}")
            filter_info.append(f"最低级别: {self.min_color_level}")
            logger.info(f"[灾害预警] 气象预警过滤器已启用，{', '.join(filter_info)}")

    def extract_city(self, headline: str) -> str | None:
        """从预警标题中提取地级市名称"""
        for city in CHINA_CITIES:
            if city in headline:
                return city
        return None

    def extract_province(self, headline: str) -> str | None:
        """从预警标题中提取省份名称"""
        # 先尝试提取地级市，再从地级市映射到省份
        city = self.extract_city(headline)
        if city:
            return CITY_TO_PROVINCE.get(city)

        # 如果没有找到地级市，直接匹配省份
        for province in CHINA_PROVINCES:
            if province in headline:
                return province
        return None

    def extract_color_level(self, headline: str) -> str:
        """从预警标题中提取颜色级别"""
        # 预处理：去除无效上下文中的颜色引用
        # 1. 去除括号内的内容 (通常是 "原...已失效" 等)
        # 兼容全角和半角括号
        cleaned = re.sub(r"[（\(].*?[）\)]", "", headline)

        # 2. 去除 "解除...预警" (通常是 "解除...预警，发布..." 或单纯解除)
        # 这里的非贪婪匹配 .*? 会匹配到最近的 "预警"
        cleaned = re.sub(r"解除[^，。,]*?预警", "", cleaned)

        # 3. 去除 "将...预警" (通常是 "将...预警降级为...")
        cleaned = re.sub(r"将[^，。,]*?预警", "", cleaned)

        # 4. 去除 "原...预警" (如果没有被括号包裹)
        cleaned = re.sub(r"原[^，。,]*?预警", "", cleaned)

        if cleaned != headline:
            logger.debug(f"[灾害预警] 标题清洗: '{headline}' -> '{cleaned}'")

        # 匹配颜色 - 优先匹配剩下的文本
        for color in ["红色", "橙色", "黄色", "蓝色", "白色"]:
            if color in cleaned:
                return color

        # 如果清洗后没有颜色了（比如只有“解除暴雨红色预警”），
        # 则说明这可能是一条解除通知，或者不包含有效的新增预警级别。
        # 这种情况下返回“白色”作为最低级别，通常会被过滤器拦截（除非用户设置阈值为白色）。
        return "白色"

    def should_filter(self, headline: str) -> bool:
        """
        判断是否应过滤该预警
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）

        匹配逻辑：
        1. 如果白名单中有地级市，必须精确匹配到白名单中的地级市
        2. 如果白名单中只有省份，则匹配省份
        3. 如果无法识别地级市或省份，拦截（不放行）
        """
        if not self.enabled:
            return False

        # 1. 级别过滤
        current_color = self.extract_color_level(headline)
        current_level_value = COLOR_LEVELS.get(current_color, 0)

        if current_level_value < self.min_level_value:
            logger.info(
                f"[灾害预警] 气象预警被级别过滤器过滤: {current_color} 低于最低要求 {self.min_color_level}"
            )
            return True

        # 2. 省份/地级市过滤
        if self.provinces:
            # 优先从标题中提取地级市
            city = self.extract_city(headline)

            # 如果白名单中有地级市，必须精确匹配
            if self.whitelist_cities:
                if city is None:
                    # 标题中无地级市（只有县级或无法识别），拦截
                    logger.info(
                        f"[灾害预警] 气象预警被过滤: 标题中无白名单内地级市，无法识别具体市级别区域"
                    )
                    return True

                if city not in self.whitelist_cities:
                    # 地级市不在白名单中，拦截
                    logger.info(
                        f"[灾害预警] 气象预警被过滤: {city} 不在白名单中"
                    )
                    return True

                # 精确匹配到白名单中的地级市，放行
                logger.debug(f"[灾害预警] 气象预警精确匹配到地级市: {city}")
                return False

            # 如果白名单中只有省份（没有地级市），则匹配省份
            if self.whitelist_provinces:
                province = self.extract_province(headline)
                if province is None:
                    # 无法识别省份，拦截
                    logger.info(
                        f"[灾害预警] 气象预警被过滤: 无法识别省份/地级市"
                    )
                    return True

                if province not in self.whitelist_provinces:
                    logger.info(
                        f"[灾害预警] 气象预警被省份过滤器过滤: {province} 不在白名单中"
                    )
                    return True

                logger.debug(f"[灾害预警] 气象预警匹配到省份: {province}")

        return False
