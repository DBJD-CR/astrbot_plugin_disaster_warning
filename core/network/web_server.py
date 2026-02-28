"""
灾害预警插件 Web 管理服务器
提供基于 Web 管理界面的 REST API 和 WebSocket 端点
"""

import asyncio
import json
import os
import platform
import secrets
import traceback
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ...utils.geolocation import close_geoip_session, fetch_location_from_ip
from ...utils.version import get_plugin_version
from ..support.config_validator import ConfigValidator
from ..support.simulation_service import (
    build_earthquake_simulation,
    get_simulation_params,
    resolve_target_session,
)

try:
    import uvicorn
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning(
        "[灾害预警] FastAPI 未安装，Web 管理端功能不可用。请运行: pip install fastapi uvicorn"
    )


def is_running_in_docker() -> bool:
    """
    检测是否在 Docker 容器中运行
    使用多种方法进行检测以提高准确性
    """
    # 方法1: 检查 /.dockerenv 文件（最可靠的容器内标志）
    if os.path.exists("/.dockerenv"):
        return True

    # 方法2: 检查当前进程的 cgroup 是否在 docker 或 kubepods 中
    try:
        with open("/proc/self/cgroup") as f:
            content = f.read()
            if "/docker/" in content or "/kubepods/" in content:
                return True
    except (FileNotFoundError, PermissionError):
        pass

    # 方法3: 检查容器特定的环境变量
    if os.environ.get("DOCKER_CONTAINER") == "true":
        return True

    return False


