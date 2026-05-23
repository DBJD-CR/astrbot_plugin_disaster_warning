"""
领域模型统一导出入口。

该文件不承载业务逻辑，
主要用于把领域层中常用的数据结构集中暴露给上层模块，
避免调用方分散地从多个子模块分别导入。
"""

# 从数据模型导出渲染相关模块
from .display_models import (
    EarthquakeDisplayModel,
    TsunamiDisplayModel,
    WeatherDisplayModel,
)

# 导出事件上下文数据类型，用于在各个展现构建器之间流转上下文
from .event_context import (
    DisplayContext,
    EarthquakeDisplayContext,
    TsunamiDisplayContext,
    WeatherDisplayContext,
)

# 导出用于归类与唯一哈希定位的实体标识符
from .event_identity import EventIdentity

# 导出标准化后的各类型灾害事件以及统一事件信封
from .event_models import EarthquakeEvent, EventEnvelope, TsunamiEvent, WeatherEvent

# 导出上游原始的Payload数据类型包装
from .event_payload import SourcePayload

# 导出数据源属性描述实体
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
