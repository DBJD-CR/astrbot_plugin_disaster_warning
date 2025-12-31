"""
气象预警省份过滤器
支持按省份白名单过滤气象预警
"""

from typing import Any

from astrbot.api import logger

# 中国所有省级行政区的名称列表（用于匹配）
CHINA_PROVINCES = [
    "北京", "天津", "上海", "重庆",  # 直辖市
    "河北", "山西", "辽宁", "吉林", "黑龙江",  # 东北华北
    "江苏", "浙江", "安徽", "福建", "江西", "山东",  # 华东
    "河南", "湖北", "湖南",  # 华中
    "广东", "海南",  # 华南
    "四川", "贵州", "云南",  # 西南
    "陕西", "甘肃", "青海",  # 西北
    "台湾",  # 台湾
    "内蒙古", "广西", "西藏", "宁夏", "新疆",  # 自治区
    "香港", "澳门",  # 特别行政区
]


class WeatherProvinceFilter:
    """气象预警省份过滤器"""

    def __init__(self, config: dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.provinces = config.get("provinces", [])
        
        if self.enabled and self.provinces:
            logger.info(f"[灾害预警] 气象预警省份过滤器已启用，白名单: {', '.join(self.provinces)}")
        elif self.enabled:
            logger.info("[灾害预警] 气象预警省份过滤器已启用，但白名单为空，将推送全国预警")

    def extract_province(self, headline: str) -> str | None:
        """从预警标题中提取省份名称"""
        for province in CHINA_PROVINCES:
            if province in headline:
                return province
        return None

    def should_filter(self, headline: str) -> bool:
        """
        判断是否应过滤该预警
        返回 True 表示应过滤（不推送），False 表示不过滤（推送）
        """
        # 未启用过滤或省份列表为空，不过滤任何预警
        if not self.enabled or not self.provinces:
            return False

        # 提取预警中的省份
        province = self.extract_province(headline)

        if province is None:
            # 无法识别省份，默认不过滤
            logger.debug(f"[灾害预警] 无法从预警标题中识别省份: {headline[:50]}...")
            return False

        # 检查省份是否在白名单中
        if province in self.provinces:
            return False  # 在白名单中，不过滤
        else:
            logger.info(f"[灾害预警] 气象预警被省份过滤器过滤: {province} 不在白名单中")
            return True  # 不在白名单中，过滤
