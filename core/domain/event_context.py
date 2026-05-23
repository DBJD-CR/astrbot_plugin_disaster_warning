"""
展示上下文领域模型。
用于承接 parser 输出后的规范化展示投影，
presenter 仅消费该层，不再直接挖掘原始 payload。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .display_models import (
    EarthquakeDisplayModel,
    TsunamiDisplayModel,
    WeatherDisplayModel,
)
from .event_payload import SourcePayload
from .source_models import SourceDescriptor


@dataclass(slots=True)
class EarthquakeDisplayContext:
    """地震展示上下文。"""

    # 事件标识与来源标识用于串联去重、日志与展示链路。
    event_id: str
    source_id: str
    # title 是展示层主标题，不一定等同于原始事件标题。
    title: str
    # 震中时间；若上游无法解析，则允许为空。
    occurred_at: datetime | None = None
    latitude: float | None = None  # 纬度
    longitude: float | None = None  # 经度
    magnitude: float | None = None  # 震级
    depth: float | None = None  # 震源深度 (km)
    # intensity 与 scale 用于承接不同来源的震度或等级信息。
    intensity: float | None = None
    scale: float | None = None
    # 第几报，默认按首报处理。
    report_num: int = 1
    # 以下布尔标记主要服务于预警更新、取消报、演练报等特殊展示分支。
    is_final: bool = False
    is_cancel: bool = False
    is_training: bool = False
    is_assumption: bool = False
    revision: str = ""
    province: str = ""
    domestic_tsunami: str = ""
    max_pga: float | None = None
    # stations 保存测站或分点观测信息，具体结构由上游来源决定。
    stations: dict[str, Any] = field(default_factory=dict)
    image_uri: str = ""
    shakemap_uri: str = ""
    # impact_area 与 local_estimation 常用于影响区域与本地预估展示。
    impact_area: str | None = None
    local_estimation: dict[str, Any] | None = None
    # 以下字段主要承接日本来源中的特有信息。
    jma_issue_type: str = ""
    jma_warn_area: str | None = None
    jma_points: list[dict[str, Any]] = field(default_factory=list)
    jma_comment: str | None = None
    jma_warning_areas: list[str] = field(default_factory=list)
    jma_warning_area_ranges: list[str] = field(default_factory=list)
    # display_model 是已经进一步整理好的展示结果，可供下游直接使用。
    display_model: EarthquakeDisplayModel | None = None
    # metadata 放补充信息，options 放展示阶段的可选控制参数。
    metadata: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    source_descriptor: SourceDescriptor | None = None
    # payload 保留原始载荷引用，便于追踪与排障，但展示层不应过度依赖它。
    payload: SourcePayload | None = None

    @property
    def event_type(self) -> str:
        """返回该上下文对应的事件类型。"""
        return "earthquake"


@dataclass(slots=True)
class TsunamiDisplayContext:
    """海啸展示上下文。"""

    event_id: str
    source_id: str
    title: str
    # level 表示海啸等级或警报级别。
    level: str = ""
    issued_at: datetime | None = None
    updated_at: datetime | None = None
    # message_type 用于区分警报、预报、解除等不同文本类型。
    message_type: str = "warning"
    org_unit: str = ""
    place_name: str = ""
    subtitle: str = ""
    latitude: float | None = None  # 纬度
    longitude: float | None = None  # 经度
    magnitude: float | None = None  # 震级
    depth: float | None = None  # 深度 (km)
    # forecasts 与 monitoring_stations 分别承接预报区域和站点观测信息。
    forecasts: list[dict[str, Any]] = field(default_factory=list)
    monitoring_stations: list[dict[str, Any]] = field(default_factory=list)
    map_urls: dict[str, str] = field(default_factory=dict)
    details_url: str = ""
    batch: str = ""
    code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    display_model: TsunamiDisplayModel | None = None
    source_descriptor: SourceDescriptor | None = None
    payload: SourcePayload | None = None

    @property
    def event_type(self) -> str:
        """返回该上下文对应的事件类型。"""
        return "tsunami"


@dataclass(slots=True)
class WeatherDisplayContext:
    """气象展示上下文。"""

    event_id: str
    source_id: str
    title: str
    headline: str = ""
    description: str = ""
    effective_at: datetime | None = None
    # severity_color 主要供卡片或富文本展示使用。
    severity_color: str = ""
    weather_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    display_model: WeatherDisplayModel | None = None
    source_descriptor: SourceDescriptor | None = None
    payload: SourcePayload | None = None

    @property
    def event_type(self) -> str:
        """返回该上下文对应的事件类型。"""
        return "weather"


# 统一展示上下文联合类型，便于上层以单一入口接收不同灾种的展示数据。
DisplayContext = (
    EarthquakeDisplayContext | TsunamiDisplayContext | WeatherDisplayContext
)


__all__ = [
    "SourcePayload",
    "DisplayContext",
    "EarthquakeDisplayContext",
    "TsunamiDisplayContext",
    "WeatherDisplayContext",
]
