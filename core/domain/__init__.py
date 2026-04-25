"""
领域模型统一导出入口。

该文件不承载业务逻辑，
主要用于把领域层中常用的数据结构集中暴露给上层模块，
避免调用方分散地从多个子模块分别导入。
"""

from .display_models import (
    EarthquakeDisplayModel,
    TsunamiDisplayModel,
    WeatherDisplayModel,
)
from .event_context import (
    DisplayContext,
    EarthquakeDisplayContext,
    TsunamiDisplayContext,
    WeatherDisplayContext,
)
from .event_identity import EventIdentity
from .event_models import EarthquakeEvent, EventEnvelope, TsunamiEvent, WeatherEvent
from .event_payload import SourcePayload
from .source_models import SourceDescriptor

__all__ = [
    "SourceDescriptor",
    "SourcePayload",
    "DisplayContext",
    "EarthquakeDisplayContext",
    "TsunamiDisplayContext",
    "WeatherDisplayContext",
    "EventIdentity",
    "EventEnvelope",
    "EarthquakeEvent",
    "TsunamiEvent",
    "WeatherEvent",
    "EarthquakeDisplayModel",
    "TsunamiDisplayModel",
    "WeatherDisplayModel",
]
