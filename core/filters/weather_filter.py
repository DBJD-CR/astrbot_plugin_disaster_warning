"""
气象预警过滤器
支持按省份白名单和颜色级别过滤气象预警
"""

from typing import Any

from astrbot.api import logger

# 中国所有省级行政区的名称列表（用于匹配）
CHINA_PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]

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

    def __init__(self, config: dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.provinces = config.get("provinces", [])
        self.min_color_level = config.get("min_color_level", "白色")
        self.min_level_value = COLOR_LEVELS.get(self.min_color_level, 0)

        if self.enabled:
            filter_info = []
            if self.provinces:
                filter_info.append(f"省份白名单: {', '.join(self.provinces)}")
            filter_info.append(f"最低级别: {self.min_color_level}")
            logger.info(f"[灾害预警] 气象预警过滤器已启用，{', '.join(filter_info)}")

    def extract_province(self, headline: str) -> str | None:
        """从预警标题中提取省份名称"""
        for province in CHINA_PROVINCES:
            if province in headline:
                return province
        return None

    def extract_color_level(self, headline: str) -> str:
        """从预警标题中提取颜色级别"""
        for color in ["红色", "橙色", "黄色", "蓝色", "白色"]:
            if color in headline:
                return color
        return "白色"

    def should_filter(self, headline: str) -> bool:
        """
        判断是否应过滤该预警
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）
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

        # 2. 省份过滤
        if self.provinces:
            province = self.extract_province(headline)
            if province is None:
                # 无法识别省份，默认不过滤
                logger.debug(f"[灾害预警] 无法从预警标题中识别省份: {headline[:50]}...")
                return False

            if province not in self.provinces:
                logger.info(
                    f"[灾害预警] 气象预警被省份过滤器过滤: {province} 不在白名单中"
                )
                return True

        return False
