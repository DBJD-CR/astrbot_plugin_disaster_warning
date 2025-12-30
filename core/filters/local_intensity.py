"""
本地烈度过滤器
"""

from typing import TypedDict

from astrbot.api import logger

from ...models.models import EarthquakeData
from ..intensity_calculator import IntensityCalculator


class LocalEstimationResult(TypedDict):
    """本地预估结果类型"""
    is_allowed: bool
    distance: float
    intensity: float
    place_name: str


class LocalIntensityFilter:
    """本地烈度过滤器"""

    def __init__(self, config: dict):
        self.enabled = config.get("enabled", False)
        self.latitude = config.get("latitude", 0.0)
        self.longitude = config.get("longitude", 0.0)
        self.threshold = config.get("intensity_threshold", 2.0)
        self.strict_mode = config.get("strict_mode", False)
        self.place_name = config.get("place_name", "本地")

    def check_event(self, earthquake: EarthquakeData) -> tuple[bool, float, float]:
        """
        检查事件是否需要推送
        :return: (is_allowed, distance, intensity)
        """
        if not self.enabled:
            return True, 0.0, 0.0

        if earthquake.latitude is None or earthquake.longitude is None:
            # 如果没有坐标，严格模式下过滤，非严格模式下允许
            return not self.strict_mode, 0.0, 0.0

        distance = IntensityCalculator.calculate_distance(
            earthquake.latitude, earthquake.longitude, self.latitude, self.longitude
        )

        intensity = IntensityCalculator.calculate_estimated_intensity(
            earthquake.magnitude or 0.0,
            distance,
            earthquake.depth or 10.0,
            event_longitude=earthquake.longitude,  # 传入经度以区分东西部
        )

        if self.strict_mode:
            if intensity < self.threshold:
                logger.info(
                    f"[灾害预警] 本地烈度 {intensity:.1f} < 阈值 {self.threshold}，严格模式已过滤"
                )
                return False, distance, intensity

        return True, distance, intensity

    def inject_local_estimation(
        self, earthquake: EarthquakeData
    ) -> LocalEstimationResult | None:
        """
        检查事件并将本地预估信息注入到 earthquake.raw_data 中
        
        :param earthquake: 地震数据对象
        :return: 包含 is_allowed, distance, intensity, place_name 的 TypedDict，
                 如果未启用则返回 None
        """
        if not self.enabled:
            return None
        
        is_allowed, distance, intensity = self.check_event(earthquake)
        
        # 构建本地预估结果
        result: LocalEstimationResult = {
            "is_allowed": is_allowed,
            "distance": distance,
            "intensity": intensity,
            "place_name": self.place_name,
        }
        
        # 将计算结果写入 earthquake.raw_data，供格式化器使用
        # 注意：raw_data 中不包含 is_allowed，只存储用于显示的信息
        earthquake.raw_data["local_estimation"] = {
            "distance": distance,
            "intensity": intensity,
            "place_name": self.place_name,
        }
        
        return result
