"""
事件展示视图工厂。
统一负责将统计记录或事件数据投影为 Web API / WebSocket / 前端展示所需的 DTO 结构。
"""

from __future__ import annotations

from typing import Any


class EventViewFactory:
    """事件展示 DTO 工厂。"""

    @staticmethod
    def build_earthquake_summary(record: dict[str, Any]) -> dict[str, Any] | None:
        """从统计记录构建地震简表视图。"""
        # 只有地震类记录才适合投影到地图/地球可视化视图中。
        if record.get("type") != "earthquake":
            return None

        latitude = record.get("latitude")
        longitude = record.get("longitude")
        # 缺少坐标的数据无法参与前端空间展示，因此直接过滤。
        if latitude is None or longitude is None:
            return None

        return {
            "id": record.get("event_id", ""),
            "latitude": latitude,
            "longitude": longitude,
            "magnitude": record.get("magnitude"),
            "place": record.get("description", "未知位置"),
            "time": record.get("time", ""),
            "source": record.get("source", ""),
            "source_id": record.get("source_id", ""),
            "report_num": record.get("report_num"),
            "depth": record.get("depth"),
        }

    @staticmethod
    def build_recent_push_view(record: dict[str, Any]) -> dict[str, Any]:
        """构建通用 recent push 视图。"""
        return {
            "id": record.get("event_id", ""),
            "type": record.get("type", "unknown"),
            "source": record.get("source", ""),
            "source_id": record.get("source_id", ""),
            "time": record.get("time", ""),
            "description": record.get("description", ""),
            "magnitude": record.get("magnitude"),
            "depth": record.get("depth"),
            "latitude": record.get("latitude"),
            "longitude": record.get("longitude"),
            "report_num": record.get("report_num"),
            "is_major": record.get("is_major", False),
        }

    @classmethod
    def build_recent_push_views(
        cls, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """批量构建 recent push 视图。"""
        # 保持工厂式批量转换，便于后续集中调整 DTO 结构而无需修改多个调用点。
        return [cls.build_recent_push_view(record) for record in records]

    @classmethod
    def build_recent_earthquake_views(
        cls, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """批量构建最近地震事件简表。"""
        views: list[dict[str, Any]] = []
        for record in records:
            earthquake_view = cls.build_earthquake_summary(record)
            if earthquake_view is not None:
                views.append(earthquake_view)
        return views
