"""
消息格式化器模块
提供灾害消息的统一格式化接口
"""

from typing import Any

from astrbot.api import logger

from ...models.models import EarthquakeData, TsunamiData, WeatherAlarmData
from .base import BaseMessageFormatter
from .earthquake import (
    CEAEEWFormatter,
    CENCEarthquakeFormatter,
    CWAEEWFormatter,
    CWAReportFormatter,
    GlobalQuakeFormatter,
    JMAEarthquakeFormatter,
    JMAEEWFormatter,
    USGSEarthquakeFormatter,
)
from .tsunami import JMATsunamiFormatter, TsunamiFormatter
from .weather import WeatherFormatter

# 格式化器映射
MESSAGE_FORMATTERS = {
    # EEW预警格式化器
    "cea_fanstudio": CEAEEWFormatter,
    "cea_pr_fanstudio": CEAEEWFormatter,
    "cea_wolfx": CEAEEWFormatter,
    "cwa_fanstudio": CWAEEWFormatter,
    "cwa_fanstudio_report": CWAReportFormatter,
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


def _safe_format_message(source_id: str, data: Any, options: dict = None) -> str:
    """安全地格式化消息，包含错误处理和回退逻辑"""
    formatter_class = get_formatter(source_id)

    # 检查映射是否存在，如果不存在则记录警告
    if source_id not in MESSAGE_FORMATTERS:
        logger.warning(
            f"[灾害预警] 未找到数据源 '{source_id}' 的专用格式化器，将回退到基础格式化。"
            f"请检查 core/message_manager.py 中的 ID 映射或 utils/formatters/__init__.py 中的注册。"
        )

    if hasattr(formatter_class, "format_message"):
        try:
            return formatter_class.format_message(data, options=options)
        except TypeError:
            # 如果不支持 options 参数，回退到旧调用方式
            try:
                return formatter_class.format_message(data)
            except Exception as e:
                logger.error(
                    f"[灾害预警] 格式化器 {formatter_class.__name__} (旧接口) 执行出错: {e}，回退到基础格式",
                    exc_info=True,
                )
        except Exception as e:
            logger.error(
                f"[灾害预警] 格式化器 {formatter_class.__name__} 执行出错: {e}，回退到基础格式",
                exc_info=True,
            )

    # 回退到基础格式化
    return BaseMessageFormatter.format_message(data)


def format_earthquake_message(
    source_id: str, earthquake: EarthquakeData, options: dict = None
) -> str:
    """格式化地震消息"""
    return _safe_format_message(source_id, earthquake, options)


def format_tsunami_message(
    source_id: str, tsunami: TsunamiData, options: dict = None
) -> str:
    """格式化海啸消息"""
    return _safe_format_message(source_id, tsunami, options)


def format_weather_message(
    source_id: str, weather: WeatherAlarmData, options: dict = None
) -> str:
    """格式化气象消息"""
    return _safe_format_message(source_id, weather, options)


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
    "CWAReportFormatter",
    "JMAEEWFormatter",
    "GlobalQuakeFormatter",
    "CENCEarthquakeFormatter",
    "JMAEarthquakeFormatter",
    "USGSEarthquakeFormatter",
    "TsunamiFormatter",
    "JMATsunamiFormatter",
    "WeatherFormatter",
]
