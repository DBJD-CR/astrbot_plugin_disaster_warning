"""
灾害预警核心服务
整合所有重构的组件
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Any

from astrbot.api import logger

from ..models.models import (
    DataSource,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from .handler_registry import WebSocketHandlerRegistry
from .handlers import DATA_HANDLERS
from .message_logger import MessageLogger
from .message_manager import MessagePushManager
from .websocket_manager import HTTPDataFetcher, WebSocketManager


class DisasterWarningService:
    """灾害预警核心服务"""

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context
        self.running = False

        # 初始化消息记录器
        self.message_logger = MessageLogger(config, "disaster_warning")

        # 初始化组件
        self.ws_manager = WebSocketManager(
            config.get("websocket_config", {}), self.message_logger
        )
        self.http_fetcher: HTTPDataFetcher | None = None
        self.message_manager = MessagePushManager(config, context)

        # 数据处理器
        self.handlers = {}
        self._initialize_handlers()

        # 连接配置
        self.connections = {}
        self.connection_tasks = []

        # 定时任务
        self.scheduled_tasks = []

    def _initialize_handlers(self):
        """初始化数据处理器"""
        for source_id, handler_class in DATA_HANDLERS.items():
            self.handlers[source_id] = handler_class(self.message_logger)

    async def initialize(self):
        """初始化服务"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警服务...")

            # 初始化HTTP获取器
            self.http_fetcher = HTTPDataFetcher(self.config)

            # 注册WebSocket消息处理器
            self._register_handlers()

            # 配置连接
            self._configure_connections()

            logger.info("[灾害预警] 灾害预警服务初始化完成")

        except Exception as e:
            logger.error(f"[灾害预警] 初始化服务失败: {e}")
            raise

    def _register_handlers(self):
        """注册消息处理器"""
        registry = WebSocketHandlerRegistry(self)
        registry.register_all(self.ws_manager)

    def _configure_connections(self):
        """配置连接 - 适配数据源配置"""
        data_sources = self.config.get("data_sources", {})

        # FAN Studio连接配置
        fan_studio_config = data_sources.get("fan_studio", {})
        if isinstance(fan_studio_config, dict) and fan_studio_config.get(
            "enabled", True
        ):
            # FAN Studio 服务器地址
            # 正式服务器: wss://ws.fanstudio.tech/[路径]
            # 备用服务器: wss://ws.fanstudio.hk/[路径]
            primary_server = "wss://ws.fanstudio.tech"
            backup_server = "wss://ws.fanstudio.hk"

            # 中国地震网地震预警
            if fan_studio_config.get("china_earthquake_warning", True):
                self.connections["fan_studio_cea"] = {
                    "url": f"{primary_server}/cea",
                    "backup_url": f"{backup_server}/cea",
                    "handler": "fan_studio",
                }

            # 台湾中央气象署强震即时警报
            if fan_studio_config.get("taiwan_cwa_earthquake", True):
                self.connections["fan_studio_cwa"] = {
                    "url": f"{primary_server}/cwa",
                    "backup_url": f"{backup_server}/cwa",
                    "handler": "fan_studio",
                }

            # 中国地震台网地震测定
            if fan_studio_config.get("china_cenc_earthquake", True):
                self.connections["fan_studio_cenc"] = {
                    "url": f"{primary_server}/cenc",
                    "backup_url": f"{backup_server}/cenc",
                    "handler": "fan_studio",
                }

            # USGS地震测定
            if fan_studio_config.get("usgs_earthquake", True):
                self.connections["fan_studio_usgs"] = {
                    "url": f"{primary_server}/usgs",
                    "backup_url": f"{backup_server}/usgs",
                    "handler": "fan_studio",
                }

            # 中国气象局气象预警
            if fan_studio_config.get("china_weather_alarm", True):
                self.connections["fan_studio_weather"] = {
                    "url": f"{primary_server}/weatheralarm",
                    "backup_url": f"{backup_server}/weatheralarm",
                    "handler": "fan_studio",
                }

            # 自然资源部海啸预警
            if fan_studio_config.get("china_tsunami", True):
                self.connections["fan_studio_tsunami"] = {
                    "url": f"{primary_server}/tsunami",
                    "backup_url": f"{backup_server}/tsunami",
                    "handler": "fan_studio",
                }

            # 日本气象厅地震预警
            if fan_studio_config.get("japan_jma_eew", True):
                self.connections["fan_studio_jma"] = {
                    "url": f"{primary_server}/jma",
                    "backup_url": f"{backup_server}/jma",
                    "handler": "fan_studio",
                }

        # P2P连接配置
        p2p_config = data_sources.get("p2p_earthquake", {})
        if isinstance(p2p_config, dict) and p2p_config.get("enabled", True):
            # 检查是否有任何P2P数据源被启用
            p2p_enabled = False
            if p2p_config.get("japan_jma_eew", True):
                p2p_enabled = True
            if p2p_config.get("japan_jma_earthquake", True):
                p2p_enabled = True
            if p2p_config.get("japan_jma_tsunami", True):
                p2p_enabled = True

            if p2p_enabled:
                self.connections["p2p_main"] = {
                    "url": "wss://api.p2pquake.net/v2/ws",
                    "handler": "p2p",
                }

        # Wolfx连接配置
        wolfx_config = data_sources.get("wolfx", {})
        if isinstance(wolfx_config, dict) and wolfx_config.get("enabled", True):
            wolfx_sources = [
                ("japan_jma_eew", "wss://ws-api.wolfx.jp/jma_eew"),
                ("china_cenc_eew", "wss://ws-api.wolfx.jp/cenc_eew"),
                ("taiwan_cwa_eew", "wss://ws-api.wolfx.jp/cwa_eew"),
                ("japan_jma_earthquake", "wss://ws-api.wolfx.jp/jma_eqlist"),
                ("china_cenc_earthquake", "wss://ws-api.wolfx.jp/cenc_eqlist"),
            ]

            for source_key, url in wolfx_sources:
                if wolfx_config.get(source_key, True):
                    conn_name = f"wolfx_{source_key}"
                    self.connections[conn_name] = {"url": url, "handler": "wolfx"}

        # Global Quake连接配置 - 服务器地址硬编码，用户只需配置是否启用
        global_quake_config = data_sources.get("global_quake", {})
        if isinstance(global_quake_config, dict) and global_quake_config.get(
            "enabled", False
        ):
            # GlobalQuake Monitor 服务器地址（硬编码）
            global_quake_url = "wss://gqm.aloys233.top/ws"
            self.connections["global_quake"] = {
                "url": global_quake_url,
                "handler": "global_quake",
            }
            logger.info("[灾害预警] Global Quake 数据源已启用")

    async def start(self):
        """启动服务"""
        if self.running:
            return

        try:
            self.running = True
            logger.info("[灾害预警] 正在启动灾害预警服务...")

            # 启动WebSocket管理器
            await self.ws_manager.start()

            # 建立WebSocket连接
            await self._establish_websocket_connections()

            # 启动Global Quake连接（如果启用）
            await self._start_global_quake_connection()

            # 启动定时HTTP数据获取
            await self._start_scheduled_http_fetch()

            # 启动清理任务
            await self._start_cleanup_task()

            # 检查并提示日志记录器状态
            if self.message_logger.enabled:
                logger.info(
                    f"[灾害预警] 原始消息日志记录已启用，日志文件: {self.message_logger.log_file_path}"
                )
            else:
                logger.info(
                    "[灾害预警] 原始消息日志记录未启用。如需调试或记录原始数据，请使用命令 '/灾害预警日志开关' 启用。"
                )

            logger.info("[灾害预警] 灾害预警服务已启动")

        except Exception as e:
            logger.error(f"[灾害预警] 启动服务失败: {e}")
            self.running = False
            raise

    async def stop(self):
        """停止服务"""
        if not self.running:
            return

        try:
            self.running = False
            logger.info("[灾害预警] 正在停止灾害预警服务...")

            # 取消所有任务
            for task in self.connection_tasks:
                task.cancel()

            for task in self.scheduled_tasks:
                task.cancel()

            # 停止WebSocket管理器
            await self.ws_manager.stop()

            # 关闭HTTP获取器
            if self.http_fetcher:
                await self.http_fetcher.__aexit__(None, None, None)

            logger.info("[灾害预警] 灾害预警服务已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 停止服务时出错: {e}")

    async def _establish_websocket_connections(self):
        """建立WebSocket连接 - 使用WebSocket管理器功能"""
        for conn_name, conn_config in self.connections.items():
            if conn_config["handler"] in ["fan_studio", "p2p", "wolfx", "global_quake"]:
                # 使用WebSocket管理器功能，传递连接信息
                connection_info = {
                    "connection_name": conn_name,
                    "handler_type": conn_config["handler"],
                    "data_source": self._get_data_source_from_connection(conn_name),
                    "established_time": None,
                    "backup_url": conn_config.get("backup_url"),  # 传递备用服务器URL
                }

                task = asyncio.create_task(
                    self.ws_manager.connect(
                        name=conn_name,
                        uri=conn_config["url"],
                        connection_info=connection_info,
                    )
                )
                self.connection_tasks.append(task)

                # 日志中显示备用服务器信息
                backup_info = (
                    f", 备用: {conn_config.get('backup_url')}"
                    if conn_config.get("backup_url")
                    else ""
                )
                logger.info(
                    f"[灾害预警] 已启动WebSocket连接任务: {conn_name} (数据源: {connection_info['data_source']}{backup_info})"
                )

    def _get_data_source_from_connection(self, connection_name: str) -> str:
        """从连接名称获取数据源ID"""
        # 连接名称到数据源ID的映射
        connection_mapping = {
            # FAN Studio
            "fan_studio_cea": "cea_fanstudio",
            "fan_studio_cwa": "cwa_fanstudio",
            "fan_studio_cenc": "cenc_fanstudio",
            "fan_studio_usgs": "usgs_fanstudio",
            "fan_studio_jma": "jma_fanstudio",
            "fan_studio_weather": "china_weather_fanstudio",
            "fan_studio_tsunami": "china_tsunami_fanstudio",
            # P2P
            "p2p_main": "jma_p2p",
            # Wolfx
            "wolfx_japan_jma_eew": "jma_wolfx",
            "wolfx_china_cenc_eew": "cea_wolfx",
            "wolfx_taiwan_cwa_eew": "cwa_wolfx",
            "wolfx_china_cenc_earthquake": "cenc_wolfx",
            "wolfx_japan_jma_earthquake": "jma_wolfx_info",
        }

        return connection_mapping.get(connection_name, "unknown")

    async def _start_global_quake_connection(self):
        """启动Global Quake WebSocket连接 - 现已整合到 WebSocketManager，此方法保留仅用于日志"""
        # Global Quake 现在通过 _configure_connections 和 _establish_websocket_connections 统一管理
        # 此方法保留以保持向后兼容，但不再执行任何操作
        global_quake_config = self.config.get("data_sources", {}).get(
            "global_quake", {}
        )
        if isinstance(global_quake_config, dict) and global_quake_config.get(
            "enabled", False
        ):
            if "global_quake" in self.connections:
                logger.debug("[灾害预警] Global Quake 已通过 WebSocketManager 统一管理")

    async def _start_scheduled_http_fetch(self):
        """启动定时HTTP数据获取"""

        async def fetch_wolfx_data():
            while self.running:
                try:
                    await asyncio.sleep(300)  # 5分钟获取一次

                    async with self.http_fetcher as fetcher:
                        # 获取中国地震台网地震列表
                        cenc_data = await fetcher.fetch_json(
                            "https://api.wolfx.jp/cenc_eqlist.json"
                        )
                        if cenc_data:
                            # 记录原始HTTP响应数据
                            if self.message_logger:
                                try:
                                    self.message_logger.log_raw_message(
                                        source="http_wolfx_cenc",
                                        message_type="http_response",
                                        raw_data=json.dumps(cenc_data),
                                        connection_info={
                                            "url": "https://api.wolfx.jp/cenc_eqlist.json",
                                            "method": "GET",
                                            "data_source": "wolfx_cenc_earthquake",
                                        },
                                    )
                                except Exception as log_e:
                                    logger.warning(
                                        f"[灾害预警] HTTP响应记录失败: {log_e}"
                                    )

                            # 使用新处理器
                            handler = self.handlers.get("cenc_wolfx")
                            if handler:
                                event = handler.parse_message(json.dumps(cenc_data))
                                if event:
                                    await self._handle_disaster_event(event)

                        # 获取日本气象厅地震列表
                        jma_data = await fetcher.fetch_json(
                            "https://api.wolfx.jp/jma_eqlist.json"
                        )
                        if jma_data:
                            # 记录原始HTTP响应数据
                            if self.message_logger:
                                try:
                                    self.message_logger.log_raw_message(
                                        source="http_wolfx_jma",
                                        message_type="http_response",
                                        raw_data=json.dumps(jma_data),
                                        connection_info={
                                            "url": "https://api.wolfx.jp/jma_eqlist.json",
                                            "method": "GET",
                                            "data_source": "wolfx_jma_earthquake",
                                        },
                                    )
                                except Exception as log_e:
                                    logger.warning(
                                        f"[灾害预警] HTTP响应记录失败: {log_e}"
                                    )

                            # 使用新处理器
                            handler = self.handlers.get("jma_wolfx_info")
                            if handler:
                                event = handler.parse_message(json.dumps(jma_data))
                                if event:
                                    await self._handle_disaster_event(event)

                except Exception as e:
                    logger.error(f"[灾害预警] 定时HTTP数据获取失败: {e}")

        task = asyncio.create_task(fetch_wolfx_data())
        self.scheduled_tasks.append(task)

    async def _start_cleanup_task(self):
        """启动清理任务"""

        async def cleanup():
            while self.running:
                try:
                    await asyncio.sleep(86400)  # 每天清理一次
                    self.message_manager.cleanup_old_records()
                except Exception as e:
                    logger.error(f"[灾害预警] 清理任务失败: {e}")

        task = asyncio.create_task(cleanup())
        self.scheduled_tasks.append(task)

    async def _handle_disaster_event(self, event: DisasterEvent):
        """处理灾害事件"""
        try:
            logger.debug(f"[灾害预警] 处理灾害事件: {event.id}")
            self._log_event(event)

            # 推送消息 - 使用新消息管理器
            push_result = await self.message_manager.push_event(event)
            if push_result:
                logger.debug(f"[灾害预警] ✅ 事件推送成功: {event.id}")
            else:
                logger.debug(f"[灾害预警] 事件推送被过滤: {event.id}")

        except Exception as e:
            logger.error(f"[灾害预警] 处理灾害事件失败: {e}")
            logger.error(
                f"[灾害预警] 失败的事件ID: {event.id if hasattr(event, 'id') else 'unknown'}"
            )
            logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def _log_event(self, event: DisasterEvent):
        """记录事件日志"""
        try:
            if isinstance(event.data, EarthquakeData):
                earthquake = event.data
                log_info = f"地震事件 - 震级: M{earthquake.magnitude}, 位置: {earthquake.place_name}, 时间: {earthquake.shock_time}, 数据源: {event.source.value}"
            elif isinstance(event.data, TsunamiData):
                tsunami = event.data
                log_info = f"海啸事件 - 级别: {tsunami.level}, 标题: {tsunami.title}, 数据源: {event.source.value}"
            elif isinstance(event.data, WeatherAlarmData):
                weather = event.data
                log_info = (
                    f"气象事件 - 标题: {weather.headline}, 数据源: {event.source.value}"
                )
            else:
                log_info = (
                    f"未知事件类型 - ID: {event.id}, 数据源: {event.source.value}"
                )

            logger.debug(f"[灾害预警] 事件详情: {log_info}")
        except Exception:
            logger.debug(
                f"[灾害预警] 事件详情: ID={event.id}, 类型={event.disaster_type.value}, 数据源={event.source.value}"
            )

    def get_service_status(self) -> dict[str, Any]:
        """获取服务状态 - 增强版本"""
        # 获取WebSocket连接状态
        connection_status = self.ws_manager.get_all_connections_status()

        # 统计活跃连接
        active_websocket_connections = sum(
            1 for status in connection_status.values() if status["connected"]
        )

        # 统计Global Quake连接（如果有的话）
        global_quake_connected = any(
            "global_quake" in task.get_name() if hasattr(task, "get_name") else False
            for task in self.connection_tasks
        )

        return {
            "running": self.running,
            "active_websocket_connections": active_websocket_connections,
            "global_quake_connected": global_quake_connected,
            "total_connections": len(connection_status),
            "connection_details": connection_status,
            "push_stats": self.message_manager.get_push_stats(),
            "data_sources": self._get_active_data_sources(),
            "message_logger_enabled": self.message_logger.enabled
            if self.message_logger
            else False,
        }

    def _get_active_data_sources(self) -> list[str]:
        """获取活跃的数据源"""
        active_sources = []
        data_sources = self.config.get("data_sources", {})

        # 遍历配置结构，收集启用的数据源
        for service_name, service_config in data_sources.items():
            if isinstance(service_config, dict) and service_config.get(
                "enabled", False
            ):
                # 收集该服务下启用的具体数据源
                for source_name, enabled in service_config.items():
                    if (
                        source_name != "enabled"
                        and isinstance(enabled, bool)
                        and enabled
                    ):
                        active_sources.append(f"{service_name}.{source_name}")

        return active_sources

    async def test_push(
        self, session: str, disaster_type: str = "earthquake", test_type: str = None
    ):
        """测试推送功能 - 预设符合实际消息格式化器的数据格式"""
        try:
            # 预设测试配置，对应不同的消息格式化器
            test_configs = {
                "earthquake": {
                    "china_eew": {  # 中国地震预警网格式
                        "source_id": "cea_fanstudio",
                        "magnitude": 5.5,
                        "depth": 10.0,
                        "intensity": 6.0,
                        "place_name": "测试地名",
                        "latitude": 31.2,
                        "longitude": 103.8,
                        "updates": 1,
                        "is_final": False,
                    },
                    "japan_eew": {  # 日本紧急地震速报格式
                        "source_id": "jma_wolfx",
                        "magnitude": 6.2,
                        "depth": 35.0,
                        "scale": 5.0,  # 震度
                        "place_name": "测试地名",
                        "latitude": 37.5,
                        "longitude": 141.8,
                        "updates": 2,
                        "is_final": False,
                        "raw_data": {
                            "areas": [
                                {
                                    "name": "测试区域1",
                                    "scaleFrom": 50,
                                    "kindCode": "10",
                                },  # 震度5强，未到达
                                {
                                    "name": "测试区域2",
                                    "scaleFrom": 45,
                                    "kindCode": "11",
                                },  # 震度5弱，已到达
                            ]
                        },
                    },
                    "usgs_info": {  # USGS地震情报格式
                        "source_id": "usgs_fanstudio",
                        "magnitude": 4.8,
                        "depth": 15.5,
                        "place_name": "测试地名",
                        "latitude": 34.1,
                        "longitude": -118.2,
                        "info_type": "automatic",
                    },
                },
                "tsunami": {
                    "china_tsunami": {  # 中国海啸预警格式
                        "source_id": "china_tsunami_fanstudio",
                        "title": "海啸黄色警报",
                        "level": "Warning",
                        "org_unit": "自然资源部海啸预警中心",
                        "forecasts": [
                            {
                                "name": "测试海域",
                                "grade": "Warning",
                                "immediate": True,
                                "estimatedArrivalTime": "12:30",
                                "maxWaveHeight": "50cm",
                            }
                        ],
                        "subtitle": "测试地点附近海域发生地震",
                    },
                    "japan_tsunami": {  # 日本海啸预警格式 - 基于P2P实际数据结构
                        "source_id": "jma_tsunami_p2p",
                        "title": "津波注意報",
                        "level": "Watch",  # P2P使用Watch/Warning/MajorWarning
                        "org_unit": "日本气象厅",
                        "forecasts": [
                            {
                                "name": "测试地点 1",
                                "grade": "Watch",  # P2P实际使用Watch/Warning/MajorWarning
                                "immediate": False,
                                "firstHeight": {
                                    "arrivalTime": "2023-12-12T13:15:00",
                                    "condition": "津波到達中と推測",
                                },
                                "maxHeight": {"description": "１ｍ", "value": 1},
                            },
                            {
                                "name": "测试地点 2",
                                "grade": "Watch",
                                "immediate": False,
                                "firstHeight": {"arrivalTime": "2023-12-12T13:25:00"},
                                "maxHeight": {"description": "０．５ｍ", "value": 0.5},
                            },
                        ],
                        "subtitle": "三陸沖を震源とする地震により、津波注意報が発表されています。",
                        "cancelled": False,  # 添加取消状态
                        "issue": {
                            "source": "日本气象厅",
                            "time": "2023-12-12T12:30:00",
                            "type": "Focus",
                        },
                    },
                },
                "weather": {
                    "china_weather": {  # 中国气象预警格式
                        "source_id": "china_weather_fanstudio",
                        "headline": "大风黄色预警信号",
                        "title": "大风黄色预警信号",
                        "description": "气象台发布大风黄色预警信号：预计今天夜间到明天白天，沿岸海域将有西南风6～7级，阵风8～9级。",
                        "type": "wind",
                        "effective_time": datetime.now(),
                        "longitude": 116.0,
                        "latitude": 39.0,
                    }
                },
            }

            # 根据灾害类型和测试类型选择配置
            if disaster_type == "earthquake":
                if test_type == "china" or test_type is None:
                    test_config = test_configs["earthquake"]["china_eew"]
                elif test_type == "japan":
                    test_config = test_configs["earthquake"]["japan_eew"]
                elif test_type == "usgs":
                    test_config = test_configs["earthquake"]["usgs_info"]
                else:
                    test_config = test_configs["earthquake"]["china_eew"]  # 默认

            elif disaster_type == "tsunami":
                if test_type == "japan" or test_type is None:
                    test_config = test_configs["tsunami"]["japan_tsunami"]
                elif test_type == "china":
                    test_config = test_configs["tsunami"]["china_tsunami"]
                else:
                    test_config = test_configs["tsunami"]["japan_tsunami"]  # 默认

            elif disaster_type == "weather":
                test_config = test_configs["weather"][
                    "china_weather"
                ]  # 气象只有一种格式

            else:
                # 默认使用地震配置
                test_config = test_configs["earthquake"]["china_eew"]

            # 创建测试事件
            test_event = self._create_simple_test_event(disaster_type, test_config)

            logger.info(
                f"[灾害预警] 创建测试事件: {test_event.id} (类型: {disaster_type}, 配置: {test_config['source_id']})"
            )

            # 注入本地预估信息（模拟真实推送流程）
            if (
                disaster_type == "earthquake"
                and self.message_manager.local_monitor.enabled
            ):
                earthquake = test_event.data
                _, distance, intensity = self.message_manager.local_monitor.check_event(
                    earthquake
                )
                test_event.raw_data["local_estimation"] = {
                    "distance": distance,
                    "intensity": intensity,
                }

            # 直接构建消息并推送（绕过复杂的过滤逻辑，仅测试消息链路）
            message = self.message_manager._build_message(test_event)
            await self.message_manager._send_message(session, message)

            logger.info(f"[灾害预警] 测试推送成功: {test_event.id}")

            # 返回简洁的成功信息
            source_name = self._get_source_display_name(test_config["source_id"])
            return f"✅ 测试推送成功\n📡 数据源: {source_name}\n🎯 消息链路畅通"

        except Exception as e:
            logger.error(f"[灾害预警] 测试推送失败: {e}")
            return f"❌ 测试推送失败: {str(e)}"

    def _create_simple_test_event(
        self, disaster_type: str, test_config: dict
    ) -> "DisasterEvent":
        """创建简化的测试事件"""
        # 使用顶部导入的类，无需在此处重新导入

        source_id = test_config["source_id"]

        # 获取数据源枚举值
        source_enum_mapping = {
            "cea_fanstudio": DataSource.FAN_STUDIO_CEA,
            "jma_wolfx": DataSource.WOLFX_JMA_EEW,
            "usgs_fanstudio": DataSource.FAN_STUDIO_USGS,
            "china_tsunami_fanstudio": DataSource.FAN_STUDIO_TSUNAMI,
            "jma_tsunami_p2p": DataSource.P2P_TSUNAMI,
            "china_weather_fanstudio": DataSource.FAN_STUDIO_WEATHER,
        }
        source_enum = source_enum_mapping.get(source_id, DataSource.FAN_STUDIO_CEA)

        if disaster_type == "earthquake":
            # 创建地震测试数据
            test_data = EarthquakeData(
                id=f"test_{source_id}_{int(datetime.now().timestamp())}",
                event_id=f"test_event_{source_id}",
                source=source_enum,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=datetime.now(),
                latitude=test_config.get("latitude", 35.0),
                longitude=test_config.get("longitude", 105.0),
                magnitude=test_config.get("magnitude", 5.5),
                depth=test_config.get("depth", 10.0),
                intensity=test_config.get("intensity"),
                scale=test_config.get("scale"),
                place_name=test_config.get("place_name", "测试地震地点"),
                raw_data={
                    **{"test": True, "source_id": source_id},
                    **test_config.get("raw_data", {}),
                },
                info_type=test_config.get("info_type"),
                updates=test_config.get("updates", 1),
                is_final=test_config.get("is_final", False),
            )
            disaster_type_enum = DisasterType.EARTHQUAKE

        elif disaster_type == "tsunami":
            # 创建海啸测试数据
            test_data = TsunamiData(
                id=f"test_{source_id}_{int(datetime.now().timestamp())}",
                code=f"test_tsunami_{source_id}",
                source=source_enum,
                title=test_config.get("title", "海啸警报测试"),
                level=test_config.get("level", "Warning"),
                org_unit=test_config.get("org_unit", "测试海啸预警中心"),
                forecasts=test_config.get("forecasts", []),
                raw_data={
                    **{"test": True, "source_id": source_id},
                    **test_config.get("raw_data", {}),
                },
                issue_time=datetime.now(),
                subtitle=test_config.get("subtitle", "测试震源信息"),
            )
            disaster_type_enum = DisasterType.TSUNAMI

        elif disaster_type == "weather":
            # 创建气象预警测试数据
            test_data = WeatherAlarmData(
                id=f"test_{source_id}_{int(datetime.now().timestamp())}",
                source=source_enum,
                headline=test_config.get("headline", "气象预警测试"),
                title=test_config.get("title", "测试预警"),
                description=test_config.get("description", "测试描述"),
                type=test_config.get("type", "unknown"),
                effective_time=test_config.get("effective_time", datetime.now()),
                longitude=test_config.get("longitude", 116.0),
                latitude=test_config.get("latitude", 39.0),
                raw_data={
                    **{"test": True, "source_id": source_id},
                    **test_config.get("raw_data", {}),
                },
                issue_time=datetime.now(),
            )
            disaster_type_enum = DisasterType.WEATHER_ALARM

        else:
            # 默认创建地震数据
            return self._create_simple_test_event("earthquake", test_config)

        return DisasterEvent(
            id=test_data.id,
            data=test_data,
            source=test_data.source,
            disaster_type=disaster_type_enum,
        )

    def _get_source_display_name(self, source_id: str) -> str:
        """获取数据源显示名称"""
        from ..models.data_source_config import get_data_source_config

        config = get_data_source_config(source_id)
        if config:
            return config.display_name
        return source_id


# 服务实例
_disaster_service: DisasterWarningService | None = None


async def get_disaster_service(
    config: dict[str, Any], context
) -> DisasterWarningService:
    """获取灾害预警服务实例"""
    global _disaster_service

    if _disaster_service is None:
        _disaster_service = DisasterWarningService(config, context)
        await _disaster_service.initialize()

    return _disaster_service


async def stop_disaster_service():
    """停止灾害预警服务"""
    global _disaster_service

    if _disaster_service:
        await _disaster_service.stop()
        _disaster_service = None
