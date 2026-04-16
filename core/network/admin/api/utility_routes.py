"""
运维/工具类路由。
承接日志摘要、打开日志目录、打开插件目录等与主业务状态弱耦合的接口，
减少 WebAdminServer 中的内联路由体积。
"""

from __future__ import annotations

import asyncio
import os
import platform

from astrbot.api import logger

from ..api_response import ApiResponse
from ..runtime_environment import is_running_in_docker


def register_utility_routes(app, disaster_service, plugin_root: str):
    """注册运维/工具类接口。"""

    @app.get("/api/logs")
    async def get_logs():
        """获取日志摘要。"""
        try:
            if not disaster_service or not disaster_service.message_logger:
                return ApiResponse.success(
                    {"enabled": False, "message": "日志功能未启用"}
                )

            return ApiResponse.success(
                disaster_service.message_logger.get_log_summary()
            )
        except Exception as e:
            logger.error(f"[灾害预警] 获取日志失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/open-log-dir")
    async def open_log_dir():
        """打开日志目录。"""
        try:
            if not disaster_service or not disaster_service.message_logger:
                return ApiResponse.error("日志功能不可用", status_code=503)

            log_path = disaster_service.message_logger.log_file_path
            log_dir = log_path.parent
            if not log_dir.exists():
                return ApiResponse.error("日志目录不存在", status_code=404)

            if is_running_in_docker():
                # 容器内无法可靠控制宿主机文件管理器，因此这里直接给出明确错误提示。
                return ApiResponse.error(
                    "Docker 环境下不支持在宿主机打开目录，请手动查看挂载路径",
                    status_code=400,
                )

            system = platform.system()
            if system == "Windows":
                os.startfile(log_dir)
            elif system == "Darwin":
                await asyncio.create_subprocess_exec("open", str(log_dir))
            else:
                await asyncio.create_subprocess_exec("xdg-open", str(log_dir))

            return ApiResponse.success(
                {"success": True, "message": "已在文件浏览器中打开日志目录"}
            )
        except Exception as e:
            logger.error(f"[灾害预警] 打开日志目录失败: {e}")
            return ApiResponse.error(str(e), status_code=500)

    @app.post("/api/open-plugin-dir")
    async def open_plugin_dir():
        """打开插件根目录。"""
        try:
            if not os.path.exists(plugin_root):
                return ApiResponse.error("插件目录不存在", status_code=404)

            if is_running_in_docker():
                # 与打开日志目录保持同一策略：容器内不尝试拉起宿主机文件管理器。
                return ApiResponse.error(
                    "Docker 环境下不支持在宿主机打开目录，请手动查看挂载路径",
                    status_code=400,
                )

            system = platform.system()
            if system == "Windows":
                os.startfile(plugin_root)
            elif system == "Darwin":
                await asyncio.create_subprocess_exec("open", str(plugin_root))
            else:
                await asyncio.create_subprocess_exec("xdg-open", str(plugin_root))

            return ApiResponse.success(
                {"success": True, "message": "已在文件浏览器中打开插件目录"}
            )
        except Exception as e:
            logger.error(f"[灾害预警] 打开插件目录失败: {e}")
            return ApiResponse.error(str(e), status_code=500)
