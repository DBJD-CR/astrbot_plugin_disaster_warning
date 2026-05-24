"""
海啸展示上下文构建器。
负责把统一投影输入整理为海啸展示上下文，供文本展示与管理端视图复用。
"""

from __future__ import annotations

from ....domain.display_models import TsunamiDisplayModel
from ....domain.event_context import TsunamiDisplayContext
from .common import build_projection_view, coerce_dict, first_non_empty


def _extract_tsunami_projection_details(metadata, source_payload):
    """提取海啸展示所需的投影细节字段。"""
    # 强制将入参属性安全规范化，建立合并字典视图
    projection_view = build_projection_view(
        payload_attributes=coerce_dict(getattr(source_payload, "attributes", None)),
        metadata=metadata,
    )
    return {
        # 预警级别
        "level": str(first_non_empty(projection_view.get("level"), "")).strip(),
        # 预警最初发布时间戳文本
        "issued_at": first_non_empty(projection_view.get("issue_time")),
        # 预警最新更新时间戳文本
        "updated_at": first_non_empty(projection_view.get("update_time")),
        # 警报子消息分类
        "message_type": str(
            first_non_empty(
                projection_view.get("message_type"),
                source_payload.message_type,
                "warning",
            )
        ).strip()
        or "warning",
        # 发布海啸预警的官方科研机构
        "org_unit": str(first_non_empty(projection_view.get("org_unit"), "")).strip(),
        # 预警区域或海洋名称
        "place_name": str(
            first_non_empty(projection_view.get("place_name"), "")
        ).strip(),
        # 附加副标题文本描述
        "subtitle": str(first_non_empty(projection_view.get("subtitle"), "")).strip(),
        # 震中地理纬度
        "latitude": first_non_empty(projection_view.get("latitude")),
        # 震中地理经度
        "longitude": first_non_empty(projection_view.get("longitude")),
        # 关联地震的震级
        "magnitude": first_non_empty(projection_view.get("magnitude")),
        # 关联地震的深度
        "depth": first_non_empty(projection_view.get("depth")),
        # 各沿岸地区海啸波高与预计到达时间预报列表
        "forecasts": list(projection_view.get("forecasts") or []),
        # 已观测录得海啸爬高波幅的实测站数据列表
        "monitoring_stations": list(projection_view.get("monitoring_stations") or []),
        # 包含海啸相关的地图的网络地址字典
        "map_urls": dict(projection_view.get("map_urls") or {}),
        # 官方海啸预警公告详细说明页面的外部超链接
        "details_url": str(
            first_non_empty(projection_view.get("details_url"), "")
        ).strip(),
        # 当前海啸预警的发布批次（如第1批、第2次更新等）
        "batch": str(first_non_empty(projection_view.get("batch"), "")).strip(),
        # 预警内部标识编码
        "code": str(first_non_empty(projection_view.get("code"), "")).strip(),
    }


def build_tsunami_display_context(projection: dict, options: dict | None = None):
    """构建海啸展示上下文主入口。"""
    envelope = projection["envelope"]
    resolved_source_id = projection["resolved_source_id"]
    source_descriptor = projection["source_descriptor"]
    source_payload = projection["source_payload"]
    metadata = projection["metadata"]
    title = projection["title"]
    domain_event = envelope.event

    # 先从投影视图中整理一组中间字段，降低最终上下文构造时的重复取值。
    payload_details = _extract_tsunami_projection_details(metadata, source_payload)
    display_metadata = {
        **metadata,
        "event_id": envelope.id,
        "source_id": resolved_source_id,
        "event_type": "tsunami",
    }
    return TsunamiDisplayContext(
        event_id=envelope.id,
        source_id=resolved_source_id,
        title=title,
        level=getattr(domain_event, "level", None) or payload_details["level"] or "",
        issued_at=(
            getattr(domain_event, "issued_at", None)
            or getattr(domain_event, "occurred_at", None)
            or payload_details["issued_at"]
        ),
        updated_at=payload_details["updated_at"],
        message_type=str(payload_details["message_type"] or "warning").strip()
        or "warning",
        org_unit=str(payload_details["org_unit"] or "").strip(),
        place_name=str(payload_details["place_name"] or "").strip(),
        subtitle=str(payload_details["subtitle"] or "").strip(),
        latitude=payload_details["latitude"],
        longitude=payload_details["longitude"],
        magnitude=payload_details["magnitude"],
        depth=payload_details["depth"],
        forecasts=list(payload_details["forecasts"]),
        monitoring_stations=list(payload_details["monitoring_stations"]),
        map_urls=dict(payload_details["map_urls"]),
        details_url=str(payload_details["details_url"] or "").strip(),
        batch=str(payload_details["batch"] or "").strip(),
        code=str(payload_details["code"] or "").strip(),
        metadata=display_metadata,
        options=dict(options or {}),
        display_model=TsunamiDisplayModel(
            title=title,
            extras=dict(display_metadata),
        ),
        source_descriptor=source_descriptor,
        payload=source_payload,
    )


__all__ = ["build_tsunami_display_context"]
