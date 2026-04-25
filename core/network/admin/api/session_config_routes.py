"""
Web 管理端会话配置路由。
负责注册会话配置列表、查询、更新与重置接口，减少 WebAdminServer 的路由定义体积。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from astrbot.api import logger

from ..payloads.api_response import ApiResponse


def register_session_config_routes(app, *, disaster_service):
    """注册会话配置相关路由。"""

    @app.get("/api/session-config/sessions")
    async def list_session_configs():
        """列出当前已知会话及其配置概览。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "session_config_manager",
            )
            if guard_result is not None:
                return guard_result

            mgr = disaster_service.session_config_manager
            sessions = mgr.list_all_known_sessions()

            data = []
            # 列表接口只返回概览字段，详细配置交由单会话查询接口提供。
            for session in sessions:
                override = mgr.get_override(session)
                effective = mgr.get_effective_config(session)
                data.append(
                    {
                        "session": session,
                        "has_override": bool(override),
                        "override_keys": list(override.keys()),
                        "push_enabled": effective.get("push_enabled", True),
                    }
                )

            return ApiResponse.success(
                {
                    "sessions": data,
                    "total": len(data),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取会话配置列表失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.get("/api/session-config/{umo:path}")
    async def get_session_config(umo: str):
        """获取指定会话的覆写配置与生效配置。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "session_config_manager",
            )
            if guard_result is not None:
                return guard_result

            mgr = disaster_service.session_config_manager
            return ApiResponse.success(
                {
                    "session": umo,
                    "override": mgr.get_override(umo),
                    "effective": mgr.get_effective_config(umo),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取会话配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/session-config/{umo:path}")
    async def update_session_config(umo: str, payload: dict[str, Any]):
        """更新指定会话配置，可提交生效配置或覆写配置。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "session_config_manager",
            )
            if guard_result is not None:
                return guard_result

            mgr = disaster_service.session_config_manager
            mode = payload.get("mode", "effective")

            # 同时支持直接提交覆写配置或生效配置，兼容高级编辑与表单式编辑两类场景。
            if mode == "override":
                override = payload.get("override", {})
                if not isinstance(override, dict):
                    return ApiResponse.error("覆写配置必须是对象", status_code=400)
                mgr.set_override(umo, override)
            else:
                effective = payload.get("effective", payload)
                if not isinstance(effective, dict):
                    return ApiResponse.error("生效配置必须是对象", status_code=400)
                mgr.update_session_from_effective(umo, effective)

            return ApiResponse.success(
                {
                    "success": True,
                    "message": "会话配置已保存",
                    "session": umo,
                    "override": mgr.get_override(umo),
                    "effective": mgr.get_effective_config(umo),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 更新会话配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.delete("/api/session-config/{umo:path}")
    async def reset_session_config(umo: str):
        """清空指定会话覆写配置，并回退到默认配置。"""
        try:
            guard_result = ApiResponse.guard_service_ready(
                disaster_service,
                "session_config_manager",
            )
            if guard_result is not None:
                return guard_result

            mgr = disaster_service.session_config_manager
            mgr.delete_override(umo)
            return ApiResponse.success(
                {
                    "success": True,
                    "message": "会话覆写已清空",
                    "session": umo,
                    "override": {},
                    "effective": mgr.get_effective_config(umo),
                }
            )
        except Exception as e:
            logger.error(f"[灾害预警] 清空会话配置失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
