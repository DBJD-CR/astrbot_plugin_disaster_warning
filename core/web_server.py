"""
Web Admin Server for Disaster Warning Plugin
Provides REST API and WebSocket endpoints for web-based management
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

from astrbot.api import logger

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("[灾害预警] FastAPI 未安装，Web 管理端功能不可用。请运行: pip install fastapi uvicorn")


class WebAdminServer:
    """Web 管理端服务器"""

    def __init__(self, disaster_service, config: dict[str, Any]):
        self.disaster_service = disaster_service
        self.config = config
        self.app = None
        self.server = None
        self._server_task = None
        self._broadcast_task = None
        self._ws_connections: list[WebSocket] = []  # Active WebSocket connections
        
        if not FASTAPI_AVAILABLE:
            return
            
        self._setup_app()

    def _setup_app(self):
        """配置 FastAPI 应用"""
        
        self.app = FastAPI(
            title="灾害预警管理端",
            description="灾害预警插件 Web 管理界面",
            version="1.0.0"
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
            self.app.mount("/", StaticFiles(directory=admin_dir, html=True), name="admin")

    def _register_routes(self):
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
                    "message_logger_enabled": status.get("message_logger_enabled", False),
                    "timestamp": datetime.now().isoformat(),
                    "start_time": status.get("start_time")
                }
            except Exception as e:
                logger.error(f"[Web Admin] 获取状态失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/statistics")
        async def get_statistics():
            """获取统计数据"""
            try:
                if not self.disaster_service or not self.disaster_service.statistics_manager:
                    return JSONResponse({"error": "统计管理器未初始化"}, status_code=503)
                
                stats = self.disaster_service.statistics_manager.stats
                return {
                    "total_received": stats.get("total_received", 0),
                    "total_events": stats.get("total_events", 0),
                    "start_time": stats.get("start_time", ""),
                    "last_updated": stats.get("last_updated", ""),
                    "by_type": dict(stats.get("by_type", {})),
                    "by_source": dict(stats.get("by_source", {})),
                    "earthquake_stats": {
                        "by_magnitude": dict(stats.get("earthquake_stats", {}).get("by_magnitude", {})),
                        "max_magnitude": stats.get("earthquake_stats", {}).get("max_magnitude")
                    },
                    "weather_stats": {
                        "by_level": dict(stats.get("weather_stats", {}).get("by_level", {})),
                        "by_type": dict(stats.get("weather_stats", {}).get("by_type", {}))
                    },
                    "recent_pushes": stats.get("recent_pushes", [])[-20:],  # 最近20条
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"[Web Admin] 获取统计失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/connections")
        async def get_connections():
            """获取连接状态详情 - 包含所有预期的数据源"""
            try:
                if not self.disaster_service or not self.disaster_service.ws_manager:
                    return JSONResponse({"error": "WebSocket 管理器未初始化"}, status_code=503)
                
                # 获取实际连接状态
                actual_connections = self.disaster_service.ws_manager.get_all_connections_status()
                
                # 获取所有预期的数据源
                expected_sources = self._get_expected_data_sources()
                
                # 合并：确保所有预期的数据源都显示，未连接的标记为 disconnected
                merged_connections = {}
                for source_name, display_name in expected_sources.items():
                    if source_name in actual_connections:
                        merged_connections[display_name] = actual_connections[source_name]
                    else:
                        # 数据源已配置但未连接
                        merged_connections[display_name] = {
                            "connected": False,
                            "retry_count": 0,
                            "has_handler": False,
                            "status": "未连接"
                        }
                
                return {
                    "connections": merged_connections,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"[Web Admin] 获取连接状态失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/config")
        async def get_config():
            """获取当前配置 (脱敏)"""
            try:
                # 返回配置的简化版本
                config_summary = {
                    "enabled": self.config.get("enabled", True),
                    "target_groups_count": len(self.config.get("target_groups", [])),
                    "platform_name": self.config.get("platform_name", "default"),
                    "data_sources": self.config.get("data_sources", {}),
                    "earthquake_filters": self.config.get("earthquake_filters", {}),
                    "local_monitoring": {
                        "enabled": self.config.get("local_monitoring", {}).get("enabled", False),
                        "place_name": self.config.get("local_monitoring", {}).get("place_name", "")
                    },
                    "web_admin": self.config.get("web_admin", {})
                }
                return config_summary
            except Exception as e:
                logger.error(f"[Web Admin] 获取配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/logs")
        async def get_logs():
            """获取日志摘要"""
            try:
                if not self.disaster_service or not self.disaster_service.message_logger:
                    return {"enabled": False, "message": "日志功能未启用"}
                
                summary = self.disaster_service.message_logger.get_log_summary()
                return summary
            except Exception as e:
                logger.error(f"[Web Admin] 获取日志失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/earthquakes")
        async def get_earthquakes():
            """获取地震数据用于3D地球可视化"""
            try:
                if not self.disaster_service or not self.disaster_service.statistics_manager:
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
                            "source": push.get("source", "")
                        }
                        # 只添加有坐标的地震
                        if eq_data["latitude"] is not None and eq_data["longitude"] is not None:
                            earthquakes.append(eq_data)
                
                return {
                    "earthquakes": earthquakes,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"[Web Admin] 获取地震数据失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/test-push")
        async def test_push(
            target_group: str = None,
            disaster_type: str = "earthquake"
        ):
            """
            简单测试推送 - 使用预设的测试数据
            
            参数:
            - target_group: 目标群号 (可选，默认使用第一个配置的群)
            - disaster_type: 灾害类型 (earthquake/tsunami/weather)
            
            注意: 此端点使用预设的测试数据。如需自定义参数，请使用 /api/simulate 端点。
            """
            try:
                if not self.disaster_service:
                    return JSONResponse({"error": "服务未初始化"}, status_code=503)
                
                # 构建目标 session
                target_session = None
                platform_name = self.config.get("platform_name", "default")
                
                if target_group:
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                else:
                    # 使用第一个配置的目标群
                    target_groups = self.config.get("target_groups", [])
                    if target_groups:
                        target_session = f"{platform_name}:GroupMessage:{target_groups[0]}"
                    else:
                        return JSONResponse({"error": "未配置目标群组"}, status_code=400)
                
                # 调用 test_push，使用默认测试格式
                result = await self.disaster_service.test_push(
                    target_session, 
                    disaster_type,
                    test_type=None  # 使用默认格式
                )
                return {"success": "✅" in result if result else False, "message": result}
            except Exception as e:
                logger.error(f"[Web Admin] 测试推送失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/simulation-params")
        async def get_simulation_params():
            """获取模拟预警可用的参数选项"""
            try:
                # 获取已配置的目标群
                target_groups = self.config.get("target_groups", [])
                platform_name = self.config.get("platform_name", "default")
                
                # 定义灾害类型及其数据源格式
                disaster_types = {
                    "earthquake": {
                        "label": "地震",
                        "icon": "🌍",
                        "formats": [
                            # FAN Studio 数据源
                            {"value": "cea_fanstudio", "label": "FAN Studio - 中国地震预警网 (CEA)"},
                            {"value": "cenc_fanstudio", "label": "FAN Studio - 中国地震台网 (CENC)"},
                            {"value": "cwa_fanstudio", "label": "FAN Studio - 台湾中央气象署 (CWA)"},
                            {"value": "jma_fanstudio", "label": "FAN Studio - 日本气象厅 (JMA)"},
                            {"value": "usgs_fanstudio", "label": "FAN Studio - USGS"},
                            # Wolfx 数据源
                            {"value": "jma_wolfx", "label": "Wolfx - 日本 JMA 紧急地震速报"},
                            {"value": "cea_wolfx", "label": "Wolfx - 中国 CENC 地震预警"},
                            {"value": "cwa_wolfx", "label": "Wolfx - 台湾 CWA 地震预警"},
                            {"value": "cenc_wolfx", "label": "Wolfx - 中国 CENC 地震情报"},
                            {"value": "jma_wolfx_info", "label": "Wolfx - 日本 JMA 地震情报"},
                            # P2P 数据源
                            {"value": "jma_p2p", "label": "P2P - 日本 JMA 紧急地震速报"},
                            {"value": "jma_p2p_info", "label": "P2P - 日本 JMA 地震情报"},
                            # Global Quake
                            {"value": "global_quake", "label": "Global Quake"}
                        ]
                    },
                    "tsunami": {
                        "label": "海啸",
                        "icon": "🌊",
                        "formats": [
                            {"value": "china_tsunami_fanstudio", "label": "FAN Studio - 中国海啸预警"},
                            {"value": "jma_tsunami_p2p", "label": "P2P - 日本海啸预警"}
                        ]
                    },
                    "weather": {
                        "label": "气象",
                        "icon": "☁️",
                        "formats": [
                            {"value": "china_weather_fanstudio", "label": "FAN Studio - 中国气象预警"}
                        ]
                    }
                }
                
                return {
                    "target_groups": target_groups,
                    "platform_name": platform_name,
                    "disaster_types": disaster_types,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"[Web Admin] 获取模拟参数失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/simulate")
        async def simulate_disaster(simulation_data: dict[str, Any]):
            """
            自定义模拟灾害预警
            
            支持的参数:
            - target_group: 目标群号 (可选，默认使用第一个配置的群)
            - disaster_type: 灾害类型 (earthquake/tsunami/weather)
            - test_type: 测试格式 (china/japan/usgs 等)
            - custom_params: 自定义参数 (震级、经纬度、深度、地名等)
            """
            try:
                if not self.disaster_service:
                    return JSONResponse({"error": "服务未初始化"}, status_code=503)
                
                # 解析参数
                target_group = simulation_data.get("target_group", "")
                disaster_type = simulation_data.get("disaster_type", "earthquake")
                test_type = simulation_data.get("test_type", "china")
                custom_params = simulation_data.get("custom_params", {})
                
                # 构建目标 session
                platform_name = self.config.get("platform_name", "default")
                
                if target_group:
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                else:
                    target_groups = self.config.get("target_groups", [])
                    if target_groups:
                        target_session = f"{platform_name}:GroupMessage:{target_groups[0]}"
                    else:
                        return JSONResponse({"error": "未配置目标群组"}, status_code=400)
                
                # 调用自定义模拟推送
                result = await self.disaster_service.simulate_custom_event(
                    session=target_session,
                    disaster_type=disaster_type,
                    test_type=test_type,
                    custom_params=custom_params
                )
                
                return {"success": "✅" in result if result else False, "message": result}
            except Exception as e:
                logger.error(f"[Web Admin] 自定义模拟推送失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.get("/api/config-schema")
        async def get_config_schema():
            """获取配置 Schema"""
            try:
                schema_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "_conf_schema.json"))
                if os.path.exists(schema_path):
                    with open(schema_path, encoding="utf-8") as f:
                        return json.load(f)
                return {"error": f"Schema file not found at: {schema_path}"}
            except Exception as e:
                logger.error(f"[Web Admin] 获取配置Schema失败: {e}, path: {schema_path}")
                import traceback
                return JSONResponse({"error": f"{str(e)}, path: {schema_path}, trace: {traceback.format_exc()}"}, status_code=500)

        @self.app.get("/api/full-config")
        async def get_full_config():
            """获取完整配置"""
            try:
                # 直接返回 Config 对象 (AstrBotConfig 实现了 dict 接口)
                return dict(self.config)
            except Exception as e:
                logger.error(f"[Web Admin] 获取完整配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        @self.app.post("/api/full-config")
        async def update_full_config(config_data: dict[str, Any]):
            """更新完整配置"""
            try:
                # 定义递归更新函数
                def deep_update(target, updates):
                    for k, v in updates.items():
                        if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                            deep_update(target[k], v)
                        else:
                            target[k] = v

                # 递归更新 Config 对象
                deep_update(self.config, config_data)
                
                # 保存配置
                # 假设 AstrBotConfig 有 save_config 方法，参考 main.py 的 usage
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
                
                return {"success": True, "message": "配置已保存"}
            except Exception as e:
                logger.error(f"[Web Admin] 保存配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        # ========== WebSocket 端点 ==========
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 端点 - 实时数据推送"""
            await websocket.accept()
            self._ws_connections.append(websocket)
            logger.info(f"[Web Admin] WebSocket 客户端已连接，当前连接数: {len(self._ws_connections)}")
            
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
                logger.debug(f"[Web Admin] WebSocket 连接异常: {e}")
            finally:
                if websocket in self._ws_connections:
                    self._ws_connections.remove(websocket)
                logger.info(f"[Web Admin] WebSocket 客户端已断开，当前连接数: {len(self._ws_connections)}")

    async def _send_full_update(self, websocket: WebSocket):
        """向单个 WebSocket 客户端发送完整数据更新"""
        try:
            data = await self._get_realtime_data()
            await websocket.send_json({
                "type": "full_update",
                "data": data
            })
        except Exception as e:
            logger.debug(f"[Web Admin] 发送数据失败: {e}")

    async def _broadcast_data(self):
        """向所有连接的客户端广播数据更新"""
        if not self._ws_connections:
            return
        
        data = await self._get_realtime_data()
        message = {
            "type": "update",
            "data": data
        }
        
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

    async def _get_realtime_data(self) -> dict:
        """获取实时数据用于 WebSocket 推送"""
        result = {
            "timestamp": datetime.now().isoformat()
        }
        
        # 状态数据
        try:
            if self.disaster_service:
                status = self.disaster_service.get_service_status()
                result["status"] = {
                    "running": status.get("running", False),
                    "uptime": status.get("uptime", "未知"),
                    "active_connections": status.get("active_websocket_connections", 0),
                    "total_connections": status.get("total_connections", 0),
                    "start_time": status.get("start_time")
                }
        except Exception as e:
            logger.debug(f"[Web Admin] 获取状态数据失败: {e}")
        
        # 统计数据
        try:
            if self.disaster_service and self.disaster_service.statistics_manager:
                stats = self.disaster_service.statistics_manager.stats
                result["statistics"] = {
                    "total_events": stats.get("total_events", 0),
                    "by_type": dict(stats.get("by_type", {})),
                    "by_source": dict(stats.get("by_source", {})),
                    "earthquake_stats": {
                        "by_magnitude": dict(stats.get("earthquake_stats", {}).get("by_magnitude", {})),
                        "max_magnitude": stats.get("earthquake_stats", {}).get("max_magnitude")
                    },
                    "recent_pushes": stats.get("recent_pushes", [])[-20:]
                }
        except Exception as e:
            logger.debug(f"[Web Admin] 获取统计数据失败: {e}")
        
        # 连接状态
        try:
            if self.disaster_service and self.disaster_service.ws_manager:
                actual_connections = self.disaster_service.ws_manager.get_all_connections_status()
                expected_sources = self._get_expected_data_sources()
                
                merged_connections = {}
                for source_name, display_name in expected_sources.items():
                    if source_name in actual_connections:
                        merged_connections[display_name] = actual_connections[source_name]
                    else:
                        merged_connections[display_name] = {
                            "connected": False,
                            "retry_count": 0,
                            "has_handler": False,
                            "status": "未连接"
                        }
                result["connections"] = merged_connections
        except Exception as e:
            logger.debug(f"[Web Admin] 获取连接状态失败: {e}")
        
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
                            "source": push.get("source", "")
                        }
                        if eq_data["latitude"] is not None and eq_data["longitude"] is not None:
                            earthquakes.append(eq_data)
                result["earthquakes"] = earthquakes
        except Exception as e:
            logger.debug(f"[Web Admin] 获取地震数据失败: {e}")
        
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
                logger.debug(f"[Web Admin] 广播循环异常: {e}")

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
            "data": data
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
            logger.debug(f"[Web Admin] 已推送新事件到 {len(self._ws_connections)} 个客户端")

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
        wolfx_sources = [
            ("japan_jma_eew", "Wolfx JMA EEW"),
            ("china_cenc_eew", "Wolfx CENC EEW"),
            ("taiwan_cwa_eew", "Wolfx CWA EEW"),
            ("japan_jma_earthquake", "Wolfx JMA Info"),
            ("china_cenc_earthquake", "Wolfx CENC Info"),
        ]
        for source_key, display_name in wolfx_sources:
            expected[f"wolfx_{source_key}"] = display_name
        
        # Global Quake
        expected["global_quake"] = "Global Quake"
        
        return expected


    async def start(self):
        """启动 Web 服务器"""
        if not FASTAPI_AVAILABLE:
            logger.error("[灾害预警] 无法启动 Web 管理端: FastAPI 未安装")
            return
        
        web_config = self.config.get("web_admin", {})
        host = web_config.get("host", "0.0.0.0")
        port = web_config.get("port", 8089)
        
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False
        )
        self.server = uvicorn.Server(config)
        
        logger.info(f"[灾害预警] Web 管理端已启动: http://{host}:{port}")
        
        # 在后台运行服务器
        self._server_task = asyncio.create_task(self.server.serve())
        
        # 启动 WebSocket 广播循环
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self):
        """停止 Web 服务器"""
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
        
        if self.server:
            self.server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
            logger.info("[灾害预警] Web 管理端已停止")
