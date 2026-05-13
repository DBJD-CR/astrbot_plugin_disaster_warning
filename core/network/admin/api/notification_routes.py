"""Web 管理端通知路由。"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger

from ..payloads.api_response import ApiResponse


def _get_notification_center(disaster_service):
    """获取通知中心实例。"""
    return getattr(disaster_service, "notification_center", None)


def register_notification_routes(app, *, disaster_service):
    """注册通知中心相关接口。"""

    @app.get("/api/notifications")
    async def get_notifications():
        """获取通知列表与元信息。"""
        notification_center = _get_notification_center(disaster_service)
        if not notification_center:
            return ApiResponse.error("通知系统不可用", status_code=503)
        try:
            return ApiResponse.success(await notification_center.get_payload())
        except Exception as e:
            logger.error(f"[灾害预警] 获取通知列表失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/notifications/read")
    async def mark_notification_read(payload: dict[str, Any]):
        """标记单条通知为已读。"""
        notification_center = _get_notification_center(disaster_service)
        if not notification_center:
            return ApiResponse.error("通知系统不可用", status_code=503)

        notification_id = payload.get("id")
        if notification_id is None:
            return ApiResponse.error("缺少必填字段 id", status_code=400)
        try:
            normalized_id = int(notification_id)
        except (TypeError, ValueError):
            return ApiResponse.error("id 必须是数字", status_code=400)

        result = await notification_center.mark_as_read(normalized_id)
        web_admin_server = getattr(disaster_service, "web_admin_server", None)
        runtime_service = getattr(web_admin_server, "_runtime_service", None)
        if runtime_service:
            await runtime_service.broadcast_data()
        return ApiResponse.success(result)

    @app.post("/api/notifications/read-all")
    async def mark_all_notifications_read():
        """标记全部通知为已读。"""
        notification_center = _get_notification_center(disaster_service)
        if not notification_center:
            return ApiResponse.error("通知系统不可用", status_code=503)

        result = await notification_center.mark_all_as_read()
        web_admin_server = getattr(disaster_service, "web_admin_server", None)
        runtime_service = getattr(web_admin_server, "_runtime_service", None)
        if runtime_service:
            await runtime_service.broadcast_data()
        return ApiResponse.success(result)

    @app.post("/api/notifications/refresh")
    async def refresh_notifications():
        """立即同步远端通知并返回最新快照。"""
        notification_center = _get_notification_center(disaster_service)
        if not notification_center:
            return ApiResponse.error("通知系统不可用", status_code=503)

        changed = await notification_center.refresh()
        web_admin_server = getattr(disaster_service, "web_admin_server", None)
        runtime_service = getattr(web_admin_server, "_runtime_service", None)
        if runtime_service:
            await runtime_service.broadcast_data()
        payload = await notification_center.get_payload()
        return ApiResponse.success(
            {
                "ok": True,
                "changed": changed,
                "items": payload.get("items", []),
                "meta": payload.get("meta", {}),
            }
        )
