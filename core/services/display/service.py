"""
展示投影服务。
统一承接展示上下文与管理端数据视图的投影构建，避免展示层逻辑分散在多个模块之间。
"""

from __future__ import annotations

from typing import Any

from ...domain.display_models import (
    EarthquakeDisplayModel,
    TsunamiDisplayModel,
    WeatherDisplayModel,
)
from ...domain.event_context import (
    EarthquakeDisplayContext,
    TsunamiDisplayContext,
    WeatherDisplayContext,
)
from ...domain.event_models import EventEnvelope
from .builders.common import prepare_display_projection
from .builders.earthquake_context_builder import build_earthquake_display_context
from .builders.tsunami_context_builder import build_tsunami_display_context
from .builders.weather_context_builder import build_weather_display_context


def _normalize_event_summary_fields(record: dict[str, Any]) -> dict[str, Any]:
    """抽取事件摘要视图通用字段。

    供通用事件摘要与地震简表共用，减少重复字段拼装逻辑。
    """
    # 提取公共核心属性并做基本兜底
    return {
        # 提取唯一的事件 ID
        "id": record.get("event_id", ""),
        # 提取事件的类型（例如 earthquake, tsunami, weather）
        "type": record.get("type", "unknown"),
        # 提取事件的显示名称或文字说明
        "source": record.get("source", ""),
        # 提取底层绑定的具体数据源 ID（例如 cenc_earthquake_report）
        "source_id": record.get("source_id", ""),
        # 提取事件发生或发布的时间戳文本
        "time": record.get("time", ""),
        # 提取事件说明或详细描述文本
        "description": record.get("description", ""),
        # 提取地震震级（如果有）
        "magnitude": record.get("magnitude"),
        # 提取地震深度（如果有）
        "depth": record.get("depth"),
        # 提取事件发生的纬度（如果有）
        "latitude": record.get("latitude"),
        # 提取事件发生的经度（如果有）
        "longitude": record.get("longitude"),
        # 提取当前是第几报（仅 EEW 震警类事件）
        "report_num": record.get("report_num"),
        # 提取是否是重大或特别提醒事件
        "is_major": record.get("is_major", False),
    }


def build_display_context(
    event: EventEnvelope,
    source_id: str,
    options: dict | None = None,
):
    """统一展示上下文构建入口。

    先把事件归一化为投影视图，再按事件类型分派到对应的展示上下文构建器。
    """
    # 将标准 EventEnvelope 连同来源 ID 转换为统一的展示投影中间表示
    projection = prepare_display_projection(event, source_id)
    # 解析当前的事件类型，优先读取 event_type 属性
    event_type = projection["envelope"].event_type or getattr(
        projection["envelope"], "event_type", "unknown"
    )

    # 地震类事件（含地震预警）共用地震展示上下文；海啸与气象分别走各自分支。
    if event_type in {"earthquake", "earthquake_warning"}:
        # 调用地震展示上下文构建器进行精细化构建
        return build_earthquake_display_context(projection, options)
    if event_type == "tsunami":
        # 调用海啸展示上下文构建器进行精细化构建
        return build_tsunami_display_context(projection, options)
    # 默认或其他未知类型均作为气象/通用展示事件处理
    return build_weather_display_context(projection, options)


def build_event_summary_view(record: dict[str, Any]) -> dict[str, Any]:
    """构建通用事件摘要视图。"""
    # 直接转发并规范化记录字段
    return _normalize_event_summary_fields(record)


