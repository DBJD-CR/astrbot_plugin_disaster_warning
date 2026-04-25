"""
Web 管理端运行态路由。
负责注册连接状态、配置摘要与重连等运行期接口，收敛 WebServerRuntimeService 中残留的路由实现。
"""

from __future__ import annotations

from astrbot.api import logger

from ..payloads.api_response import ApiResponse


def register_runtime_admin_routes(
    app,
    *,
    disaster_service,
    connections_payload_builder,
    config_payload_builder,
    expected_sources_getter,
):
    """注册运行态管理路由。"""

    @app.post("/api/reconnect")
    async def force_reconnect():
        """触发所有数据源立即重连。"""
        try:
            guard_result = ApiResponse.guard_service_ready(disaster_service)
            if guard_result is not None:
                return guard_result

            results = await disaster_service.reconnect_all_sources()
            # 同时返回汇总结果与逐连接明细，便于前端展示总览提示和排障详情。
            triggered = sum(1 for s in results.values() if "已触发" in s)
            failed = sum(1 for s in results.values() if "失败" in s)
            return ApiResponse.success(
                {
                    "success": True,
                    "message": f"操作完成: 触发 {triggered} 个重连, {failed} 个失败",
                    "details": results,
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 通过Web端进行手动重连失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/connections")
    async def get_connections():
        """获取连接状态接口响应。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "ws_manager",
            )
            if guard_result is not None:
                return guard_result

            expected_sources = expected_sources_getter()
            return ApiResponse.success(
                connections_payload_builder.build_api_payload(expected_sources)
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取连接状态失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/config")
    async def get_config():
        """获取管理端使用的配置摘要。"""
        try:
            return ApiResponse.success(config_payload_builder.build_summary())
        except Exception as e:
            logger.error(f"[灾害预警] 获取配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
