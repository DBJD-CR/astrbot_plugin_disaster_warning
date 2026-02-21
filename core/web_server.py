"""
灾害预警插件 Web 管理服务器
提供基于 Web 管理界面的 REST API 和 WebSocket 端点
"""

import asyncio
import json
import os
import platform
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ..utils.geolocation import close_geoip_session, fetch_location_from_ip
from ..utils.version import get_plugin_version
from .config_validator import ConfigValidator

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
        admin_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin")
        if os.path.exists(admin_dir):
            self.app.mount(
                "/", StaticFiles(directory=admin_dir, html=True), name="admin"
            )

    def _register_routes(self):
        """注册 API 路由"""

        @self.app.get("/logo.png")
        async def get_logo():
            """获取插件 Logo"""
            logo_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "logo.png"
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
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as e:
                logger.error(f"[灾害预警] 获取统计失败: {e}")
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
                    "web_admin": self.config.get("web_admin", {}),
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
                plugin_dir = os.path.dirname(os.path.dirname(__file__))

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
        async def get_simulation_params():
            """获取模拟预警可用的参数选项"""
            try:
                # 获取已配置的目标会话
                target_sessions = self.config.get("target_sessions", [])

                # 定义灾害类型及其数据源格式
                disaster_types = {
                    "earthquake": {
                        "label": "地震",
                        "icon": "🌍",
                        "formats": [
                            # FAN Studio 数据源
                            {
                                "value": "cea_fanstudio",
                                "label": "FAN Studio - 中国地震预警网 (CEA)",
                            },
                            {
                                "value": "cea_pr_fanstudio",
                                "label": "FAN Studio - 中国地震预警网 (省级)",
                            },
                            {
                                "value": "cenc_fanstudio",
                                "label": "FAN Studio - 中国地震台网 (CENC)",
                            },
                            {
                                "value": "cwa_fanstudio",
                                "label": "FAN Studio - 台湾中央气象署 (强震即时警报)",
                            },
                            {
                                "value": "cwa_fanstudio_report",
                                "label": "FAN Studio - 台湾中央气象署 (地震报告)",
                            },
                            {
                                "value": "jma_fanstudio",
                                "label": "FAN Studio - 日本气象厅 (JMA)",
                            },
                            {"value": "usgs_fanstudio", "label": "FAN Studio - USGS"},
                            # Wolfx 数据源
                            {
                                "value": "jma_wolfx",
                                "label": "Wolfx - 日本 JMA 紧急地震速报",
                            },
                            {
                                "value": "cea_wolfx",
                                "label": "Wolfx - 中国 CENC 地震预警",
                            },
                            {
                                "value": "cwa_wolfx",
                                "label": "Wolfx - 台湾 CWA 地震预警",
                            },
                            {
                                "value": "cenc_wolfx",
                                "label": "Wolfx - 中国 CENC 地震情报",
                            },
                            {
                                "value": "jma_wolfx_info",
                                "label": "Wolfx - 日本 JMA 地震情报",
                            },
                            # P2P 数据源
                            {
                                "value": "jma_p2p",
                                "label": "P2P - 日本 JMA 紧急地震速报",
                            },
                            {
                                "value": "jma_p2p_info",
                                "label": "P2P - 日本 JMA 地震情报",
                            },
                            # Global Quake
                            {"value": "global_quake", "label": "Global Quake"},
                        ],
                    },
                    "tsunami": {
                        "label": "海啸",
                        "icon": "🌊",
                        "formats": [
                            {
                                "value": "china_tsunami_fanstudio",
                                "label": "FAN Studio - 中国海啸预警",
                            },
                            {"value": "jma_tsunami_p2p", "label": "P2P - 日本海啸预警"},
                        ],
                    },
                    "weather": {
                        "label": "气象",
                        "icon": "☁️",
                        "formats": [
                            {
                                "value": "china_weather_fanstudio",
                                "label": "FAN Studio - 中国气象预警",
                            }
                        ],
                    },
                }

                return {
                    "target_sessions": target_sessions,
                    "disaster_types": disaster_types,
                    "timestamp": datetime.now().isoformat(),
                }
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
                final_target_session = None
                if target_session:
                    final_target_session = target_session
                else:
                    target_sessions = self.config.get("target_sessions", [])
                    if target_sessions:
                        final_target_session = target_sessions[0]
                    else:
                        return JSONResponse(
                            {"error": "未配置目标会话"}, status_code=400
                        )

                # 提取地震参数
                lat = float(custom_params.get("latitude", 39.9))
                lon = float(custom_params.get("longitude", 116.4))
                magnitude = float(custom_params.get("magnitude", 5.5))
                depth = float(custom_params.get("depth", 10.0))
                source = custom_params.get("source", test_type)

                # 复用命令行版本的逻辑
                from ..models.models import (
                    DATA_SOURCE_MAPPING,
                    DisasterEvent,
                    DisasterType,
                    EarthquakeData,
                    get_data_source_from_id,
                )
                from ..utils.fe_regions import translate_place_name

                manager = self.disaster_service.message_manager

                # 1. 获取数据源
                data_source = get_data_source_from_id(source)
                if not data_source:
                    return JSONResponse(
                        {
                            "error": f"无效的数据源: {source}",
                            "valid_sources": list(DATA_SOURCE_MAPPING.keys()),
                        },
                        status_code=400,
                    )

                # 2. 构造模拟数据
                final_place_name = translate_place_name("模拟震中", lat, lon)

                earthquake = EarthquakeData(
                    id=f"sim_{int(datetime.now().timestamp())}",
                    event_id=f"sim_{int(datetime.now().timestamp())}",
                    source=data_source,
                    disaster_type=DisasterType.EARTHQUAKE,
                    shock_time=datetime.now(),
                    latitude=lat,
                    longitude=lon,
                    depth=depth,
                    magnitude=magnitude,
                    place_name=final_place_name,
                    source_id=source,
                    raw_data={"test": True, "source_id": source},
                )

                # 特定数据源处理
                if source == "usgs_fanstudio":
                    earthquake.update_time = datetime.now()
                if source in ["jma_p2p", "jma_wolfx", "jma_p2p_info"]:
                    earthquake.max_scale = max(0, min(7, int(magnitude - 2)))
                    earthquake.scale = earthquake.max_scale

                disaster_event = DisasterEvent(
                    id=f"sim_evt_{int(datetime.now().timestamp())}",
                    data=earthquake,
                    source=data_source,
                    disaster_type=DisasterType.EARTHQUAKE,
                    source_id=source,
                )

                # 3. 执行过滤器测试
                report_lines = [
                    "🧪 灾害预警模拟报告",
                    f"Input: M{magnitude} @ ({lat}, {lon}), Depth {depth}km\n",
                ]

                global_pass = True
                local_pass = True

                # 全局过滤器
                if manager.intensity_filter:
                    if manager.intensity_filter.should_filter(earthquake):
                        global_pass = False
                        report_lines.append(
                            "❌ 全局过滤: 拦截 (不满足最小震级/烈度要求)"
                        )
                    else:
                        report_lines.append("✅ 全局过滤: 通过")

                # 本地监控
                if manager.local_monitor:
                    result = manager.local_monitor.inject_local_estimation(earthquake)
                    if result is None:
                        report_lines.append("ℹ️ 本地监控: 未启用")
                    else:
                        allowed = result.get("is_allowed", True)
                        dist = result.get("distance")
                        inte = result.get("intensity")

                        if allowed:
                            report_lines.append("✅ 本地监控: 触发")
                        else:
                            local_pass = False
                            report_lines.append("❌ 本地监控: 拦截 (严格模式生效中)")

                        report_lines.append(
                            f"   ⦁ 严格模式: {'开启' if manager.local_monitor.strict_mode else '关闭 (仅计算不拦截)'}"
                        )
                        dist_str = f"{dist:.1f} km" if dist is not None else "未知"
                        inte_str = f"{inte:.1f}" if inte is not None else "未知"
                        report_lines.extend(
                            [
                                f"   ⦁ 距本地: {dist_str}",
                                f"   ⦁ 预估最大本地烈度: {inte_str}",
                                f"   ⦁ 本地烈度阈值: {manager.local_monitor.threshold}",
                            ]
                        )
                else:
                    report_lines.append("ℹ️ 本地监控: 未配置")

                # 4. 如果通过过滤器，发送消息
                if global_pass and local_pass:
                    logger.info("[灾害预警] 开始构建模拟预警消息...")
                    msg_chain = await manager.build_message_async(disaster_event)
                    await manager._send_message(final_target_session, msg_chain)
                    logger.info(
                        f"[灾害预警] ✅ 模拟事件已成功推送到 {final_target_session}"
                    )
                    report_lines.append(f"\n✅ 消息已发送到: {final_target_session}")

                    return {
                        "success": True,
                        "message": "\n".join(report_lines),
                    }
                else:
                    report_lines.append("\n⛔ 结论: 该事件不会触发预警推送。")
                    return {
                        "success": False,
                        "message": "\n".join(report_lines),
                    }

            except Exception as e:
                logger.error(f"[灾害预警] 模拟推送失败: {e}")
                import traceback

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
                        os.path.dirname(os.path.dirname(__file__)), "_conf_schema.json"
                    )
                )
                if os.path.exists(schema_path):
                    with open(schema_path, encoding="utf-8") as f:
                        return json.load(f)
                return {"error": f"Schema file not found at: {schema_path}"}
            except Exception as e:
                logger.error(f"[灾害预警] 获取配置Schema失败: {e}, path: {schema_path}")
                import traceback

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
                # 直接返回 Config 对象 (AstrBotConfig 实现了 dict 接口)
                return dict(self.config)
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

        # ========== WebSocket 端点 ==========
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 端点 - 实时数据推送"""
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

        except (asyncio.TimeoutError, OSError, Exception):
            # logger.debug(f"[灾害预警] TCP Ping {host}:{port} 异常: {e}")
            return None

    async def _background_ping_loop(self):
        """后台定期更新延迟缓存"""
        logger.info("[灾害预警] 启动后台延迟检测任务")

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
                        if isinstance(result, Exception):
                            self._latency_cache[source_name] = None
                        else:
                            self._latency_cache[source_name] = result

                logger.debug(f"[灾害预警] 延迟缓存已更新: {self._latency_cache}")

                # 每45秒更新一次
                await asyncio.sleep(45)

            except asyncio.CancelledError:
                logger.info("[灾害预警] 后台延迟检测任务已停止")
                break
            except Exception as e:
                logger.error(f"[灾害预警] 后台延迟检测出错: {e}")
                await asyncio.sleep(45)

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
