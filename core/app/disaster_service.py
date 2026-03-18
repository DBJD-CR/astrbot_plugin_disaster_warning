"""
灾害预警核心服务
整合所有重构的组件
"""

import asyncio
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from astrbot.api import logger
from astrbot.api.star import StarTools

if TYPE_CHECKING:
    from ..support.telemetry_manager import TelemetryManager

from ...models.data_source_config import (
    DATA_SOURCE_CONFIGS,
    is_source_enabled_in_data_sources,
)
from ...models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    TsunamiData,
    WeatherAlarmData,
)
from ...utils.fe_regions import load_data_async
from ...utils.formatters import MESSAGE_FORMATTERS
from ...utils.time_converter import TimeConverter
from ..handlers import DATA_HANDLERS
from ..message.message_logger import MessageLogger
from ..message.message_manager import MessagePushManager
from ..network.handler_registry import WebSocketHandlerRegistry
from ..network.websocket_manager import HTTPDataFetcher, WebSocketManager
from ..storage.session_config_manager import SessionConfigManager
from ..storage.statistics_manager import StatisticsManager


class DisasterWarningService:
    """灾害预警核心服务"""

    EEW_VALID_DURATION_SECONDS = 300

    # 机构级归一化配置：同机构不同数据源共享状态与重置逻辑
    _EEW_QUERY_INSTITUTIONS: dict[str, dict[str, Any]] = {
        "china": {
            "display_name": "中国地震预警网 EEW",
            "active_name": "中国地震预警网",
            "source_ids": ["cea_fanstudio", "cea_pr_fanstudio", "cea_wolfx"],
        },
        "japan": {
            "display_name": "日本気象庁 EEW",
            "active_name": "日本気象庁",
            "source_ids": ["jma_fanstudio", "jma_p2p", "jma_wolfx"],
        },
        "taiwan": {
            "display_name": "中央氣象署 EEW",
            "active_name": "中央氣象署",
            "source_ids": ["cwa_fanstudio", "cwa_wolfx"],
        },
    }

    def __init__(self, config: dict[str, Any], context):
        self.config = config
        self.context = context
        self.running = False
        self._start_lock = asyncio.Lock()  # 防止并发启动的锁
        self._stop_lock = asyncio.Lock()  # 防止并发停止导致的竞态
        self._stopping = False

        # 初始化消息记录器
        self.message_logger = MessageLogger(config, "disaster_warning")

        # 初始化统计管理器
        self.statistics_manager = StatisticsManager(config)

        # 遥测管理器引用 (由 main.py 注入)
        self._telemetry: TelemetryManager | None = None

        # 会话差异配置管理器
        self.session_config_manager = SessionConfigManager(config)

        # 初始化组件（传入 telemetry，但此时可能为 None）
        self.ws_manager = WebSocketManager(
            config.get("websocket_config", {}),
            self.message_logger,
            telemetry=self._telemetry,
        )
        self.http_fetcher: HTTPDataFetcher | None = None

        # 初始化消息管理器
        self.message_manager = MessagePushManager(
            config, context, telemetry=self._telemetry
        )
        # 消息限流 (数据源离线通知)
        self._offline_notification_state: dict[str, dict[str, float]] = {}

        # 数据处理器
        self.handlers = {}
        self._initialize_handlers()

        # 连接配置
        self.connections = {}
        self.connection_tasks = []

        # 定时任务
        self.scheduled_tasks = []

        # 服务级后台任务托管（用于统一回收由处理器派发的异步任务）
        self.background_tasks: set[asyncio.Task] = set()

        # Web 管理端服务器引用（用于事件驱动的 WebSocket 推送）
        self.web_admin_server = None

        # 地震列表缓存（用于查询指令）
        self.earthquake_lists = {"cenc": {}, "jma": {}}

        # 数据持久化路径
        self.storage_dir = StarTools.get_data_dir("astrbot_plugin_disaster_warning")
        self.cache_file = os.path.join(self.storage_dir, "earthquake_lists_cache.json")

        # EEW 查询状态缓存（机构级）
        self.eew_query_cache_file = os.path.join(
            self.storage_dir, "eew_query_cache.json"
        )
        self.eew_query_state: dict[str, dict[str, Any]] = {}

    def _initialize_handlers(self):
        """初始化数据处理器"""
        for source_id, handler_class in DATA_HANDLERS.items():
            self.handlers[source_id] = handler_class(self.message_logger)

    def _check_registry_integrity(self):
        """检查各注册表的一致性"""
        handler_ids = set(DATA_HANDLERS.keys())
        formatter_ids = set(MESSAGE_FORMATTERS.keys())
        config_ids = set(DATA_SOURCE_CONFIGS.keys())
        mapping_ids = set(DATA_SOURCE_MAPPING.keys())

        # 1. 检查 Handler 是否都有 Formatter
        missing_formatters = handler_ids - formatter_ids
        if missing_formatters:
            logger.warning(
                f"[灾害预警] 以下数据源缺少格式化器注册: {missing_formatters}"
            )

        # 2. 检查 Handler 是否都有 Config
        missing_configs = handler_ids - config_ids
        if missing_configs:
            logger.warning(f"[灾害预警] 以下数据源缺少配置定义: {missing_configs}")

        # 3. 检查 Handler 是否都在 Mapping 中 (用于枚举转换)
        missing_mappings = handler_ids - mapping_ids
        if missing_mappings:
            logger.warning(
                f"[灾害预警] 以下数据源缺少 ID-枚举 映射: {missing_mappings}"
            )

        if not missing_formatters and not missing_configs and not missing_mappings:
            logger.debug("[灾害预警] 注册表完整性自检通过")

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

            # 执行注册表自检
            self._check_registry_integrity()

            # 异步预加载 FE Regions 数据，防止后续同步调用阻塞事件循环
            await load_data_async()

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
                await self._telemetry.track_error(
                    e, module="core.disaster_service.initialize"
                )
            raise

    def _register_handlers(self):
        """注册消息处理器"""
        registry = WebSocketHandlerRegistry(self)
        registry.register_all(self.ws_manager)
        # 注册离线通知回调
        self.ws_manager.set_offline_notify_callback(self._handle_offline_notification)

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
                "china_earthquake_warning_provincial",
                "taiwan_cwa_earthquake",
                "taiwan_cwa_report",
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
            global_quake_url = "wss://gqm.aloys23.link/ws"
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
                self._stopping = False
                self.start_time = datetime.now(timezone.utc)  # 记录启动时间
                logger.info("[灾害预警] 正在启动灾害预警服务...")

                # 初始化统计管理器的数据库连接
                await self.statistics_manager.initialize()

                # 加载缓存数据
                self._load_earthquake_lists_cache()
                self._load_eew_query_cache()

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
                    await self._telemetry.track_error(
                        e, module="core.disaster_service.start"
                    )
                raise

    async def _cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def register_background_task(self, task: asyncio.Task) -> None:
        """注册服务级后台任务，确保停机时可统一回收。"""
        if task is None:
            return

        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def stop(self):
        """停止服务"""
        async with self._stop_lock:
            if self._stopping:
                logger.debug("[灾害预警] 停止流程已在执行中，跳过重复调用")
                return
            self._stopping = True
            try:
                logger.info("[灾害预警] 正在停止灾害预警服务...")
                # 先标记为停止，阻止新任务进入
                was_running = self.running
                self.running = False

                # 仅在服务实际运行过时保存缓存
                if was_running:
                    self._save_earthquake_lists_cache()
                    self._save_eew_query_cache()

                # 取消并等待所有连接任务退出
                connection_tasks = list(self.connection_tasks)
                await self._cancel_and_wait(connection_tasks)
                self.connection_tasks.clear()

                # 取消并等待所有定时任务退出
                scheduled_tasks = list(self.scheduled_tasks)
                await self._cancel_and_wait(scheduled_tasks)
                self.scheduled_tasks.clear()

                # 取消并等待由处理器派发的服务级后台任务
                background_tasks = [
                    task for task in self.background_tasks if task and not task.done()
                ]
                await self._cancel_and_wait(background_tasks)
                self.background_tasks.clear()

                # 停止WebSocket管理器
                await self.ws_manager.stop()

                # 关闭HTTP获取器
                if self.http_fetcher:
                    await self.http_fetcher.close()

                # 关闭数据库连接
                if self.statistics_manager and self.statistics_manager._db_initialized:
                    await self.statistics_manager.db.close()

                logger.info("[灾害预警] 灾害预警服务已停止")

            except Exception as e:
                logger.error(f"[灾害预警] 停止服务时出错: {e}")
                # 上报停止服务错误到遥测
                if self._telemetry and self._telemetry.enabled:
                    await self._telemetry.track_error(
                        e, module="core.disaster_service.stop"
                    )
            finally:
                self._stopping = False

    async def _establish_websocket_connections(self):
        """建立WebSocket连接 - 使用WebSocket管理器功能"""
        logger.debug(
            f"[灾害预警] 开始建立WebSocket连接，当前任务数: {len(self.connection_tasks)}"
        )

        async def _connect_with_timeout(name, uri, info):
            """带超时的连接包装器"""
            try:
                # 设置连接阶段的超时限制 (如 30 秒)
                # 注意：ws_manager.connect 内部包含重连循环，这里设置的是首次连接或单次尝试的策略建议
                # 实际上 ws_manager.connect 是长驻任务，我们通过包装来确保启动逻辑不被卡死
                await self.ws_manager.connect(
                    name=name,
                    uri=uri,
                    connection_info=info,
                )
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket 连接任务 {name} 异常终止: {e}")

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

                # 启动连接任务
                task = asyncio.create_task(
                    _connect_with_timeout(
                        conn_name, conn_config["url"], connection_info
                    ),
                    name=f"dw_ws_connect_{conn_name}",
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

        logger.debug(
            f"[灾害预警] WebSocket连接建立完成，总任务数: {len(self.connection_tasks)}"
        )

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
                        # 获取中国地震台网地震列表 (添加超时保护且不覆盖旧缓存)
                        try:
                            cenc_data = await asyncio.wait_for(
                                fetcher.fetch_json(
                                    "https://api.wolfx.jp/cenc_eqlist.json"
                                ),
                                timeout=60,
                            )
                            if cenc_data:
                                # 更新缓存
                                self.update_earthquake_list("cenc", cenc_data)

                                # 仅在启用该数据源时才解析并尝试推送
                                if self.is_wolfx_source_enabled(
                                    "china_cenc_earthquake"
                                ):
                                    handler = self.handlers.get("cenc_wolfx")
                                    if handler:
                                        event = handler.parse_message(
                                            json.dumps(cenc_data)
                                        )
                                        if event:
                                            await self._handle_disaster_event(event)
                        except asyncio.TimeoutError:
                            logger.warning(
                                "[灾害预警] 定时获取 CENC 地震列表超时，保留原有缓存"
                            )
                        except Exception as e:
                            logger.error(f"[灾害预警] 获取 CENC 数据出错: {e}")

                        # 获取日本气象厅地震列表 (添加超时保护且不覆盖旧缓存)
                        try:
                            jma_data = await asyncio.wait_for(
                                fetcher.fetch_json(
                                    "https://api.wolfx.jp/jma_eqlist.json"
                                ),
                                timeout=60,
                            )
                            if jma_data:
                                # 更新缓存
                                self.update_earthquake_list("jma", jma_data)

                                # 仅在启用该数据源时才解析并尝试推送
                                if self.is_wolfx_source_enabled("japan_jma_earthquake"):
                                    handler = self.handlers.get("jma_wolfx_info")
                                    if handler:
                                        event = handler.parse_message(
                                            json.dumps(jma_data)
                                        )
                                        if event:
                                            await self._handle_disaster_event(event)
                        except asyncio.TimeoutError:
                            logger.warning(
                                "[灾害预警] 定时获取 JMA 地震列表超时，保留原有缓存"
                            )
                        except Exception as e:
                            logger.error(f"[灾害预警] 获取 JMA 数据出错: {e}")

                except Exception as e:
                    logger.error(f"[灾害预警] 定时HTTP数据获取失败: {e}")

        task = asyncio.create_task(fetch_wolfx_data(), name="dw_http_fetch_wolfx")
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

        task = asyncio.create_task(cleanup(), name="dw_cleanup")
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
        temp_file = self.cache_file + ".tmp"
        try:
            if not os.path.exists(self.storage_dir):
                os.makedirs(self.storage_dir, exist_ok=True)

            # 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.earthquake_lists, f, ensure_ascii=False)

            # 原子性重命名 (在 Windows 上如果目标存在会报错，需先删除)
            if os.path.exists(self.cache_file):
                os.replace(temp_file, self.cache_file)
            else:
                os.rename(temp_file, self.cache_file)

            logger.info("[灾害预警] Wolfx 地震列表缓存已保存")
        except Exception as e:
            logger.error(f"[灾害预警] 保存 Wolfx 地震列表缓存失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

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

            # 解析深度数值
            depth_val = -1.0
            try:
                if isinstance(depth, (int, float)):
                    depth_val = float(depth)
                elif isinstance(depth, str):
                    clean_depth = depth.lower().replace("km", "").strip()
                    if clean_depth:
                        depth_val = float(clean_depth)
            except Exception:
                depth_val = -1.0

            # 深度显示逻辑
            depth_label = "深度"
            depth_value_str = str(depth).replace("km", "").strip()
            depth_unit = "km"

            if source_type == "jma":
                depth_label = "深さ"
                if depth_val == 0.0:
                    depth_value_str = "ごく浅い"
                    depth_unit = ""
                    depth = "ごく浅い"
                else:
                    if depth_val >= 0:
                        formatted_val = (
                            f"{int(depth_val)}"
                            if depth_val.is_integer()
                            else f"{depth_val}"
                        )
                        depth = f"{formatted_val} km"
                        depth_value_str = formatted_val
                    else:
                        clean_d = str(depth).replace("km", "").strip()
                        depth = f"{clean_d} km"
            else:
                # cenc
                depth_label = "深度"
                if depth_val == 0.0:
                    depth_value_str = "极浅"
                    depth_unit = ""
                    depth = "极浅"
                else:
                    if depth_val >= 0:
                        formatted_val = (
                            f"{int(depth_val)}"
                            if depth_val.is_integer()
                            else f"{depth_val}"
                        )
                        depth = f"{formatted_val} km"
                        depth_value_str = formatted_val
                    else:
                        clean_d = str(depth).replace("km", "").strip()
                        depth = f"{clean_d} km"

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
                "depth_label": depth_label,
                "depth_value": depth_value_str,
                "depth_unit": depth_unit,
                "is_text_depth": (depth_val == 0.0),
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
        # 先更新 EEW 查询状态（与推送过滤解耦）
        try:
            self._update_eew_query_state(event)
        except Exception as e:
            logger.debug(f"[灾害预警] 更新 EEW 查询状态失败（已忽略）: {e}")

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

            # 推送消息 - 使用新消息管理器
            target_sessions = self.session_config_manager.list_target_sessions()
            push_result = await self.message_manager.push_event(
                event,
                target_sessions=target_sessions,
                session_config_getter=self.session_config_manager.get_effective_config,
            )
            if push_result:
                logger.debug(f"[灾害预警] ✅ 事件推送成功: {event.id}")
            else:
                logger.debug(f"[灾害预警] 事件推送被过滤: {event.id}")

            # 记录统计数据 (不管是否推送成功)
            await self.statistics_manager.record_push(
                event,
                pushed_sessions=self.message_manager.last_success_sessions,
            )

            # 实时通知 Web 管理端（如果已配置）
            if self.web_admin_server:
                try:
                    # 构建事件摘要
                    event_summary = {
                        "id": event.id,
                        "type": event.disaster_type.value
                        if hasattr(event.disaster_type, "value")
                        else str(event.disaster_type),
                        "source": event.source.value
                        if hasattr(event.source, "value")
                        else str(event.source),
                        "time": datetime.now().isoformat(),
                    }
                    await self.web_admin_server.notify_event(event_summary)
                except Exception as ws_e:
                    logger.debug(f"[灾害预警] WebSocket 通知失败: {ws_e}")

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
                log_info = f"气象事件 - 标题: {weather.title or weather.headline}, 数据源: {event.source.value}"
            else:
                log_info = (
                    f"未知事件类型 - ID: {event.id}, 数据源: {event.source.value}"
                )

            logger.debug(f"[灾害预警] 事件详情: {log_info}")
        except Exception:
            logger.debug(
                f"[灾害预警] 事件详情: ID={event.id}, 类型={event.disaster_type.value}, 数据源={event.source.value}"
            )

    async def _handle_offline_notification(self, payload: dict[str, Any]) -> None:
        """处理 WebSocket 管理器离线通知回调"""
        await self.notify_data_source_offline(
            connection_name=payload.get("connection_name", "unknown"),
            data_source=payload.get("data_source", "unknown"),
            stage=payload.get("stage", "unknown"),
            reason=payload.get("reason", "未知原因"),
            next_retry_in=payload.get("next_retry_in"),
            retry_count=payload.get("retry_count"),
            fallback_count=payload.get("fallback_count"),
        )

    async def notify_data_source_offline(
        self,
        connection_name: str,
        data_source: str,
        stage: str,
        reason: str,
        next_retry_in: str | None = None,
        retry_count: int | None = None,
        fallback_count: int | None = None,
    ) -> bool:
        """推送数据源离线通知（兜底重试/停止重连）"""
        if not self.message_manager:
            return False

        # 生成去重键
        key = f"{connection_name}:{stage}"
        now = asyncio.get_running_loop().time()
        state = self._offline_notification_state.get(key, {})
        last_ts = state.get("last_ts", 0.0)
        # 兜底重试与停止重连为高优先级，但仍避免过频刷屏（默认 30 分钟）
        ttl_seconds = 1800
        if now - last_ts < ttl_seconds:
            return False

        # 组装消息
        stage_map = {
            "fallback": "进入兜底重试",
            "stop": "停止重连",
        }
        stage_text = stage_map.get(stage, stage)
        retry_part = (
            f"短时重试: {retry_count}" if retry_count is not None else "短时重试: 未知"
        )
        fallback_part = (
            f"兜底重试: {fallback_count}"
            if fallback_count is not None
            else "兜底重试: 未知"
        )
        next_retry_part = (
            f"下一次重试: {next_retry_in}" if next_retry_in else "下一次重试: 未知"
        )

        message_lines = [
            "⚠️ 数据源离线通知",
            f"📡 连接: {connection_name}",
            f"🧩 数据源: {data_source}",
            f"⛔ 状态: {stage_text}",
            f"📝 原因: {reason}",
            f"🔁 {retry_part}",
            f"🛟 {fallback_part}",
        ]
        if stage == "fallback":
            message_lines.append(f"⏳ {next_retry_part}")

        message = "\n".join(message_lines)
        success = await self.message_manager.push_system_message(message)
        if success:
            self._offline_notification_state[key] = {"last_ts": now}
        return bool(success)

    async def reconnect_all_sources(self) -> dict[str, str]:
        """
        强制重连所有已启用但离线的数据源
        返回: dict {connection_name: status_message}
        """
        results = {}
        if not self.ws_manager:
            return {"error": "WebSocket管理器未初始化"}

        reconnect_count = 0

        # 遍历 Service 层配置的所有连接
        for conn_name, conn_config in self.connections.items():
            # 检查连接状态
            is_connected = False
            if conn_name in self.ws_manager.connections:
                ws = self.ws_manager.connections[conn_name]
                if not ws.closed:
                    is_connected = True

            if is_connected:
                results[conn_name] = "已连接 (跳过)"
                continue

            # 执行强制重连
            try:
                # 确保 connection_info 存在于 ws_manager 中
                # 如果因为某种原因丢失，尝试修复（通常 start() 后都会有）
                if conn_name not in self.ws_manager.connection_info:
                    connection_info = {
                        "connection_name": conn_name,
                        "handler_type": conn_config["handler"],
                        "data_source": self._get_data_source_from_connection(conn_name),
                        "established_time": None,
                        "backup_url": conn_config.get("backup_url"),
                    }
                    self.ws_manager.connection_info[conn_name] = {
                        "uri": conn_config["url"],
                        "headers": None,
                        "connection_type": "websocket",
                        "established_time": None,
                        "retry_count": 0,
                        **connection_info,
                    }

                # 调用 WebSocket Manager 的强制重连
                if hasattr(self.ws_manager, "force_reconnect"):
                    triggered = await self.ws_manager.force_reconnect(conn_name)
                    if triggered:
                        results[conn_name] = "✅ 已触发重连"
                        reconnect_count += 1
                    else:
                        results[conn_name] = "⚠️ 重连未触发"
                else:
                    results[conn_name] = "❌ Manager不支持重连"

            except Exception as e:
                results[conn_name] = f"❌ 失败: {e}"
                logger.error(f"[灾害预警] 手动重连 {conn_name} 失败: {e}")

        logger.info(f"[灾害预警] 手动重连操作完成，触发了 {reconnect_count} 个重连任务")
        return results

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

        # 获取子数据源启用状态
        sub_source_status = self._get_sub_source_status()

        return {
            "running": self.running,
            "active_websocket_connections": active_websocket_connections,
            "global_quake_connected": global_quake_connected,
            "total_connections": len(connection_status),
            "connection_details": connection_status,
            "sub_source_status": sub_source_status,  # 新增：子数据源状态
            "statistics_summary": self.statistics_manager.get_summary(),
            "data_sources": self._get_active_data_sources(),
            "message_logger_enabled": self.message_logger.enabled
            if self.message_logger
            else False,
            "uptime": self._get_uptime(),  # 添加运行时间
            "start_time": self.start_time.isoformat()
            if hasattr(self, "start_time")
            else None,
        }

    def _get_sub_source_status(self) -> dict[str, dict[str, bool]]:
        """获取所有子数据源的启用状态"""
        status = {
            "fan_studio": {},
            "p2p_earthquake": {},
            "wolfx": {},
            "global_quake": {},
        }

        data_sources = self.config.get("data_sources", {})

        # FAN Studio
        fan_config = data_sources.get("fan_studio", {})
        if isinstance(fan_config, dict):
            status["fan_studio"] = {
                k: v
                for k, v in fan_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        # P2P
        p2p_config = data_sources.get("p2p_earthquake", {})
        if isinstance(p2p_config, dict):
            status["p2p_earthquake"] = {
                k: v
                for k, v in p2p_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        # Wolfx
        wolfx_config = data_sources.get("wolfx", {})
        if isinstance(wolfx_config, dict):
            status["wolfx"] = {
                k: v
                for k, v in wolfx_config.items()
                if k != "enabled" and isinstance(v, bool)
            }

        # Global Quake (仅总开关)
        gq_config = data_sources.get("global_quake", {})
        if isinstance(gq_config, dict):
            status["global_quake"] = {"enabled": gq_config.get("enabled", False)}

        return status

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

    def _get_source_id_from_event(self, event: DisasterEvent) -> str:
        """将事件 source 枚举反向映射为 source_id。"""
        reverse_mapping = {v.value: k for k, v in DATA_SOURCE_MAPPING.items()}
        source_value = event.source.value if hasattr(event.source, "value") else ""
        return reverse_mapping.get(source_value, source_value)

    def _resolve_event_publish_time_utc(
        self, event: DisasterEvent, source_id: str
    ) -> datetime:
        """解析事件发布时间并归一化为 UTC（优先发布时间，其次接收时间）。"""
        data = event.data
        candidate = None

        if isinstance(data, EarthquakeData):
            candidate = data.create_time or data.update_time or data.shock_time

        if candidate is None:
            candidate = event.receive_time if hasattr(event, "receive_time") else None

        if candidate is None:
            return datetime.now(timezone.utc)

        if candidate.tzinfo is not None:
            return candidate.astimezone(timezone.utc)

        # Naive 时间按来源推断时区
        if "jma" in source_id or "p2p" in source_id:
            inferred_tz = TimeConverter._get_timezone("Asia/Tokyo")
        elif source_id == "global_quake":
            inferred_tz = timezone.utc
        else:
            inferred_tz = TimeConverter._get_timezone("Asia/Shanghai")

        return candidate.replace(tzinfo=inferred_tz).astimezone(timezone.utc)

    def _normalize_eew_query_institution(self, source_id: str) -> str | None:
        """将 source_id 归一化到机构维度。"""
        for institution_key, meta in self._EEW_QUERY_INSTITUTIONS.items():
            if source_id in meta.get("source_ids", []):
                return institution_key
        return None

    def _build_eew_query_fingerprint(self, data: EarthquakeData, source_id: str) -> str:
        """构建机构内去重指纹（跨数据源）。"""
        event_key = data.event_id or data.id or ""
        place = (data.place_name or "未知地点").strip()
        magnitude = "?" if data.magnitude is None else f"{float(data.magnitude):.1f}"
        shock_time = self._resolve_event_publish_time_utc(
            DisasterEvent(
                id=data.id,
                data=data,
                source=data.source,
                disaster_type=data.disaster_type,
            ),
            source_id,
        )
        minute_bucket = shock_time.strftime("%Y%m%d%H%M")
        return f"{event_key}|{place}|{magnitude}|{minute_bucket}"

    def _should_replace_eew_query_state(
        self, current: dict[str, Any], candidate: dict[str, Any]
    ) -> bool:
        """判断候选 EEW 状态是否应覆盖当前状态。"""
        current_fp = current.get("fingerprint", "")
        candidate_fp = candidate.get("fingerprint", "")

        # 同一事件：优先更高报次或更晚发布时间
        if current_fp and candidate_fp and current_fp == candidate_fp:
            current_updates = int(current.get("updates", 1) or 1)
            candidate_updates = int(candidate.get("updates", 1) or 1)
            if candidate_updates > current_updates:
                return True
            if candidate_updates < current_updates:
                return False

        # 不同事件：以发布时间新者覆盖
        current_issued = TimeConverter.parse_datetime(current.get("issued_at"))
        candidate_issued = TimeConverter.parse_datetime(candidate.get("issued_at"))
        if current_issued is None:
            return True
        if candidate_issued is None:
            return False
        if current_issued.tzinfo is None:
            current_issued = current_issued.replace(tzinfo=timezone.utc)
        if candidate_issued.tzinfo is None:
            candidate_issued = candidate_issued.replace(tzinfo=timezone.utc)
        return candidate_issued >= current_issued

    def _update_eew_query_state(self, event: DisasterEvent) -> None:
        """更新地震预警查询状态（机构级，跨源去重）。"""
        if event.disaster_type != DisasterType.EARTHQUAKE_WARNING:
            return
        if not isinstance(event.data, EarthquakeData):
            return

        source_id = self._get_source_id_from_event(event)
        institution_key = self._normalize_eew_query_institution(source_id)
        if not institution_key:
            return

        issued_at = self._resolve_event_publish_time_utc(event, source_id)
        expires_at = issued_at + timedelta(seconds=self.EEW_VALID_DURATION_SECONDS)
        data = event.data

        # 机构内去重：同一事件多来源仅保留一份
        event_key = data.event_id or data.id or ""
        place = (data.place_name or "未知地点").strip()
        magnitude = data.magnitude
        magnitude_text = "未知" if magnitude is None else f"{float(magnitude):.1f}"
        minute_bucket = issued_at.strftime("%Y%m%d%H%M")
        fingerprint = f"{event_key}|{place}|{magnitude_text}|{minute_bucket}"

        candidate = {
            "source_id": source_id,
            "event_id": event_key,
            "display_place": place,
            "display_magnitude": magnitude,
            "updates": int(getattr(data, "updates", 1) or 1),
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "fingerprint": fingerprint,
        }

        current = self.eew_query_state.get(institution_key)
        if current and not self._should_replace_eew_query_state(current, candidate):
            return

        self.eew_query_state[institution_key] = candidate

    @staticmethod
    def _format_elapsed_seconds(total_seconds: int) -> str:
        """将秒数格式化为“X天Y时Z分W秒”样式。"""
        total_seconds = max(0, int(total_seconds))
        days, rem = divmod(total_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)

        if days > 0:
            return f"{days}天{hours}时{minutes}分{seconds}秒"
        if hours > 0:
            return f"{hours}时{minutes}分{seconds}秒"
        if minutes > 0:
            return f"{minutes}分{seconds}秒"
        return f"{seconds}秒"

    def _get_enabled_eew_sources_by_institution(self) -> dict[str, list[str]]:
        """返回每个机构当前启用的 source_id 列表。"""
        data_sources_cfg = self.config.get("data_sources", {})
        result: dict[str, list[str]] = {}

        for institution_key, meta in self._EEW_QUERY_INSTITUTIONS.items():
            enabled_sources = [
                source_id
                for source_id in meta.get("source_ids", [])
                if is_source_enabled_in_data_sources(source_id, data_sources_cfg)
            ]
            result[institution_key] = enabled_sources

        return result

    @staticmethod
    def _parse_utc_datetime(value: Any) -> datetime | None:
        """将字符串时间解析为 UTC aware datetime。"""
        dt = TimeConverter.parse_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def get_eew_query_status_data(self) -> dict[str, Any]:
        """获取地震预警查询的结构化状态数据（供 Web 与指令复用）。"""
        now_utc = datetime.now(timezone.utc)
        enabled_sources_map = self._get_enabled_eew_sources_by_institution()

        institutions: list[dict[str, Any]] = []
        for institution_key, meta in self._EEW_QUERY_INSTITUTIONS.items():
            enabled_sources = enabled_sources_map.get(institution_key, [])
            display_name = meta.get("display_name", institution_key)
            active_name = meta.get("active_name", display_name)

            item: dict[str, Any] = {
                "institution_key": institution_key,
                "display_name": display_name,
                "active_name": active_name,
                "enabled": bool(enabled_sources),
                "enabled_sources": enabled_sources,
                "status": "unavailable",
                "elapsed_seconds": None,
                "issued_at": None,
                "expires_at": None,
                "magnitude": None,
                "place": None,
            }

            if not enabled_sources:
                institutions.append(item)
                continue

            state = self.eew_query_state.get(institution_key)
            if not isinstance(state, dict):
                item["status"] = "no_data"
                institutions.append(item)
                continue

            issued_at = self._parse_utc_datetime(state.get("issued_at"))
            expires_at = self._parse_utc_datetime(state.get("expires_at"))
            if issued_at is None:
                item["status"] = "no_data"
                institutions.append(item)
                continue

            if expires_at is None:
                expires_at = issued_at + timedelta(
                    seconds=self.EEW_VALID_DURATION_SECONDS
                )

            item["issued_at"] = issued_at.isoformat()
            item["expires_at"] = expires_at.isoformat()
            item["magnitude"] = state.get("display_magnitude")
            item["place"] = state.get("display_place") or "未知地点"

            elapsed = int((now_utc - issued_at).total_seconds())
            item["elapsed_seconds"] = max(0, elapsed)
            item["status"] = "active" if now_utc < expires_at else "inactive"
            institutions.append(item)

        return {
            "timestamp": now_utc.isoformat(),
            "valid_duration_seconds": self.EEW_VALID_DURATION_SECONDS,
            "institutions": institutions,
        }

    def get_eew_query_text(self) -> str:
        """生成 /地震预警查询 文本。"""
        status_data = self.get_eew_query_status_data()
        institutions = status_data.get("institutions", [])

        active_lines: list[str] = []
        inactive_items: list[tuple[int, str]] = []
        no_data_lines: list[str] = []
        unavailable_lines: list[str] = []

        for item in institutions:
            display_name = item.get("display_name", "未知机构")
            active_name = item.get("active_name", display_name)
            status = item.get("status")

            if status == "unavailable":
                unavailable_lines.append(
                    f"- {display_name}：未启用对应数据源开关，无法计算无 EEW 时间"
                )
                continue

            if status == "no_data":
                no_data_lines.append(
                    f"- {display_name}：已启用数据源，但暂无可计算历史数据"
                )
                continue

            if status == "active":
                magnitude = item.get("magnitude")
                place = item.get("place") or "未知地点"
                if magnitude is None:
                    mag_text = "?"
                else:
                    try:
                        mag_text = f"{float(magnitude):.1f}"
                    except Exception:
                        mag_text = str(magnitude)
                active_lines.append(
                    f"[{active_name}] 当前正在发布地震预警：M {mag_text} {place}"
                )
                continue

            elapsed = int(item.get("elapsed_seconds") or 0)
            inactive_items.append(
                (elapsed, f"{self._format_elapsed_seconds(elapsed)} 无 {display_name}")
            )

        inactive_lines = [
            line for _, line in sorted(inactive_items, key=lambda item: item[0])
        ]

        lines: list[str] = []
        if active_lines:
            lines.extend(active_lines)
            if inactive_lines:
                lines.append("")
                lines.extend(inactive_lines)
        else:
            lines.append("当前没有正在生效的地震预警")
            if inactive_lines:
                lines.append("")
                lines.extend(inactive_lines)

        if no_data_lines:
            lines.append("")
            lines.append("以下机构暂无可计算的历史 EEW 数据：")
            lines.extend(no_data_lines)

        if unavailable_lines:
            lines.append("")
            lines.append("以下机构因数据源开关未启用，无法参与计算：")
            lines.extend(unavailable_lines)

        # 兜底：避免空文本
        if not lines:
            lines.append("当前没有正在生效的地震预警")

        return "\n".join(lines)

    def _load_eew_query_cache(self):
        """从文件加载 EEW 查询状态缓存。"""
        try:
            if not os.path.exists(self.eew_query_cache_file):
                logger.debug("[灾害预警] EEW 查询缓存文件不存在，将使用空状态")
                return

            with open(self.eew_query_cache_file, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                logger.warning("[灾害预警] EEW 查询缓存格式无效，已忽略")
                return

            restored: dict[str, dict[str, Any]] = {}
            for key, value in data.items():
                if key not in self._EEW_QUERY_INSTITUTIONS:
                    continue
                if not isinstance(value, dict):
                    continue
                if not value.get("issued_at"):
                    continue
                restored[key] = value

            self.eew_query_state = restored
            if restored:
                logger.debug("[灾害预警] 已恢复 EEW 查询缓存")

        except Exception as e:
            logger.warning(f"[灾害预警] 加载 EEW 查询缓存失败: {e}")

    def _save_eew_query_cache(self):
        """保存 EEW 查询状态缓存到文件。"""
        temp_file = self.eew_query_cache_file + ".tmp"
        try:
            if not os.path.exists(self.storage_dir):
                os.makedirs(self.storage_dir, exist_ok=True)

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.eew_query_state, f, ensure_ascii=False)

            if os.path.exists(self.eew_query_cache_file):
                os.replace(temp_file, self.eew_query_cache_file)
            else:
                os.rename(temp_file, self.eew_query_cache_file)

            logger.debug("[灾害预警] EEW 查询缓存已保存")
        except Exception as e:
            logger.error(f"[灾害预警] 保存 EEW 查询缓存失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass


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
