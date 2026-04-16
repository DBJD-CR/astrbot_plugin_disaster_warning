"""
Web 管理端 API 响应封装。
统一处理成功响应、错误响应以及常见的服务可用性检查。
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


class ApiResponse:
    """统一 API 响应辅助器。"""

    @staticmethod
    def success(data: dict[str, Any] | None = None, status_code: int = 200):
        """返回成功响应。"""
        payload = data or {}
        # FastAPI 对 200 + dict 会自动序列化；仅在需要自定义状态码时显式包裹 JSONResponse。
        if status_code == 200:
            return payload
        return JSONResponse(payload, status_code=status_code)

    @staticmethod
    def error(message: str, status_code: int = 500, **extra: Any):
        """返回错误响应。"""
        payload: dict[str, Any] = {"error": message}
        payload.update(extra)
        return JSONResponse(payload, status_code=status_code)

    @staticmethod
    def guard_service_ready(service, manager_name: str | None = None):
        """检查服务或其子管理器是否已就绪。"""
        # 路由层统一通过这个守卫函数返回 503，避免各接口重复拼装相同的未就绪响应。
        if service is None:
            return ApiResponse.error("服务未初始化", status_code=503)

        if manager_name and getattr(service, manager_name, None) is None:
            manager_display = {
                "statistics_manager": "统计管理器",
                "ws_manager": "WebSocket 管理器",
                "session_config_manager": "会话配置管理器",
                "message_logger": "日志功能",
            }.get(manager_name, manager_name)
            return ApiResponse.error(f"{manager_display}未初始化", status_code=503)

        return None
