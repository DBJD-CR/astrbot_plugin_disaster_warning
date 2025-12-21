"""
消息格式化器模块
提供灾害消息的统一格式化接口
"""

from ...models.models import EarthquakeData, TsunamiData, WeatherAlarmData
from .base import BaseMessageFormatter
from .earthquake import (
    CEAEEWFormatter,
    CWAEEWFormatter,
    JMAEEWFormatter,
    CENCEarthquakeFormatter,
    JMAEarthquakeFormatter,
    USGSEarthquakeFormatter,
    GlobalQuakeFormatter,
)
from .tsunami import TsunamiFormatter, JMATsunamiFormatter
from .weather import WeatherFormatter

# 格式化器映射
MESSAGE_FORMATTERS = {
    # EEW预警格式化器
    "cea_fanstudio": CEAEEWFormatter,
    "cea_wolfx": CEAEEWFormatter,
    "cwa_fanstudio": CWAEEWFormatter,
    "cwa_wolfx": CWAEEWFormatter,
    "jma_fanstudio": JMAEEWFormatter,
    "jma_p2p": JMAEEWFormatter,
    "jma_wolfx": JMAEEWFormatter,
    "global_quake": GlobalQuakeFormatter,
    # 地震情报格式化器
    "cenc_fanstudio": CENCEarthquakeFormatter,
    "cenc_wolfx": CENCEarthquakeFormatter,
    "jma_p2p_info": JMAEarthquakeFormatter,
    "jma_wolfx_info": JMAEarthquakeFormatter,
    "usgs_fanstudio": USGSEarthquakeFormatter,
    # 海啸预警格式化器
    "china_tsunami_fanstudio": TsunamiFormatter,
    "jma_tsunami_p2p": JMATsunamiFormatter,
    # 气象预警格式化器
    "china_weather_fanstudio": WeatherFormatter,
}


def get_formatter(source_id: str):
    """获取指定数据源的格式化器"""
    return MESSAGE_FORMATTERS.get(source_id, BaseMessageFormatter)


def format_earthquake_message(
    source_id: str, earthquake: EarthquakeData, options: dict = None
) -> str:
    """格式化地震消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        try:
            if source_id in ["jma_p2p_info", "jma_wolfx_info"]:
                return formatter_class.format_message(earthquake, options=options)
            return formatter_class.format_message(earthquake)
        except TypeError:
            # 如果不支持 options 参数，回退到旧调用方式
            return formatter_class.format_message(earthquake)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(earthquake)


def format_tsunami_message(source_id: str, tsunami: TsunamiData) -> str:
    """格式化海啸消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        return formatter_class.format_message(tsunami)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(tsunami)


def format_weather_message(source_id: str, weather: WeatherAlarmData) -> str:
    """格式化气象消息"""
    formatter_class = get_formatter(source_id)
    if hasattr(formatter_class, "format_message"):
        return formatter_class.format_message(weather)

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(weather)


__all__ = [
    "BaseMessageFormatter",
    "MESSAGE_FORMATTERS",
    "get_formatter",
    "format_earthquake_message",
    "format_tsunami_message",
    "format_weather_message",
    # 导出各个Formatter以便Typing或其他用途
    "CEAEEWFormatter",
    "CWAEEWFormatter",
    "JMAEEWFormatter",
    "GlobalQuakeFormatter",
    "CENCEarthquakeFormatter",
    "JMAEarthquakeFormatter",
    "USGSEarthquakeFormatter",
    "TsunamiFormatter",
    "JMATsunamiFormatter",
    "WeatherFormatter",
]
