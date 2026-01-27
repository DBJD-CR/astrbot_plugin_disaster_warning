"""
灾害预警核心服务
整合所有重构的组件
"""

import asyncio
import json
import os
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from astrbot.api import logger
from astrbot.api.star import StarTools

if TYPE_CHECKING:
    from .telemetry_manager import TelemetryManager

from ..models.models import (
    DisasterEvent,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from .handler_registry import WebSocketHandlerRegistry
from .handlers import DATA_HANDLERS
from .message_logger import MessageLogger
from .message_manager import MessagePushManager
from .statistics_manager import StatisticsManager
from .websocket_manager import HTTPDataFetcher, WebSocketManager


class DisasterWarningService:
    """灾害预警核心服务"""

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context
        self.running = False
        self._start_lock = asyncio.Lock()  # 防止并发启动的锁

        # 初始化消息记录器
        self.message_logger = MessageLogger(config, "disaster_warning")

        # 初始化统计管理器
        self.statistics_manager = StatisticsManager()

        # 遥测管理器引用 (由 main.py 注入)
        self._telemetry: TelemetryManager | None = None

        # 初始化组件（传入 telemetry，但此时可能为 None）
        self.ws_manager = WebSocketManager(
            config.get("websocket_config", {}), self.message_logger, telemetry=self._telemetry
        )
        self.http_fetcher: HTTPDataFetcher | None = None
        
        # 初始化消息管理器
        self.message_manager = MessagePushManager(config, context, telemetry=self._telemetry)

        # 数据处理器
        self.handlers = {}
        self._initialize_handlers()

        # 连接配置
        self.connections = {}
        self.connection_tasks = []

        # 定时任务
        self.scheduled_tasks = []

        # 地震列表缓存（用于查询指令）
        self.earthquake_lists = {"cenc": {}, "jma": {}}

        # 数据持久化路径
        self.storage_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.cache_file = os.path.join(self.storage_dir, "earthquake_lists_cache.json")

    def _initialize_handlers(self):
        """初始化数据处理器"""
        for source_id, handler_class in DATA_HANDLERS.items():
            self.handlers[source_id] = handler_class(self.message_logger)

    def set_telemetry(self, telemetry: Optional["TelemetryManager"]):
        """设置遥测管理器引用"""
        self._telemetry = telemetry
        # 同时更新子组件的遥测引用
        if self.ws_manager:
            self.ws_manager._telemetry = telemetry
        if self.message_manager:
            self.message_manager._telemetry = telemetry
            if self.message_manager.browser_manager:
                self.message_manager.browser_manager._telemetry = telemetry

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
            # 上报初始化失败错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(e, module="core.disaster_service.initialize")
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

            # 检查是否启用了至少一个 FAN Studio 子数据源
            fan_sub_sources = [
                "china_earthquake_warning",
                "taiwan_cwa_earthquake",
                "china_cenc_earthquake",
                "usgs_earthquake",
                "china_weather_alarm",
                "china_tsunami",
                "japan_jma_eew",
            ]

            any_fan_source_enabled = any(
                fan_studio_config.get(source, True) for source in fan_sub_sources
            )

            if any_fan_source_enabled:
                # 使用 /all 路径建立单一连接
                self.connections["fan_studio_all"] = {
                    "url": f"{primary_server}/all",
                    "backup_url": f"{backup_server}/all",
                    "handler": "fan_studio",
                }
                logger.info("[灾害预警] 已配置 FAN Studio 全量数据连接 (/all)")

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
            wolfx_sub_sources = [
                "japan_jma_eew",
                "china_cenc_eew",
                "taiwan_cwa_eew",
                "japan_jma_earthquake",
                "china_cenc_earthquake",
            ]

            any_wolfx_source_enabled = any(
                wolfx_config.get(source, True) for source in wolfx_sub_sources
            )

            if any_wolfx_source_enabled:
                # 使用 /all_eew 路径建立单一连接
                self.connections["wolfx_all"] = {
                    "url": "wss://ws-api.wolfx.jp/all_eew",
                    "handler": "wolfx",
                }
                logger.info("[灾害预警] 已配置 Wolfx 全量数据连接 (/all_eew)")

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
        # 使用锁防止并发启动导致的重复连接
        async with self._start_lock:
            if self.running:
                logger.debug("[灾害预警] 服务已在运行中，跳过重复启动")
                return

            try:
                self.running = True
                self.start_time = datetime.now(timezone.utc)  # 记录启动时间
                logger.info("[灾害预警] 正在启动灾害预警服务...")

                # 加载缓存数据
                self._load_earthquake_lists_cache()

                # 启动WebSocket管理器
                await self.ws_manager.start()

                # 建立WebSocket连接
                await self._establish_websocket_connections()

                # 启动定时HTTP数据获取
                await self._start_scheduled_http_fetch()

                # 启动清理任务
                await self._start_cleanup_task()

                # 检查并提示日志记录器状态
                if self.message_logger.enabled:
                    logger.debug(
                        f"[灾害预警] 原始消息日志记录已启用，日志文件: {self.message_logger.log_file_path}"
                    )
                else:
                    logger.debug(
                        "[灾害预警] 原始消息日志记录未启用。如需调试或记录原始数据，请使用命令 '/灾害预警日志开关' 启用。"
                    )

                logger.info("[灾害预警] 灾害预警服务已启动")

            except Exception as e:
                logger.error(f"[灾害预警] 启动服务失败: {e}")
                self.running = False
                # 上报启动失败错误到遥测
                if self._telemetry and self._telemetry.enabled:
                    await self._telemetry.track_error(e, module="core.disaster_service.start")
                raise

    async def stop(self):
        """停止服务"""
        if not self.running:
            return

        try:
            # 保存缓存数据
            self._save_earthquake_lists_cache()

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
                await self.http_fetcher.close()  # 修改点：调用显式的 close()

            logger.info("[灾害预警] 灾害预警服务已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 停止服务时出错: {e}")
            # 上报停止服务错误到遥测
            if self._telemetry and self._telemetry.enabled:
                await self._telemetry.track_error(e, module="core.disaster_service.stop")

    async def _establish_websocket_connections(self):
        """建立WebSocket连接 - 使用WebSocket管理器功能"""
        logger.debug(f"[灾害预警] 开始建立WebSocket连接，当前任务数: {len(self.connection_tasks)}")
        
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
                logger.debug(
                    f"[灾害预警] 已启动WebSocket连接任务: {conn_name} (数据源: {connection_info['data_source']}{backup_info})"
                )
        
        logger.debug(f"[灾害预警] WebSocket连接建立完成，总任务数: {len(self.connection_tasks)}")

    def _get_data_source_from_connection(self, connection_name: str) -> str:
        """从连接名称获取数据源ID"""
        # 连接名称到数据源ID的映射
        connection_mapping = {
            # FAN Studio
            "fan_studio_all": "fan_studio_mixed",  # 混合数据源
            # P2P
            "p2p_main": "jma_p2p",
            # Wolfx
            "wolfx_all": "wolfx_mixed",  # 混合数据源
            # Global Quake
            "global_quake": "global_quake",
        }

        return connection_mapping.get(connection_name, "unknown")

    def is_fan_studio_source_enabled(self, source_key: str) -> bool:
        """检查特定的 FAN Studio 数据源是否启用"""
        data_sources = self.config.get("data_sources", {})
        fan_studio_config = data_sources.get("fan_studio", {})

        if not isinstance(fan_studio_config, dict) or not fan_studio_config.get(
            "enabled", True
        ):
            return False

        return fan_studio_config.get(source_key, True)

    def is_wolfx_source_enabled(self, source_key: str) -> bool:
        """检查特定的 Wolfx 数据源是否启用"""
        data_sources = self.config.get("data_sources", {})
        wolfx_config = data_sources.get("wolfx", {})

        if not isinstance(wolfx_config, dict) or not wolfx_config.get("enabled", True):
            return False

        return wolfx_config.get(source_key, True)

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
                            # HTTP 获取的数据不再写入日志，避免冗余

                            # 更新缓存
                            self.update_earthquake_list("cenc", cenc_data)

                            # 仅在启用该数据源时才解析并尝试推送
                            if self.is_wolfx_source_enabled("china_cenc_earthquake"):
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
                            # HTTP 获取的数据不再写入日志，避免冗余

                            # 更新缓存
                            self.update_earthquake_list("jma", jma_data)

                            # 仅在启用该数据源时才解析并尝试推送
                            if self.is_wolfx_source_enabled("japan_jma_earthquake"):
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

    def update_earthquake_list(self, list_type: str, data: dict[str, Any]):
        """更新内存中的地震列表"""
        if list_type in self.earthquake_lists:
            self.earthquake_lists[list_type] = data
            logger.debug(f"[灾害预警] 已更新 {list_type} 地震列表缓存")

    def _load_earthquake_lists_cache(self):
        """从文件加载地震列表缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "cenc" in data and "jma" in data:
                        self.earthquake_lists = data
                        logger.debug("[灾害预警] 已恢复 Wolfx 地震列表本地缓存")
            else:
                logger.debug("[灾害预警] 本地缓存文件不存在，将使用空的 Wolfx 地震列表")
        except Exception as e:
            logger.warning(f"[灾害预警] 加载 Wolfx 地震列表缓存失败: {e}")

    def _save_earthquake_lists_cache(self):
        """保存地震列表缓存到文件"""
        try:
            if not os.path.exists(self.storage_dir):
                os.makedirs(self.storage_dir, exist_ok=True)

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.earthquake_lists, f, ensure_ascii=False)
            logger.info("[灾害预警] Wolfx 地震列表缓存已保存")
        except Exception as e:
            logger.error(f"[灾害预警] 保存 Wolfx 地震列表缓存失败: {e}")

    def get_formatted_list_data(self, source_type: str, count: int) -> list[dict]:
        """获取格式化后的地震列表数据（用于卡片渲染）"""
        data = self.earthquake_lists.get(source_type, {})
        if not data:
            return []

        # 排序 keys: No1, No2...
        sorted_keys = sorted(
            [k for k in data.keys() if k.startswith("No")],
            key=lambda x: int(x[2:]) if x[2:].isdigit() else 999,
        )

        result = []
        for key in sorted_keys[:count]:
            item = data[key]
            formatted_item = self._format_list_item(source_type, item)
            if formatted_item:
                result.append(formatted_item)

        return result

    def _format_list_item(self, source_type: str, item: dict) -> dict | None:
        """格式化单个列表项"""
        try:
            location = item.get("location", "未知地点")
            time_str = item.get("time", "")
            magnitude = item.get("magnitude", "0.0")
            depth = item.get("depth", "0")

            # 统一深度格式
            if isinstance(depth, (int, float)):
                depth = f"{depth}km"
            elif isinstance(depth, str) and not depth.endswith("km"):
                depth = f"{depth}km"

            intensity_display = "-"
            intensity_class = "int-unknown"

            if source_type == "cenc":
                # CENC 使用 intensity (烈度) 或 magnitude (震级) 估算
                # Wolfx CENC 列表通常包含 intensity 字段，如果没有则用震级估算
                intensity = item.get("intensity")
                if intensity is None or intensity == "":
                    # 简单的震级到烈度映射估算 (仅用于显示颜色)
                    try:
                        mag_val = float(magnitude)
                        if mag_val < 3:
                            intensity = "1"
                        elif mag_val < 5:
                            intensity = "3"
                        elif mag_val < 6:
                            intensity = "5"
                        elif mag_val < 7:
                            intensity = "7"
                        elif mag_val < 8:
                            intensity = "9"
                        else:
                            intensity = "11"
                    except Exception:
                        intensity = "0"

                intensity_display = str(intensity)

                # 映射颜色类
                try:
                    int_val = float(intensity)
                    if int_val < 3:
                        intensity_class = "int-1"
                    elif int_val < 5:
                        intensity_class = "int-2"
                    elif int_val < 6:
                        intensity_class = "int-3"
                    elif int_val < 7:
                        intensity_class = "int-4"
                    elif int_val < 8:
                        intensity_class = "int-5-weak"
                    elif int_val < 9:
                        intensity_class = "int-5-strong"
                    elif int_val < 10:
                        intensity_class = "int-6-weak"
                    elif int_val < 11:
                        intensity_class = "int-6-strong"
                    else:
                        intensity_class = "int-7"
                except Exception:
                    pass

            elif source_type == "jma":
                # JMA 使用 shindo (震度)
                shindo = str(item.get("shindo", ""))
                intensity_display = shindo

                # 映射颜色类
                if shindo == "1":
                    intensity_class = "int-1"
                elif shindo == "2":
                    intensity_class = "int-2"
                elif shindo == "3":
                    intensity_class = "int-3"
                elif shindo == "4":
                    intensity_class = "int-4"
                elif shindo in ["5-", "5弱"]:
                    intensity_class = "int-5-weak"
                elif shindo in ["5+", "5強", "5强"]:
                    intensity_class = "int-5-strong"
                elif shindo in ["6-", "6弱"]:
                    intensity_class = "int-6-weak"
                elif shindo in ["6+", "6強", "6强"]:
                    intensity_class = "int-6-strong"
                elif shindo == "7":
                    intensity_class = "int-7"

            return {
                "location": location,
                "time": time_str,
                "magnitude": magnitude,
                "depth": depth,
                "intensity_display": intensity_display,
                "intensity_class": intensity_class,
                "raw": item,  # 保留原始数据用于文本模式
            }

        except Exception as e:
            logger.error(f"[灾害预警] 格式化列表项失败: {e}")
            return None

    def is_in_silence_period(self) -> bool:
        """检查是否处于启动后的静默期"""
        if not hasattr(self, "start_time"):
            return False

        debug_config = self.config.get("debug_config", {})
        silence_duration = debug_config.get("startup_silence_duration", 0)

        if silence_duration <= 0:
            return False

        elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return elapsed < silence_duration

    async def _handle_disaster_event(self, event: DisasterEvent):
        """处理灾害事件"""
        # 检查静默期
        if self.is_in_silence_period():
            debug_config = self.config.get("debug_config", {})
            silence_duration = debug_config.get("startup_silence_duration", 0)
            elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            logger.debug(
                f"[灾害预警] 处于启动静默期 (剩余 {silence_duration - elapsed:.1f}s)，忽略事件: {event.id}"
            )
            # 静默期内不记录统计数据，直接返回
            return

        try:
            logger.debug(f"[灾害预警] 处理灾害事件: {event.id}")
            self._log_event(event)

            # 记录统计数据 (不管是否推送成功)
            self.statistics_manager.record_push(event)

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
            # 遥测: 记录错误（包含堆栈，便于诊断，同时由 _sanitize_stack 处理隐私）
            if self._telemetry and self._telemetry.enabled:
                asyncio.create_task(
                    self._telemetry.track_error(
                        exception=e,
                        module="disaster_service._handle_disaster_event",
                    )
                )

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

        # 统计Global Quake连接
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
            "statistics_summary": self.statistics_manager.get_summary(),
            "data_sources": self._get_active_data_sources(),
            "message_logger_enabled": self.message_logger.enabled
            if self.message_logger
            else False,
            "uptime": self._get_uptime(),  # 添加运行时间
        }

    def _get_uptime(self) -> str:
        """获取服务运行时间"""
        if not self.running or not hasattr(self, "start_time"):
            return "未运行"

        delta = datetime.now(timezone.utc) - self.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分")
        parts.append(f"{seconds}秒")

        return "".join(parts)

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
