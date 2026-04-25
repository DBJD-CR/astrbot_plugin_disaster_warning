"""
展示器子系统导出。

该文件集中导出消息展示层常用的展示器、注册中心方法与气象展示常量，
方便上层模块统一导入。
"""

from .base_presenter import BasePresenter
from .earthquake_presenter import (
    CencEarthquakePresenter,
    CwaReportPresenter,
    UsgsEarthquakePresenter,
)
from .global_quake_display_context import GlobalQuakeDisplayContextBuilder
from .presenter_registry import (
    get_presenter,
    get_text_presenter_keys,
    present_message,
)
from .text_presenter import TextPresenter
from .tsunami_presenter import TsunamiAlertPresenter
from .weather_constants import (
    COLOR_LEVEL_EMOJI,
    DEFAULT_MAX_DESCRIPTION_LENGTH,
    SORTED_WEATHER_TYPES,
    WEATHER_EMOJI_MAP,
)
from .weather_presenter import WeatherAlertPresenter

__all__ = [
    "BasePresenter",
    "TextPresenter",
    "get_presenter",
    "get_text_presenter_keys",
    "present_message",
    "CencEarthquakePresenter",
    "CwaReportPresenter",
    "UsgsEarthquakePresenter",
    "TsunamiAlertPresenter",
    "WeatherAlertPresenter",
    "GlobalQuakeDisplayContextBuilder",
    "WEATHER_EMOJI_MAP",
    "SORTED_WEATHER_TYPES",
    "COLOR_LEVEL_EMOJI",
    "DEFAULT_MAX_DESCRIPTION_LENGTH",
]