class WebAdminServer:
    """Web 管理端服务器"""

    # 数据源内部名称 -> 配置键的映射（两处用到：/api/connections 和 _get_realtime_data）
    _SOURCE_CONFIG_KEY: dict[str, str] = {
        "fan_studio_all": "fan_studio",
        "p2p_main": "p2p_earthquake",
        "wolfx_all": "wolfx",
        "global_quake": "global_quake",
    }

    def __init__(self, disaster_service, config: dict[str, Any]):
        self.disaster_service = disaster_service
        self.config = config
        self.app = None
        self.server = None
        self._server_task = None
        self._broadcast_task = None
        self._ping_task = None  # 新增：定期ping任务
        self._ws_connections: list[WebSocket] = []  # Active WebSocket connections
        self._latency_cache: dict[str, float | None] = {}  # 新增：延迟缓存
        self._auth_enabled = False
        self._auth_token: str | None = None

        if not FASTAPI_AVAILABLE:
            return

        self._setup_app()

    def _setup_app(self):
        """配置 FastAPI 应用"""

        self.app = FastAPI(
            title="灾害预警管理端",
            description="灾害预警插件 Web 管理界面",
            version="1.0.0",
        )

        # 鉴权配置
        password = self.config.get("web_admin", {}).get("password", "")
        if password:
            self._auth_enabled = True
            self._auth_token = secrets.token_hex(32)

        # 鉴权中间件
        @self.app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if not self._auth_enabled:
                return await call_next(request)
            path = request.url.path
            # 不需要鉴权的路径
            if path in {"/api/login", "/api/auth-info"}:
                return await call_next(request)
            # 只保护 /api/*（/ws 由 WebSocket 端点自行校验）
            if not path.startswith("/api"):
                return await call_next(request)
            # WebSocket 和 API 均支持 token 查询参数或 Authorization 头
            token = request.query_params.get("token", "")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
            if not self._auth_token or not secrets.compare_digest(token, self._auth_token):
                return JSONResponse({"error": "未授权，请先登录"}, status_code=401)
            return await call_next(request)

        # CORS 配置
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册路由
        self._register_routes()

        # 静态文件服务
        admin_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "admin"
        )
        if os.path.exists(admin_dir):
            self.app.mount(
                "/", StaticFiles(directory=admin_dir, html=True), name="admin"
            )

    def _register_routes(self):
        """注册 API 路由"""

        @self.app.get("/api/auth-info")
        async def get_auth_info():
            """返回是否需要密码认证"""
            return {"auth_required": self._auth_enabled}

        @self.app.post("/api/login")
        async def login(credentials: dict[str, Any]):
            """密码登录，返回访问令牌"""
            if not self._auth_enabled:
                return {"token": "no-auth", "auth_required": False}
            password = self.config.get("web_admin", {}).get("password", "")
            if secrets.compare_digest(credentials.get("password", ""), password):
                return {"token": self._auth_token, "auth_required": True}
            return JSONResponse({"error": "密码错误"}, status_code=401)

        @self.app.get("/logo.png")
        async def get_logo():
            """获取插件 Logo"""
            logo_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logo.png"
            )
            if os.path.exists(logo_path):
                return FileResponse(logo_path)
            return JSONResponse(
                {"error": "未找到插件 Logo 的图片文件"}, status_code=404
            )

        """注册 API 路由"""

        @self.app.get("/api/status")
        async def get_status():
            """获取服务状态"""
            try:
                if not self.disaster_service:
                    return JSONResponse({"error": "服务未初始化"}, status_code=503)

                status = self.disaster_service.get_service_status()
                return {
                    "running": status.get("running", False),
                    "uptime": status.get("uptime", "未知"),
                    "active_connections": status.get("active_websocket_connections", 0),
                    "total_connections": status.get("total_connections", 0),
                    "connection_details": status.get("connection_details", {}),
                    "data_sources": status.get("data_sources", []),
                    "sub_source_status": status.get(
                        "sub_source_status", {}
                    ),  # 新增：子数据源状态
                    "message_logger_enabled": status.get(
                        "message_logger_enabled", False
                    ),
                    "timestamp": datetime.now().isoformat(),
                    "start_time": status.get("start_time"),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取状态失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/statistics")
        async def get_statistics():
            """获取统计数据"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return JSONResponse(
                        {"error": "统计管理器未初始化"}, status_code=503
                    )

                stats = self.disaster_service.statistics_manager.stats
                return {
                    "total_received": stats.get("total_received", 0),
                    "total_events": stats.get("total_events", 0),
                    "start_time": stats.get("start_time", ""),
                    "last_updated": stats.get("last_updated", ""),
                    "by_type": dict(stats.get("by_type", {})),
                    "by_source": dict(stats.get("by_source", {})),
                    "earthquake_stats": {
                        "by_magnitude": dict(
                            stats.get("earthquake_stats", {}).get("by_magnitude", {})
                        ),
                        "by_region": dict(
                            stats.get("earthquake_stats", {}).get("by_region", {})
                        ),
                        "max_magnitude": stats.get("earthquake_stats", {}).get(
                            "max_magnitude"
                        ),
                    },
                    "weather_stats": {
                        "by_level": dict(
                            stats.get("weather_stats", {}).get("by_level", {})
                        ),
                        "by_type": dict(
                            stats.get("weather_stats", {}).get("by_type", {})
                        ),
                        "by_region": dict(
                            stats.get("weather_stats", {}).get("by_region", {})
                        ),
                    },
                    "log_stats": self.disaster_service.message_logger.get_log_summary()
                    if self.disaster_service.message_logger
                    else {},
                    "recent_pushes": stats.get("recent_pushes", [])[
                        :50
                    ],  # 取最新的50条
                    "session_stats": stats.get("session_stats", {}),
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取统计失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/statistics/reset")
        async def reset_statistics():
            """清除统计数据（等价于 /灾害预警统计清除）"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return JSONResponse(
                        {"error": "统计管理器未初始化"}, status_code=503
                    )

                await self.disaster_service.statistics_manager.reset_stats()

                return {
                    "success": True,
                    "message": "统计数据已清除",
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 通过Web端清除统计失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/reconnect")
        async def force_reconnect():
            """强制重连所有离线数据源"""
            try:
                if not self.disaster_service:
                    return JSONResponse({"error": "服务未初始化"}, status_code=503)

                results = await self.disaster_service.reconnect_all_sources()

                # 统计结果
                triggered = sum(1 for s in results.values() if "已触发" in s)
                failed = sum(1 for s in results.values() if "失败" in s)

                return {
                    "success": True,
                    "message": f"操作完成: 触发 {triggered} 个重连, {failed} 个失败",
                    "details": results,
                }
            except Exception as e:
                logger.error(f"[灾害预警] 通过Web端进行手动重连失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/connections")
        async def get_connections():
            """获取连接状态详情 - 包含所有预期的数据源"""
            try:
                if not self.disaster_service or not self.disaster_service.ws_manager:
                    return JSONResponse(
                        {"error": "WebSocket 管理器未初始化"}, status_code=503
                    )

                # 获取实际连接状态
                actual_connections = (
                    self.disaster_service.ws_manager.get_all_connections_status()
                )

                # 获取子数据源状态
                status_data = self.disaster_service.get_service_status()
                sub_source_status = status_data.get("sub_source_status", {})

                # 获取所有预期的数据源
                expected_sources = self._get_expected_data_sources()

                # 数据源内部名称 -> 配置键的映射
                source_config_key = self._SOURCE_CONFIG_KEY
                data_sources_config = self.config.get("data_sources", {})

                # 合并：确保所有预期的数据源都显示，未连接的标记为 disconnected
                merged_connections = {}
                for source_name, display_name in expected_sources.items():
                    conn_info = {}

                    if source_name in actual_connections:
                        conn_info = actual_connections[
                            source_name
                        ].copy()  # 复制以避免修改原始引用
                    else:
                        # 数据源已配置但未连接
                        conn_info = {
                            "connected": False,
                            "retry_count": 0,
                            "has_handler": False,
                            "status": "未连接",
                        }

                    # 注入是否启用标志
                    cfg_key = source_config_key.get(source_name, source_name)
                    conn_info["enabled"] = bool(
                        data_sources_config.get(cfg_key, {}).get("enabled", False)
                    )

                    # 注入延迟信息（从缓存中读取）
                    latency = self._latency_cache.get(source_name)
                    conn_info["latency"] = latency  # 单位：毫秒，None表示无法测量

                    # 注入子数据源状态
                    if source_name == "fan_studio_all":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "fan_studio", {}
                        )
                    elif source_name == "p2p_main":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "p2p_earthquake", {}
                        )
                    elif source_name == "wolfx_all":
                        conn_info["sub_sources"] = sub_source_status.get("wolfx", {})
                    elif source_name == "global_quake":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "global_quake", {}
                        )

                    merged_connections[display_name] = conn_info

                return {
                    "connections": merged_connections,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取连接状态失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/config")
        async def get_config():
            """获取当前配置 (脱敏)"""
            try:
                # 返回配置的简化版本
                config_summary = {
                    "enabled": self.config.get("enabled", True),
                    "target_sessions_count": len(
                        self.config.get("target_sessions", [])
                    ),
                    "data_sources": self.config.get("data_sources", {}),
                    "earthquake_filters": self.config.get("earthquake_filters", {}),
                    "local_monitoring": {
                        "enabled": self.config.get("local_monitoring", {}).get(
                            "enabled", False
                        ),
                        "place_name": self.config.get("local_monitoring", {}).get(
                            "place_name", ""
                        ),
                    },
                    "display_timezone": self.config.get("display_timezone", "UTC+8"),
                    "web_admin": {
                        k: v for k, v in self.config.get("web_admin", {}).items()
                        if k != "password"
                    },
                }
                return config_summary
            except Exception as e:
                logger.error(f"[灾害预警] 获取配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/logs")
        async def get_logs():
            """获取日志摘要"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.message_logger
                ):
                    return {"enabled": False, "message": "日志功能未启用"}

                summary = self.disaster_service.message_logger.get_log_summary()
                return summary
            except Exception as e:
                logger.error(f"[灾害预警] 获取日志失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/open-log-dir")
        async def open_log_dir():
            """打开日志目录"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.message_logger
                ):
                    return JSONResponse({"error": "日志功能不可用"}, status_code=503)

                log_path = self.disaster_service.message_logger.log_file_path
                log_dir = log_path.parent

                if not log_dir.exists():
                    return JSONResponse({"error": "日志目录不存在"}, status_code=404)

                # 检查是否在 Docker 容器中运行
                if is_running_in_docker():
                    return JSONResponse(
                        {
                            "error": "Docker 环境下不支持在宿主机打开目录，请手动查看挂载路径"
                        },
                        status_code=400,
                    )

                # 打开目录
                system = platform.system()
                if system == "Windows":
                    os.startfile(log_dir)
                elif system == "Darwin":  # macOS
                    await asyncio.create_subprocess_exec("open", str(log_dir))
                else:  # Linux
                    await asyncio.create_subprocess_exec("xdg-open", str(log_dir))

                return {"success": True, "message": "已在文件浏览器中打开日志目录"}
            except Exception as e:
                logger.error(f"[灾害预警] 打开日志目录失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/open-plugin-dir")
        async def open_plugin_dir():
            """打开插件根目录"""
            try:
                # 获取插件根目录 (当前文件所在目录的上级目录)
                plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

                if not os.path.exists(plugin_dir):
                    return JSONResponse({"error": "插件目录不存在"}, status_code=404)

                # 检查是否在 Docker 容器中运行
                if is_running_in_docker():
                    return JSONResponse(
                        {
                            "error": "Docker 环境下不支持在宿主机打开目录，请手动查看挂载路径"
                        },
                        status_code=400,
                    )

                # 打开目录
                system = platform.system()
                if system == "Windows":
                    os.startfile(plugin_dir)
                elif system == "Darwin":  # macOS
                    await asyncio.create_subprocess_exec("open", str(plugin_dir))
                else:  # Linux
                    await asyncio.create_subprocess_exec("xdg-open", str(plugin_dir))

                return {"success": True, "message": "已在文件浏览器中打开插件目录"}
            except Exception as e:
                logger.error(f"[灾害预警] 打开插件目录失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/events")
        async def get_events_paginated(
            page: int = 1,
            limit: int = 50,
            type: str = "",
            source: str = "",
            min_magnitude: float | None = None,
            magnitude_order: str = "",
        ):
            """分页获取历史事件记录（支持按类型、数据源、最小震级过滤与震级排序）"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return {
                        "events": [],
                        "total": 0,
                        "page": page,
                        "limit": limit,
                        "total_pages": 0,
                        "sources": [],
                        "max_limit": 200,
                    }

                db = self.disaster_service.statistics_manager.db
                event_type = type if type else None
                source_filters = [s.strip() for s in source.split(",") if s.strip()]
                max_limit = 200
                # 限制每页最多 max_limit 条
                limit = min(max(1, limit), max_limit)
                page = max(1, page)

                normalized_magnitude_order = magnitude_order.lower().strip()
                if normalized_magnitude_order not in {"", "asc", "desc"}:
                    normalized_magnitude_order = ""

                total = await db.get_events_count(
                    event_type,
                    source_filters,
                    min_magnitude=min_magnitude,
                )
                events = await db.get_events_paginated(
                    page,
                    limit,
                    event_type,
                    source_filters,
                    min_magnitude=min_magnitude,
                    magnitude_order=normalized_magnitude_order or None,
                )
                total_pages = (total + limit - 1) // limit if total > 0 else 0
                source_options = await db.get_event_source_options(event_type)
                # 兼容旧前端：继续返回字符串数组
                available_sources = [
                    item.get("source_label", "")
                    for item in source_options
                    if item.get("source_label")
                ]

                return {
                    "events": events,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                    "sources": available_sources,
                    "source_options": source_options,
                    "max_limit": max_limit,
                }
            except Exception as e:
                logger.error(f"[灾害预警] 分页获取事件失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/events/sources")
        async def get_event_sources(type: str = ""):
            """获取可筛选的数据源列表"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return {"sources": []}

                db = self.disaster_service.statistics_manager.db
                event_type = type if type else None
                source_options = await db.get_event_source_options(event_type)
                # 兼容旧前端：继续返回字符串数组
                sources = [
                    item.get("source_label", "")
                    for item in source_options
                    if item.get("source_label")
                ]
                return {"sources": sources, "source_options": source_options}
            except Exception as e:
                logger.error(f"[灾害预警] 获取数据源列表失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/events/major")
        async def get_major_events(limit: int = 100):
            """获取重大事件列表（用于时间轴）"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return {"events": []}

                db = self.disaster_service.statistics_manager.db
                limit = min(max(1, limit), 200)
                events = await db.get_major_events(limit)
                return {"events": events}
            except Exception as e:
                logger.error(f"[灾害预警] 获取重大事件失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/earthquakes")
        async def get_earthquakes():
            """获取地震数据用于3D地球可视化"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return {"earthquakes": [], "timestamp": datetime.now().isoformat()}

                # 从统计管理器获取最近的地震事件
                stats = self.disaster_service.statistics_manager.stats
                recent_pushes = stats.get("recent_pushes", [])

                earthquakes = []
                for push in recent_pushes:
                    if push.get("type") == "earthquake":
                        eq_data = {
                            "id": push.get("event_id", ""),  # 修正：使用 event_id
                            "latitude": push.get("latitude"),
                            "longitude": push.get("longitude"),
                            "magnitude": push.get("magnitude"),
                            "place": push.get("description", "未知位置"),
                            "time": push.get("time", ""),
                            "source": push.get("source", ""),
                        }
                        # 只添加有坐标的地震
                        if (
                            eq_data["latitude"] is not None
                            and eq_data["longitude"] is not None
                        ):
                            earthquakes.append(eq_data)

                return {
                    "earthquakes": earthquakes,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取地震数据失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/trend")
        async def get_trend(hours: int = 24):
            """获取预警趋势数据"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return JSONResponse(
                        {"error": "统计管理器未初始化"}, status_code=503
                    )

                # 限制范围：24小时或168小时(7天)
                if hours not in [24, 168]:
                    hours = 24

                trend_data = self.disaster_service.statistics_manager.get_trend_data(
                    hours
                )
                return {
                    "data": trend_data,
                    "hours": hours,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取趋势数据失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/heatmap")
        async def get_heatmap(days: int = 180, year: int = None):
            """获取日历热力图数据"""
            try:
                if (
                    not self.disaster_service
                    or not self.disaster_service.statistics_manager
                ):
                    return JSONResponse(
                        {"error": "统计管理器未初始化"}, status_code=503
                    )

                # 如果指定了年份，优先按年份获取
                if year:
                    heatmap_data = (
                        self.disaster_service.statistics_manager.get_heatmap_data(
                            days=0, year=year
                        )
                    )
                else:
                    # 限制范围：90-365天
                    if days < 90:
                        days = 90
                    elif days > 365:
                        days = 365

                    heatmap_data = (
                        self.disaster_service.statistics_manager.get_heatmap_data(
                            days=days
                        )
                    )

                return {
                    "data": heatmap_data,
                    "days": days,
                    "year": year,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取热力图数据失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/simulation-params")
        async def get_simulation_params_api():
            """获取模拟预警可用的参数选项"""
            try:
                return get_simulation_params(self.config)
            except Exception as e:
                logger.error(f"[灾害预警] 获取模拟参数失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/simulate")
        async def simulate_disaster(simulation_data: dict[str, Any]):
            """
            模拟灾害预警（复用命令行版本的过滤器测试逻辑）

            目前仅支持地震模拟，会执行完整的过滤器测试

            支持的参数:
            - target_session: 目标会话UMO (可选，默认使用第一个配置的会话)
            - disaster_type: 灾害类型 (仅支持earthquake)
            - test_type: 数据源ID
            - custom_params: 自定义参数 (震级、经纬度、深度等)
            """
            try:
                if not self.disaster_service:
                    return JSONResponse({"error": "服务未初始化"}, status_code=503)

                # 解析参数
                target_session = simulation_data.get("target_session", "")
                disaster_type = simulation_data.get("disaster_type", "earthquake")
                test_type = simulation_data.get("test_type", "cea_fanstudio")
                custom_params = simulation_data.get("custom_params", {})

                # 目前仅支持地震模拟
                if disaster_type != "earthquake":
                    return JSONResponse(
                        {
                            "error": f"暂不支持 {disaster_type} 类型的模拟，仅支持 earthquake"
                        },
                        status_code=400,
                    )

                # 确定目标 session
                final_target_session = resolve_target_session(
                    self.config, target_session
                )
                if not final_target_session:
                    return JSONResponse({"error": "未配置目标会话"}, status_code=400)

                # 提取地震参数
                lat = float(custom_params.get("latitude", 39.9))
                lon = float(custom_params.get("longitude", 116.4))
                magnitude = float(custom_params.get("magnitude", 5.5))
                depth = float(custom_params.get("depth", 10.0))
                source = custom_params.get("source", test_type)

                manager = self.disaster_service.message_manager
                try:
                    simulation_result = build_earthquake_simulation(
                        manager,
                        lat=lat,
                        lon=lon,
                        magnitude=magnitude,
                        depth=depth,
                        source=source,
                    )
                except ValueError as ve:
                    return JSONResponse({"error": str(ve)}, status_code=400)

                if simulation_result.global_pass and simulation_result.local_pass:
                    logger.info("[灾害预警] 开始构建模拟预警消息...")
                    msg_chain = await manager.build_message_async(
                        simulation_result.disaster_event
                    )
                    await manager._send_message(final_target_session, msg_chain)
                    logger.info(
                        f"[灾害预警] ✅ 模拟事件已成功推送到 {final_target_session}"
                    )
                    simulation_result.report_lines.append(
                        f"\n✅ 消息已发送到: {final_target_session}"
                    )

                    return {
                        "success": True,
                        "message": "\n".join(simulation_result.report_lines),
                    }

                simulation_result.report_lines.append(
                    "\n⛔ 结论: 该事件不会触发预警推送。"
                )
                return {
                    "success": False,
                    "message": "\n".join(simulation_result.report_lines),
                }

            except Exception as e:
                logger.error(f"[灾害预警] 模拟推送失败: {e}")
                logger.error(traceback.format_exc())
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/geolocate")
        async def get_geolocation(request: Request):
            """
            获取当前客户端IP的地理位置信息

            返回格式:
            {
                "success": true,
                "data": {
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "city": "Beijing",
                    "province": "Beijing"
                }
            }
            """
            try:
                # 从请求中获取客户端IP
                client_ip = request.client.host if request.client else None

                # 调用地理定位API，传入客户端IP
                location_data = await fetch_location_from_ip(ip=client_ip)

                return {
                    "success": True,
                    "data": {
                        "latitude": location_data.get("latitude"),
                        "longitude": location_data.get("longitude"),
                        "city": location_data.get("city_zh", ""),
                        "province": location_data.get("province_name_zh", ""),
                        "country": location_data.get("country_name_zh", ""),
                        "ip": location_data.get("ip", ""),
                    },
                }
            except Exception as e:
                logger.error(f"[灾害预警] IP地理定位失败: {e}")
                return JSONResponse(
                    {"success": False, "error": f"获取地理位置失败: {str(e)}"},
                    status_code=500,
                )

        @self.app.get("/api/config-schema")
        async def get_config_schema():
            """获取配置 Schema"""
            try:
                schema_path = os.path.abspath(
                    os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "_conf_schema.json",
                    )
                )
                if os.path.exists(schema_path):
                    with open(schema_path, encoding="utf-8") as f:
                        return json.load(f)
                return {"error": f"Schema file not found at: {schema_path}"}
            except Exception as e:
                logger.error(f"[灾害预警] 获取配置Schema失败: {e}, path: {schema_path}")
                return JSONResponse(
                    {
                        "error": f"{str(e)}, path: {schema_path}, trace: {traceback.format_exc()}"
                    },
                    status_code=500,
                )

        @self.app.get("/api/full-config")
        async def get_full_config():
            """获取完整配置"""
            try:
                full = dict(self.config)
                # 剔除 web_admin.password，避免明文密码通过 API 泄露
                if "web_admin" in full and isinstance(full["web_admin"], dict):
                    full["web_admin"] = {
                        k: v for k, v in full["web_admin"].items() if k != "password"
                    }
                return full
            except Exception as e:
                logger.error(f"[灾害预警] 获取完整配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/full-config")
        async def update_full_config(config_data: dict[str, Any]):
            """更新完整配置"""
            try:
                # 1. 创建当前配置的副本 (转换为普通 dict)
                current_config_dict = dict(self.config)

                # 定义递归更新函数
                def deep_update(target, updates):
                    for k, v in updates.items():
                        if (
                            isinstance(v, dict)
                            and k in target
                            and isinstance(target[k], dict)
                        ):
                            deep_update(target[k], v)
                        else:
                            target[k] = v

                # 2. 应用更新到副本
                deep_update(current_config_dict, config_data)

                # 3. 执行校验
                validated_config = ConfigValidator.validate(current_config_dict)

                # 4. 将校验后的配置回写到 self.config
                # 注意：self.config 是 AstrBotConfig 对象，我们需要逐项更新
                for key, value in validated_config.items():
                    self.config[key] = value

                # 5. 保存配置
                if hasattr(self.config, "save_config"):
                    self.config.save_config()

                return {"success": True, "message": "配置已校验并保存"}
            except Exception as e:
                logger.error(f"[灾害预警] 保存配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/session-config/sessions")
        async def list_session_configs():
            """列出当前已知会话及其配置概览"""
            try:
                if not self.disaster_service or not hasattr(
                    self.disaster_service, "session_config_manager"
                ):
                    return JSONResponse(
                        {"error": "会话配置管理器未初始化"}, status_code=503
                    )

                mgr = self.disaster_service.session_config_manager
                sessions = mgr.list_all_known_sessions()

                data = []
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

                return {
                    "sessions": data,
                    "total": len(data),
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取会话配置列表失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/session-config/{umo:path}")
        async def get_session_config(umo: str):
            """获取指定会话的 override 与 effective 配置"""
            try:
                if not self.disaster_service or not hasattr(
                    self.disaster_service, "session_config_manager"
                ):
                    return JSONResponse(
                        {"error": "会话配置管理器未初始化"}, status_code=503
                    )

                mgr = self.disaster_service.session_config_manager
                return {
                    "session": umo,
                    "override": mgr.get_override(umo),
                    "effective": mgr.get_effective_config(umo),
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取会话配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/session-config/{umo:path}")
        async def update_session_config(umo: str, payload: dict[str, Any]):
            """更新指定会话配置（提交 effective 或 override）"""
            try:
                if not self.disaster_service or not hasattr(
                    self.disaster_service, "session_config_manager"
                ):
                    return JSONResponse(
                        {"error": "会话配置管理器未初始化"}, status_code=503
                    )

                mgr = self.disaster_service.session_config_manager
                mode = payload.get("mode", "effective")

                if mode == "override":
                    override = payload.get("override", {})
                    if not isinstance(override, dict):
                        return JSONResponse(
                            {"error": "override 必须是对象"}, status_code=400
                        )
                    mgr.set_override(umo, override)
                else:
                    effective = payload.get("effective", payload)
                    if not isinstance(effective, dict):
                        return JSONResponse(
                            {"error": "effective 必须是对象"}, status_code=400
                        )
                    mgr.update_session_from_effective(umo, effective)

                return {
                    "success": True,
                    "message": "会话配置已保存",
                    "session": umo,
                    "override": mgr.get_override(umo),
                    "effective": mgr.get_effective_config(umo),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 更新会话配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.delete("/api/session-config/{umo:path}")
        async def reset_session_config(umo: str):
            """清空指定会话覆写配置（回退到默认）"""
            try:
                if not self.disaster_service or not hasattr(
                    self.disaster_service, "session_config_manager"
                ):
                    return JSONResponse(
                        {"error": "会话配置管理器未初始化"}, status_code=503
                    )

                mgr = self.disaster_service.session_config_manager
                mgr.delete_override(umo)
                return {
                    "success": True,
                    "message": "会话覆写已清空",
                    "session": umo,
                    "override": {},
                    "effective": mgr.get_effective_config(umo),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 清空会话配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        # ========== WebSocket 端点 ==========
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 端点 - 实时数据推送"""
            # 在 accept() 前校验 token，不合法则拒绝握手
            if self._auth_enabled:
                token = websocket.query_params.get("token", "")
                if not token:
                    token = websocket.headers.get("Authorization", "")
                    token = token[7:] if token.startswith("Bearer ") else ""
                if not self._auth_token or not secrets.compare_digest(token, self._auth_token):
                    await websocket.close(code=1008)  # 1008 = Policy Violation
                    return

            await websocket.accept()
            self._ws_connections.append(websocket)
            logger.info(
                f"[灾害预警] 有 WebSocket 客户端已连接，当前连接数: {len(self._ws_connections)}"
            )

            try:
                # 发送初始数据
                await self._send_full_update(websocket)

                # 保持连接并处理客户端消息
                while True:
                    try:
                        data = await websocket.receive_text()
                        msg = json.loads(data)

                        # 处理客户端请求
                        if msg.get("type") == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif msg.get("type") == "refresh":
                            await self._send_full_update(websocket)
                    except json.JSONDecodeError:
                        pass  # 忽略无效 JSON
            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.debug(f"[灾害预警] WebSocket 连接异常: {e}")
            finally:
                if websocket in self._ws_connections:
                    self._ws_connections.remove(websocket)
                logger.info(
                    f"[灾害预警] 有 WebSocket 客户端已断开，当前连接数: {len(self._ws_connections)}"
                )

    async def _send_full_update(self, websocket: WebSocket):
        """向单个 WebSocket 客户端发送完整数据更新"""
        try:
            data = await self._get_realtime_data()
            await websocket.send_json({"type": "full_update", "data": data})
        except Exception as e:
            logger.debug(f"[灾害预警] 发送数据失败: {e}")

    async def _broadcast_data(self):
        """向所有连接的客户端广播数据更新"""
        if not self._ws_connections:
            return

        data = await self._get_realtime_data()
        message = {"type": "update", "data": data}

        # 发送给所有连接的客户端
        # 使用快照避免并发修改导致跳过某些连接
        disconnected = []
        for ws in list(self._ws_connections):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        # 清理断开的连接
        for ws in disconnected:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)

    async def _get_realtime_data(self) -> dict:
        """获取实时数据用于 WebSocket 推送"""
        result = {"timestamp": datetime.now().isoformat()}

        # 状态数据
        try:
            if self.disaster_service:
                status = self.disaster_service.get_service_status()
                result["status"] = {
                    "running": status.get("running", False),
                    "uptime": status.get("uptime", "未知"),
                    "active_connections": status.get("active_websocket_connections", 0),
                    "total_connections": status.get("total_connections", 0),
                    "sub_source_status": status.get(
                        "sub_source_status", {}
                    ),  # 新增：子数据源状态
                    "start_time": status.get("start_time"),
                    "version": get_plugin_version(),
                }
        except Exception as e:
            logger.debug(f"[灾害预警] 获取状态数据失败: {e}")

        # 统计数据
        try:
            if self.disaster_service and self.disaster_service.statistics_manager:
                stats = self.disaster_service.statistics_manager.stats
                result["statistics"] = {
                    "total_events": stats.get("total_events", 0),
                    "by_type": dict(stats.get("by_type", {})),
                    "by_source": dict(stats.get("by_source", {})),
                    "earthquake_stats": {
                        "by_magnitude": dict(
                            stats.get("earthquake_stats", {}).get("by_magnitude", {})
                        ),
                        "by_region": dict(
                            stats.get("earthquake_stats", {}).get("by_region", {})
                        ),
                        "max_magnitude": stats.get("earthquake_stats", {}).get(
                            "max_magnitude"
                        ),
                    },
                    "weather_stats": {
                        "by_level": dict(
                            stats.get("weather_stats", {}).get("by_level", {})
                        ),
                        "by_type": dict(
                            stats.get("weather_stats", {}).get("by_type", {})
                        ),
                        "by_region": dict(
                            stats.get("weather_stats", {}).get("by_region", {})
                        ),
                    },
                    "log_stats": self.disaster_service.message_logger.get_log_summary()
                    if self.disaster_service and self.disaster_service.message_logger
                    else {},
                    "recent_pushes": stats.get("recent_pushes", [])[:250],
                    "session_stats": stats.get("session_stats", {}),
                }
        except Exception as e:
            logger.debug(f"[灾害预警] 获取统计数据失败: {e}")

        # 连接状态
        try:
            if self.disaster_service and self.disaster_service.ws_manager:
                actual_connections = (
                    self.disaster_service.ws_manager.get_all_connections_status()
                )

                # 获取子数据源状态
                status_data = self.disaster_service.get_service_status()
                sub_source_status = status_data.get("sub_source_status", {})

                expected_sources = self._get_expected_data_sources()

                # WebSocket推送时使用缓存的延迟数据，不执行ping
                source_config_key = self._SOURCE_CONFIG_KEY
                data_sources_config = self.config.get("data_sources", {})
                merged_connections = {}
                for source_name, display_name in expected_sources.items():
                    conn_info = {}

                    if source_name in actual_connections:
                        conn_info = actual_connections[source_name].copy()
                    else:
                        conn_info = {
                            "connected": False,
                            "retry_count": 0,
                            "has_handler": False,
                            "status": "未连接",
                        }

                    # 注入是否启用标志（与 /api/connections 保持一致）
                    cfg_key = source_config_key.get(source_name, source_name)
                    conn_info["enabled"] = bool(
                        data_sources_config.get(cfg_key, {}).get("enabled", False)
                    )

                    # 使用缓存的延迟信息
                    conn_info["latency"] = self._latency_cache.get(source_name)

                    # 注入子数据源状态
                    if source_name == "fan_studio_all":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "fan_studio", {}
                        )
                    elif source_name == "p2p_main":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "p2p_earthquake", {}
                        )
                    elif source_name == "wolfx_all":
                        conn_info["sub_sources"] = sub_source_status.get("wolfx", {})
                    elif source_name == "global_quake":
                        conn_info["sub_sources"] = sub_source_status.get(
                            "global_quake", {}
                        )

                    merged_connections[display_name] = conn_info

                result["connections"] = merged_connections
        except Exception as e:
            logger.debug(f"[灾害预警] 获取连接状态失败: {e}")

        # 地震数据
        try:
            if self.disaster_service and self.disaster_service.statistics_manager:
                stats = self.disaster_service.statistics_manager.stats
                recent_pushes = stats.get("recent_pushes", [])
                earthquakes = []
                for push in recent_pushes:
                    if push.get("type") == "earthquake":
                        eq_data = {
                            "id": push.get("event_id", ""),
                            "latitude": push.get("latitude"),
                            "longitude": push.get("longitude"),
                            "magnitude": push.get("magnitude"),
                            "place": push.get("description", "未知位置"),
                            "time": push.get("time", ""),
                            "source": push.get("source", ""),
                        }
                        if (
                            eq_data["latitude"] is not None
                            and eq_data["longitude"] is not None
                        ):
                            earthquakes.append(eq_data)
                result["earthquakes"] = earthquakes
        except Exception as e:
            logger.debug(f"[灾害预警] 获取地震数据失败: {e}")

        return result

    async def _broadcast_loop(self):
        """后台广播循环 - 作为保底同步机制，较低频率"""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒同步一次（保底，主要依赖事件驱动）
                await self._broadcast_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[灾害预警] 广播循环异常: {e}")

    async def notify_event(self, event_data: dict = None):
        """
        事件驱动推送 - 当有新灾害事件时立即推送给所有客户端

        Args:
            event_data: 可选，新事件的数据。如果不提供，会推送完整数据更新。
        """
        if not self._ws_connections:
            return

        # 获取最新数据并立即推送
        data = await self._get_realtime_data()
        message = {
            "type": "event",  # 事件驱动的更新
            "data": data,
        }

        if event_data:
            message["new_event"] = event_data

        # 发送给所有连接的客户端
        disconnected = []
        for ws in self._ws_connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        # 清理断开的连接
        for ws in disconnected:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)

        if event_data:
            logger.debug(
                f"[灾害预警] 已推送新事件到 {len(self._ws_connections)} 个客户端"
            )

    def _get_expected_data_sources(self) -> dict[str, str]:
        """获取所有支持的数据源列表 (无论是否启用)

        Returns:
            dict: 内部连接名称 -> 显示名称 的映射
        """
        expected = {}

        # FAN Studio
        expected["fan_studio_all"] = "FAN Studio"

        # P2P
        expected["p2p_main"] = "P2P地震情報"

        # Wolfx
        expected["wolfx_all"] = "Wolfx"

        # Global Quake
        expected["global_quake"] = "Global Quake"

        return expected

    def _get_data_source_host(self, source_name: str) -> str | None:
        """获取数据源的主机名（用于ping）

        Args:
            source_name: 数据源内部名称

        Returns:
            主机名，如果无法确定则返回None
        """
        host_map = {
            "fan_studio_all": "ws.fanstudio.tech",
            "p2p_main": "api.p2pquake.net",
            "wolfx_all": "ws-api.wolfx.jp",
            "global_quake": "gqm.aloys23.link",
        }
        return host_map.get(source_name)

    async def _ping_host(
        self, host: str, port: int = 443, timeout: float = 3.0
    ) -> float | None:
        """使用 TCP 连接测试主机延迟 (tcping)

        Args:
            host: 主机名或IP地址
            port: 端口号，默认 443
            timeout: 超时时间（秒）

        Returns:
            延迟时间（毫秒），如果失败则返回None
        """
        try:
            start_time = asyncio.get_running_loop().time()
            # 尝试建立 TCP 连接
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=timeout)
            end_time = asyncio.get_running_loop().time()

            # 关闭连接
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

            # 计算延迟 (毫秒)
            latency = (end_time - start_time) * 1000
            return latency

        except (asyncio.TimeoutError, OSError, Exception) as e:
            logger.debug(f"[灾害预警] TCP Ping {host}:{port} 异常: {e}")
            return None

    async def _background_ping_loop(self):
        """后台定期更新延迟缓存"""
        logger.info("[灾害预警] 启动后台延迟检测任务")

        # 新增：记录连续失败次数
        ping_failures = {}

        while True:
            try:
                # 获取所有预期的数据源
                expected_sources = self._get_expected_data_sources()

                # 并发测试所有数据源的延迟
                ping_tasks = {}
                for source_name in expected_sources.keys():
                    host = self._get_data_source_host(source_name)
                    if host:
                        # 使用 TCP Ping 测试 443 端口
                        ping_tasks[source_name] = self._ping_host(
                            host, port=443, timeout=2.0
                        )

                # 等待所有ping完成
                if ping_tasks:
                    results = await asyncio.gather(
                        *ping_tasks.values(), return_exceptions=True
                    )
                    for source_name, result in zip(ping_tasks.keys(), results):
                        if isinstance(result, Exception) or result is None:
                            # 失败时增加计数
                            ping_failures[source_name] = (
                                ping_failures.get(source_name, 0) + 1
                            )
                            # 连续失败 3 次才判定为无法测量
                            if ping_failures[source_name] >= 3:
                                self._latency_cache[source_name] = None
                        else:
                            # 成功时重置计数并更新缓存
                            ping_failures[source_name] = 0
                            self._latency_cache[source_name] = result

                logger.debug(f"[灾害预警] 延迟缓存已更新: {self._latency_cache}")

                # 每30秒更新一次，与前端广播频率保持一致
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info("[灾害预警] 后台延迟检测任务已停止")
                break
            except Exception as e:
                logger.error(f"[灾害预警] 后台延迟检测出错: {e}")
                await asyncio.sleep(30)

    async def start(self):
        """启动 Web 服务器"""
        if not FASTAPI_AVAILABLE:
            logger.error("[灾害预警] 无法启动 Web 管理端: FastAPI 未安装")
            return

        web_config = self.config.get("web_admin", {})
        host = web_config.get("host", "0.0.0.0")
        port = web_config.get("port", 8089)

        config = uvicorn.Config(
            self.app, host=host, port=port, log_level="warning", access_log=False
        )
        self.server = uvicorn.Server(config)

        logger.info(f"[灾害预警] Web 管理端已启动: http://{host}:{port}")

        # 在后台运行服务器
        self._server_task = asyncio.create_task(self.server.serve())

        # 启动 WebSocket 广播循环
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        # 启动后台延迟检测任务
        self._ping_task = asyncio.create_task(self._background_ping_loop())

    async def stop(self):
        """停止 Web 服务器"""
        # 停止后台延迟检测任务
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        # 停止 WebSocket 广播循环
        if self._broadcast_task:
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # 关闭所有 WebSocket 连接
        for ws in self._ws_connections:
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_connections.clear()

        # 关闭共享的 GeoIP ClientSession
        try:
            await close_geoip_session()
        except Exception as e:
            logger.debug(f"[灾害预警] 关闭 GeoIP session 时出错: {e}")

        if self.server:
            self.server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
            logger.info("[灾害预警] Web 管理端已停止")
