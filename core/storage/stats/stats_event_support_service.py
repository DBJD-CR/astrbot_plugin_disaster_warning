"""
统计事件辅助服务。
负责事件描述、地区提取和地震展示级别解析，
减少 StatisticsManager 中残留的领域辅助逻辑。
"""

from __future__ import annotations

from ....utils.converters import ScaleConverter
from ...domain.event_models import (
    EarthquakeEvent,
    EventEnvelope,
    TsunamiEvent,
    WeatherEvent,
)

CHINA_PROVINCES = [
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
]


class StatsEventSupportService:
    """统计事件辅助服务。"""

    def __init__(self, manager):
        self.manager = manager

    def extract_region(self, text: str, strict: bool = False) -> str | None:
        """从文本中提取地区（省份）信息。"""
        if not text:
            return None if strict else "未知"

        for province in CHINA_PROVINCES:
            if text.startswith(province):
                return province

        if strict:
            return None

        return text[:2]

    def get_earthquake_level(self, data) -> float | None:
        """提取可展示的地震震度值（优先 scale / max_scale / intensity）。"""
        candidates = [getattr(data, "scale", None), getattr(data, "intensity", None)]
        max_scale = getattr(data, "max_scale", None)
        if max_scale is not None:
            candidates.insert(1, max_scale)

        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, (int, float)):
                return float(candidate)
            parsed = ScaleConverter.parse_jma_cwa_scale(candidate)
            if parsed is not None:
                return parsed
        return None

    def get_event_description_from_envelope(self, envelope: EventEnvelope) -> str:
        """基于新领域包络生成简短事件描述。"""
        domain_event = envelope.event
        if isinstance(domain_event, EarthquakeEvent):
            place_name = domain_event.place_name or "未知地点"
            if domain_event.magnitude is None:
                return (
                    "震源参数调查中"
                    if place_name in ["未知地点", "未知位置"]
                    else place_name
                )
            return f"M{domain_event.magnitude:.1f} {place_name}"

        if isinstance(domain_event, TsunamiEvent):
            return f"{domain_event.title} ({domain_event.level})"

        if isinstance(domain_event, WeatherEvent):
            return f"{domain_event.title or domain_event.headline}"

        return "未知事件"

    def get_event_description(self, event: EventEnvelope) -> str:
        """生成简短的事件描述。"""
        return self.get_event_description_from_envelope(event)
