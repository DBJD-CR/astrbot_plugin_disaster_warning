"""
烈度、震度及USGS过滤器
"""
from astrbot.api import logger
from ...models.models import EarthquakeData

class IntensityFilter:
    """烈度过滤器 - 专门处理使用烈度的数据源"""

    def __init__(self, enabled: bool = True, min_magnitude: float = 0, min_intensity: float = 0):
        self.enabled = enabled
        self.min_magnitude = min_magnitude
        self.min_intensity = min_intensity

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # 检查震级
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        # 检查烈度
        if (
            earthquake.intensity is not None
            and earthquake.intensity < self.min_intensity
        ):
            logger.debug(
                f"[灾害预警] 烈度 {earthquake.intensity} < 最小烈度 {self.min_intensity}"
            )
            return True

        return False


class ScaleFilter:
    """震度过滤器 - 专门处理使用震度的数据源"""

    def __init__(self, enabled: bool = True, min_magnitude: float = 0, min_scale: float = 0):
        self.enabled = enabled
        self.min_magnitude = min_magnitude
        self.min_scale = min_scale

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # 检查震级
        # 特殊处理：如果震级为-1.0（通常表示未知或调查中），则跳过震级过滤，仅依赖震度过滤
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude != -1.0
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        # 检查震度
        if earthquake.scale is not None and earthquake.scale < self.min_scale:
            logger.debug(
                f"[灾害预警] 震度 {earthquake.scale} < 最小震度 {self.min_scale}"
            )
            return True

        return False


class USGSFilter:
    """USGS专用过滤器 - 只检查震级"""

    def __init__(self, enabled: bool = True, min_magnitude: float = 0):
        self.enabled = enabled
        self.min_magnitude = min_magnitude

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # USGS只检查震级
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude < self.min_magnitude
        ):
            logger.debug(
                f"[灾害预警] 震级 {earthquake.magnitude} < 最小震级 {self.min_magnitude}"
            )
            return True

        return False
