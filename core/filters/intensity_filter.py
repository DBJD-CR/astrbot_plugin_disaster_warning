"""
烈度、震度、USGS、Global Quake过滤器
"""

from astrbot.api import logger

from ...models.models import EarthquakeData


class IntensityFilter:
    """烈度过滤器 - 专门处理使用烈度的数据源"""

    def __init__(
        self, enabled: bool = True, min_magnitude: float = 0, min_intensity: float = 0
    ):
        self.enabled = enabled
        self.min_magnitude = min_magnitude
        self.min_intensity = min_intensity

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件 - OR逻辑"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # 检查震级条件
        magnitude_pass = False
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude >= self.min_magnitude
        ):
            magnitude_pass = True

        # 检查烈度条件
        intensity_pass = False
        if (
            earthquake.intensity is not None
            and earthquake.intensity >= self.min_intensity
        ):
            intensity_pass = True

        # OR逻辑：满足任一条件即可
        if magnitude_pass or intensity_pass:
            return False  # 不过滤

        logger.debug(
            f"[灾害预警] 过滤: 震级{earthquake.magnitude} < {self.min_magnitude} 且 烈度{earthquake.intensity} < {self.min_intensity}"
        )
        return True


class ScaleFilter:
    """震度过滤器 - 专门处理使用震度的数据源"""

    def __init__(
        self, enabled: bool = True, min_magnitude: float = 0, min_scale: float = 0
    ):
        self.enabled = enabled
        self.min_magnitude = min_magnitude
        self.min_scale = min_scale

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件 - OR逻辑"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # 检查震级条件
        magnitude_pass = False
        # 特殊处理：如果震级为-1.0（通常表示未知或调查中），视为不满足震级条件（避免误判），依赖震度判断
        # 或者也可以视为通过？通常震级未知时主要看震度
        # 这里逻辑：如果震级有效且 >= 阈值，则通过
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude != -1.0
            and earthquake.magnitude >= self.min_magnitude
        ):
            magnitude_pass = True

        # 检查震度条件
        scale_pass = False
        if earthquake.scale is not None and earthquake.scale >= self.min_scale:
            scale_pass = True

        # OR逻辑：满足任一条件即可
        if magnitude_pass or scale_pass:
            return False  # 不过滤

        logger.debug(
            f"[灾害预警] 过滤: 震级{earthquake.magnitude} < {self.min_magnitude} 且 震度{earthquake.scale} < {self.min_scale}"
        )
        return True


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


class GlobalQuakeFilter:
    """Global Quake专用过滤器 - 使用OR逻辑"""

    def __init__(
        self, enabled: bool = True, min_magnitude: float = 0, min_intensity: float = 0
    ):
        self.enabled = enabled
        self.min_magnitude = min_magnitude
        self.min_intensity = min_intensity

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        # 如果未启用，不过滤任何事件
        if not self.enabled:
            return False

        # 检查震级条件
        magnitude_pass = False
        if (
            earthquake.magnitude is not None
            and earthquake.magnitude >= self.min_magnitude
        ):
            magnitude_pass = True

        # 检查烈度条件
        # 注意：处理烈度为"-"或None的情况，此时认为烈度为0，不满足条件
        intensity_pass = False
        current_intensity = earthquake.intensity
        if current_intensity is not None:
            # 确保烈度是数值类型
            if isinstance(current_intensity, (int, float)):
                if current_intensity >= self.min_intensity:
                    intensity_pass = True

        # OR逻辑：满足任一条件即可
        if magnitude_pass or intensity_pass:
            return False  # 不过滤

        logger.debug(
            f"[灾害预警] Global Quake过滤: 震级{earthquake.magnitude} < {self.min_magnitude} 且 烈度{earthquake.intensity} < {self.min_intensity}"
        )
        return True


class KeywordFilter:
    """关键词过滤器 - 适用于所有地震信息"""

    def __init__(
        self,
        enabled: bool = False,
        blacklist: list[str] = None,
        whitelist: list[str] = None,
    ):
        self.enabled = enabled
        self.blacklist = blacklist or []
        self.whitelist = whitelist or []

    def should_filter(self, earthquake: EarthquakeData) -> bool:
        """判断是否过滤该地震事件"""
        if not self.enabled:
            return False

        location = earthquake.place_name or ""

        # 黑名单过滤
        if self.blacklist:
            for keyword in self.blacklist:
                if keyword and keyword in location:
                    logger.debug(
                        f"[灾害预警] 关键词过滤(黑名单): '{location}' 包含 '{keyword}'"
                    )
                    return True

        # 白名单过滤
        if self.whitelist:
            hit = False
            for keyword in self.whitelist:
                if keyword and keyword in location:
                    hit = True
                    break

            if not hit:
                logger.debug(
                    f"[灾害预警] 关键词过滤(白名单): '{location}' 不包含任一白名单关键词"
                )
                return True

        return False
