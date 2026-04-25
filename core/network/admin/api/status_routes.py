"""
Web 管理端状态与统计路由。
负责注册状态查询、统计查询与统计重置接口，减少 WebAdminServer 的路由定义体积。
"""

from __future__ import annotations

from datetime import datetime

from astrbot.api import logger

from ..payloads.api_response import ApiResponse


def register_status_routes(app, *, disaster_service, realtime_payload_builder):
    """注册状态与统计相关路由。"""

    @app.get("/api/status")
    async def get_status():
        """获取服务状态。"""
        try:
            guard_result = ApiResponse.guard_service_ready(disaster_service)
            if guard_result is not None:
                return guard_result
            # 直接复用实时载荷构建器中的状态快照逻辑，避免多个接口字段逐渐漂移。
            return ApiResponse.success(
                realtime_payload_builder.build_status_api_payload()
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取状态失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/statistics")
    async def get_statistics():
        """获取统计数据。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return guard_result
            return ApiResponse.success(
                realtime_payload_builder.build_statistics_api_payload()
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取统计失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/statistics/reset")
    async def reset_statistics():
        """清除统计数据（等价于 /灾害预警统计清除）。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "statistics_manager",
            )
            if guard_result is not None:
                return guard_result

            await disaster_service.statistics_manager.reset_stats()

            return ApiResponse.success(
                {
                    "success": True,
                    "message": "统计数据已清除",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 通过Web端清除统计失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