def build_event_summary_views(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """批量构建事件摘要视图。"""
    # 遍历原始记录列表并逐一进行归一化映射
    return [build_event_summary_view(record) for record in records]


def build_earthquake_summary_view(record: dict[str, Any]) -> dict[str, Any] | None:
    """从统计记录构建地震简表视图。

    仅对具备经纬度的地震记录生效，便于管理端地图与列表复用。
    """
    # 仅允许筛选处理真正的地震类记录
    if record.get("type") != "earthquake":
        return None

    latitude = record.get("latitude")
    longitude = record.get("longitude")
    # 地图投影必须具备合法的经纬度信息，缺少任何一项均判定为无效数据直接抛弃
    if latitude is None or longitude is None:
        return None

    # 获取公共规范字段字典，用于构造扁平化的地震面板属性
    common = _normalize_event_summary_fields(record)
    return {
        "id": common["id"],
        "latitude": latitude,
        "longitude": longitude,
        "magnitude": common["magnitude"],
        # 如果描述信息为空，则回退为未知位置
        "place": common["description"] or "未知位置",
        "time": common["time"],
        "source": common["source"],
        "source_id": common["source_id"],
        "report_num": common["report_num"],
        "depth": common["depth"],
    }


def build_recent_earthquake_views(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量构建最近地震事件简表。"""
    views: list[dict[str, Any]] = []
    # 逐条尝试解析，剔除那些非地震类型或缺少地理位置参数的无效记录
    for record in records:
        earthquake_view = build_earthquake_summary_view(record)
        if earthquake_view is not None:
            views.append(earthquake_view)
    return views


def build_earthquake_views_from_stats(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """从统计状态统一提取地震简表。"""
    # 提取最近推送历史数据
    recent_pushes = stats.get("recent_pushes", []) if isinstance(stats, dict) else []
    return build_recent_earthquake_views(recent_pushes)


def build_admin_statistics_projection(
    stats: dict[str, Any],
    *,
    log_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建管理端统计投影，统一供实时面板与接口层使用。"""
    if not isinstance(stats, dict):
        stats = {}

    # 从原始统计中分离出地震、气象专项统计子节点
    earthquake_stats = dict(stats.get("earthquake_stats", {}))
    weather_stats = dict(stats.get("weather_stats", {}))
    # 取最近250条推送记录用于管理端面板渲染，多余的予以截断以减轻前台压力
    recent_push_records = list(stats.get("recent_pushes", [])[:250])
    # 解析用于地图渲染的地震位置标记列表
    earthquake_views = build_recent_earthquake_views(recent_push_records)
    # 解析用于前端通知滚动条的通用事件简表
    event_summary_views = build_event_summary_views(recent_push_records)

    return {
        # 记录自启动以来捕获的事件总数
        "total_events": stats.get("total_events", 0),
        # 各事件类型的分类统计计数
        "by_type": dict(stats.get("by_type", {})),
        # 各数据源渠道的分类统计计数
        "by_source": dict(stats.get("by_source", {})),
        "earthquake_stats": {
            # 按震级区间划分的地震次数计数
            "by_magnitude": dict(earthquake_stats.get("by_magnitude", {})),
            # 按受灾或发生地区分类的地震次数计数
            "by_region": dict(earthquake_stats.get("by_region", {})),
            # 自启动以来的最大震级记录
            "max_magnitude": earthquake_stats.get("max_magnitude"),
        },
        "weather_stats": {
            # 按预警级别颜色划分的气象次数统计
            "by_level": dict(weather_stats.get("by_level", {})),
            # 按预警气象类型（台风、大风、暴雨等）分类计数
            "by_type": dict(weather_stats.get("by_type", {})),
            # 按气象发生省份分类的计数
            "by_region": dict(weather_stats.get("by_region", {})),
        },
        # 原始推送历史缓存
        "recent_pushes": recent_push_records,
        # 归一化后的事件快照列表
        "event_summary_views": event_summary_views,
        # 归一化后的地震经纬度快照列表
        "earthquake_views": earthquake_views,
        # 推送终端会话的触达及连接统计数据
        "session_stats": dict(stats.get("session_stats", {})),
        # 当前系统的日志大小、缓存条目等运行指标
        "log_stats": dict(log_stats or {}),
    }


__all__ = [
    "EarthquakeDisplayContext",
    "TsunamiDisplayContext",
    "WeatherDisplayContext",
    "EarthquakeDisplayModel",
    "TsunamiDisplayModel",
    "WeatherDisplayModel",
    "build_display_context",
    "build_event_summary_view",
    "build_event_summary_views",
    "build_earthquake_summary_view",
    "build_recent_earthquake_views",
    "build_earthquake_views_from_stats",
    "build_admin_statistics_projection",
]
