"""
WebSocket连接管理器
适配数据处理器架构，提供更好的错误处理和重连机制
(已迁移至 aiohttp 实现以获得更好的跨平台兼容性)
"""

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType

from astrbot.api import logger


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self, config: dict[str, Any], message_logger=None):
        self.config = config
        self.message_logger = message_logger
        self.connections: dict[str, ClientWebSocketResponse] = {}
        self.message_handlers: dict[str, Callable] = {}
        self.reconnect_tasks: dict[str, asyncio.Task] = {}
        self.connection_retry_counts: dict[str, int] = {}
        self.fallback_retry_counts: dict[str, int] = {}  # 兜底重试计数
        self.connection_info: dict[str, dict] = {}  # 新增：存储连接信息
        self.running = False
        self.session: aiohttp.ClientSession | None = None

    def register_handler(self, connection_name: str, handler: Callable):
        """注册消息处理器"""
        self.message_handlers[connection_name] = handler
        logger.info(f"[灾害预警] 注册处理器: {connection_name}")

    async def connect(
        self,
        name: str,
        uri: str,
        headers: dict | None = None,
        is_retry: bool = False,
        connection_info: dict | None = None,
    ):
        """建立WebSocket连接 - aiohttp版本"""
        # 确保 session 存在
        if not self.session or self.session.closed:
            logger.warning(f"[灾害预警] WebSocket会话未就绪，正在重新初始化: {name}")
            # 使用默认配置初始化，实际应该在 start 中完成
            self.session = aiohttp.ClientSession()

        try:
            # 记录连接信息
            self.connection_info[name] = {
                "uri": uri,
                "headers": headers,
                "connection_type": "websocket",
                "established_time": None,
                "retry_count": 0,
                **(connection_info or {}),
            }

            # 如果是重试连接，记录重试次数
            if is_retry:
                current_retry = self.connection_retry_counts.get(name, 0) + 1
                self.connection_retry_counts[name] = current_retry
            else:
                logger.info(f"[灾害预警] 正在连接 {name}")
                # 首次连接时重置重试计数
                self.connection_retry_counts[name] = 0

            # aiohttp ws_connect 配置
            connect_kwargs = {
                "url": uri,
                "headers": headers or {},
                "heartbeat": self.config.get("heartbeat_interval", 60),
                "timeout": self.config.get("connection_timeout", 10),
                "max_msg_size": self.config.get("max_message_size", 2**20),  # 1MB默认
            }

            # 添加SSL配置（如果需要）
            if self.config.get("ssl_verify", True) is False:
                connect_kwargs["ssl"] = False

            async with self.session.ws_connect(**connect_kwargs) as websocket:
                self.connections[name] = websocket
                self.connection_info[name]["established_time"] = (
                    asyncio.get_event_loop().time()
                )
                logger.info(f"[灾害预警] WebSocket连接成功: {name}")
                # 连接成功，重置所有重试计数
                self.connection_retry_counts[name] = 0
                self.fallback_retry_counts[name] = 0

                try:
                    # 处理消息 - aiohttp 风格
                    async for msg in websocket:
                        if msg.type == WSMsgType.TEXT:
                            message = msg.data
                            try:
                                # 记录原始消息
                                if self.message_logger:
                                    self._log_message(name, message, uri)

                                # 智能处理器查找（支持前缀匹配）
                                handler_name = self._find_handler_by_prefix(name)

                                if handler_name:
                                    # 增强：传递更多连接信息给处理器
                                    await self.message_handlers[handler_name](
                                        message,
                                        connection_name=name,
                                        connection_info=self.connection_info[name],
                                    )
                                else:
                                    logger.warning(
                                        f"[灾害预警] 未找到消息处理器 - 连接: {name}"
                                    )
                            except Exception as e:
                                # 消息处理层面的错误不应导致连接断开
                                logger.error(f"[灾害预警] 消息处理错误 {name}: {e}")
                                logger.debug(
                                    f"[灾害预警] 异常堆栈: {traceback.format_exc()}"
                                )

                        elif msg.type == WSMsgType.ERROR:
                            # 抛出异常以触发重连逻辑
                            raise msg.data

                        elif msg.type == WSMsgType.CLOSED:
                            logger.info(
                                f"[灾害预警] WebSocket连接已关闭: {name}, code={websocket.close_code}"
                            )
                            break

                    # 检查连接关闭代码，如果是非正常关闭则抛出异常以触发重连
                    if (
                        websocket.close_code is not None
                        and websocket.close_code not in (1000, 1001)
                    ):
                        raise Exception(
                            f"WebSocket连接意外关闭，代码 {websocket.close_code}"
                        )

                except Exception as e:
                    # 这里的异常通常是处理循环中的非预期间断
                    logger.error(f"[灾害预警] WebSocket消息循环异常 {name}: {e}")
                    raise

                # 连接正常结束 (code 1000/1001)
                logger.info(f"[灾害预警] 连接断开: {name}")

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # 网络层面的错误
            logger.warning(f"[灾害预警] 连接中断或失败 {name}: {e}")
            self._handle_connection_error(name, uri, headers, e)

        except Exception as e:
            logger.error(f"[灾害预警] 未知连接错误 {name}: {type(e).__name__} - {e}")
            logger.debug(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")
            self._handle_connection_error(name, uri, headers, e)

    def _log_message(self, name: str, message: Any, uri: str):
        """记录消息辅助方法"""
        try:
            # 尝试使用消息记录器格式
            self.message_logger.log_raw_message(
                source=f"websocket_{name}",
                message_type="websocket_message",
                raw_data=message,
                connection_info={
                    "url": uri,
                    "connection_type": "websocket",
                    "handler": self._get_handler_name_for_connection(name),
                    **self.connection_info.get(name, {}),
                },
            )
        except (TypeError, AttributeError):
            # 向后兼容：旧的消息记录器格式
            try:
                self.message_logger.log_websocket_message(name, message, uri)
            except Exception as e:
                logger.warning(f"[灾害预警] 消息记录失败: {e}")

    def _handle_connection_error(
        self, name: str, uri: str, headers: dict | None, error: Exception
    ):
        """统一处理连接错误"""
        # 清理连接信息
        self.connections.pop(name, None)
        # 保存旧的连接信息以便重连时使用（包含 backup_url 等配置）
        connection_info = self.connection_info.pop(name, {})

        # 启动重连任务
        if self.running:
            # 检查是否应该重连
            if self._should_reconnect_on_error(error):
                asyncio.create_task(
                    self._schedule_reconnect(name, uri, headers, connection_info)
                )
            else:
                logger.warning(f"[灾害预警] {name} 遇到不可恢复错误，停止重连")

    def _should_reconnect_on_error(self, error: Exception) -> bool:
        """判断遇到错误时是否应该重连"""
        error_msg = str(error).lower()

        # SSL错误通常不需要重试（配置问题）
        if "ssl" in error_msg or "certificate" in error_msg:
            return False

        # 认证错误不需要重试
        if "401" in error_msg or "403" in error_msg:
            return False

        # 其他大部分网络错误都值得重试
        return True

    def _get_handler_name_for_connection(self, connection_name: str) -> str:
        """获取连接对应的处理器名称"""
        # 定义连接名称前缀到处理器名称的映射
        # 优化：优先匹配更长的前缀，防止 fan_studio_all 被误识别为其他
        prefix_mappings = {
            "fan_studio_all": "fan_studio",  # 明确匹配 /all 连接
            "p2p_": "p2p",
            "wolfx_": "wolfx",
            "global_quake": "global_quake",
        }

        # 尝试前缀匹配
        for prefix, handler_name in prefix_mappings.items():
            if connection_name.startswith(prefix):
                return handler_name

        # 如果没有找到匹配，尝试更宽松的前缀匹配
        for handler_name in self.message_handlers.keys():
            if connection_name.startswith(handler_name):
                return handler_name

        return "unknown"

    async def _schedule_reconnect(
        self,
        name: str,
        uri: str,
        headers: dict | None = None,
        connection_info: dict | None = None,
    ):
        """计划重连 - 优化版本，基于配置的固定间隔"""
        if name in self.reconnect_tasks:
            self.reconnect_tasks[name].cancel()

        async def reconnect():
            # 获取重连配置
            max_retries = self.config.get("max_reconnect_retries", 3)
            reconnect_interval = self.config.get("reconnect_interval", 10)

            # 获取兜底重试配置
            fallback_enabled = self.config.get("fallback_retry_enabled", True)
            fallback_interval = self.config.get(
                "fallback_retry_interval", 1800
            )  # 默认30分钟
            fallback_max_count = self.config.get(
                "fallback_retry_max_count", -1
            )  # -1表示无限重试

            # 获取当前重试次数
            current_retry = self.connection_retry_counts.get(name, 0)
            current_fallback = self.fallback_retry_counts.get(name, 0)

            # 检查是否已达到最大重试次数
            # 如果配置了备用服务器，总次数为主备各 max_retries 次
            # 使用传入的 connection_info 检查 backup_url，因为 self.connection_info 已被清理
            has_backup = connection_info and connection_info.get("backup_url")
            total_max_retries = max_retries * 2 if has_backup else max_retries

            if current_retry >= total_max_retries:
                # 短时重连次数用尽，检查是否启用兜底重试
                if not fallback_enabled:
                    logger.error(
                        f"[灾害预警] {name} 重连失败，已达到最大重试次数 ({total_max_retries})，停止重连"
                    )
                    return

                # 检查兜底重试次数是否达到上限
                if fallback_max_count != -1 and current_fallback >= fallback_max_count:
                    logger.error(
                        f"[灾害预警] {name} 兜底重试失败，已达到最大兜底重试次数 ({fallback_max_count})，停止重连"
                    )
                    return

                # 进入兜底重试阶段
                self.fallback_retry_counts[name] = current_fallback + 1
                fallback_display = current_fallback + 1
                fallback_max_display = (
                    "无限" if fallback_max_count == -1 else str(fallback_max_count)
                )

                # 将兜底重试间隔格式化为更易读的单位，避免小于 60 秒时显示为 0 分钟的情况
                if fallback_interval < 60:
                    fallback_interval_display = f"{fallback_interval} 秒"
                else:
                    minutes = fallback_interval // 60
                    seconds = fallback_interval % 60
                    if seconds == 0:
                        fallback_interval_display = f"{minutes} 分钟"
                    else:
                        fallback_interval_display = f"{minutes} 分钟 {seconds} 秒"

                logger.warning(
                    f"[灾害预警] {name} 短时重连失败，将在 {fallback_interval_display} 后进行兜底重试 "
                    f"({fallback_display}/{fallback_max_display})"
                )

                try:
                    await asyncio.sleep(fallback_interval)
                    # 重置短时重连计数器，重新开始短时重连流程
                    self.connection_retry_counts[name] = 0
                    logger.info(f"[灾害预警] {name} 开始兜底重试，重置短时重连计数器")
                    await self.connect(
                        name,
                        uri,
                        headers,
                        is_retry=True,
                        connection_info=connection_info,
                    )
                except asyncio.CancelledError:
                    logger.info(f"[灾害预警] {name} 兜底重试任务被取消")
                except Exception as e:
                    logger.error(f"[灾害预警] {name} 兜底重试失败: {e}")
                return

            # 确定目标服务器 URI
            target_uri = uri
            server_type = "主服务器"

            # 如果有备用服务器且重试次数超过一半，切换到备用服务器
            if has_backup and current_retry >= max_retries:
                backup_url = connection_info.get("backup_url")
                if backup_url:
                    target_uri = backup_url
                    server_type = "备用服务器"

            # 计算显示用的重试进度，使日志更符合直觉
            # 如果是备用服务器，重新从 1 开始计数
            display_retry = current_retry + 1
            if server_type == "备用服务器":
                display_retry = current_retry - max_retries + 1

            logger.info(
                f"[灾害预警] {name} 将在 {reconnect_interval} 秒后尝试重连{server_type} ({display_retry}/{max_retries})"
            )

            try:
                await asyncio.sleep(reconnect_interval)
                # 标记为重试连接
                # 必须将 connection_info 传回去，否则下次重试时配置会丢失
                await self.connect(
                    name,
                    target_uri,
                    headers,
                    is_retry=True,
                    connection_info=connection_info,
                )
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket管理器重连执行失败 {name}: {e}")
                pass

        self.reconnect_tasks[name] = asyncio.create_task(reconnect())

    async def disconnect(self, name: str):
        """断开连接"""
        if name in self.connections:
            try:
                await self.connections[name].close()
                logger.info(f"[灾害预警] WebSocket连接已关闭: {name}")
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket断开连接时出错 {name}: {e}")
            finally:
                self.connections.pop(name, None)
                self.connection_info.pop(name, None)

        if name in self.reconnect_tasks:
            self.reconnect_tasks[name].cancel()
            self.reconnect_tasks.pop(name, None)

    async def send_message(self, name: str, message: str):
        """发送消息"""
        if name in self.connections:
            try:
                await self.connections[name].send_str(message)
                logger.debug(f"[灾害预警] 消息已发送到 {name}: {message[:100]}...")
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket管理器发送消息失败 {name}: {e}")
        else:
            logger.warning(f"[灾害预警] WebSocket管理器尝试发送到未连接的连接: {name}")

    def get_connection_status(self, name: str) -> dict[str, Any]:
        """获取连接状态信息"""
        status = {
            "connected": name in self.connections and not self.connections[name].closed,
            "retry_count": self.connection_retry_counts.get(name, 0),
            "has_handler": name in self.message_handlers,
        }

        if name in self.connection_info:
            info = self.connection_info[name]
            status.update(
                {
                    "uri": info.get("uri"),
                    "established_time": info.get("established_time"),
                    "connection_type": info.get("connection_type"),
                }
            )

        return status

    def get_all_connections_status(self) -> dict[str, dict[str, Any]]:
        """获取所有连接的状态信息"""
        return {
            name: self.get_connection_status(name)
            for name in self.connection_info.keys()
        }

    async def start(self):
        """启动管理器"""
        self.running = True

        # 初始化 Shared Session
        if not self.session or self.session.closed:
            # 复用 http_timeout 配置
            timeout = aiohttp.ClientTimeout(total=self.config.get("http_timeout", 30))
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("[灾害预警] WebSocket管理器已启动")

        if not self.message_handlers:
            logger.warning("[灾害预警] 没有注册任何消息处理器")

    async def stop(self):
        """停止管理器"""
        logger.info("[灾害预警] WebSocket管理器正在停止...")
        self.running = False

        # 取消所有重连任务
        for task in self.reconnect_tasks.values():
            task.cancel()

        # 断开所有连接
        for name in list(self.connections.keys()):
            await self.disconnect(name)

        # 关闭 Session
        if self.session:
            await self.session.close()
            self.session = None

        # 清理所有状态
        self.connections.clear()
        self.connection_info.clear()
        self.connection_retry_counts.clear()
        self.fallback_retry_counts.clear()

        logger.info("[灾害预警] WebSocket管理器已停止")

    def _find_handler_by_prefix(self, connection_name: str) -> str | None:
        """通过前缀匹配查找处理器名称"""
        # 定义连接名称前缀到处理器名称的映射
        prefix_mappings = {
            "fan_studio_all": "fan_studio",  # 明确匹配 /all 连接
            "p2p_": "p2p",
            "wolfx_": "wolfx",
            "global_quake": "global_quake",
        }

        # 尝试前缀匹配
        for prefix, handler_name in prefix_mappings.items():
            if connection_name.startswith(prefix):
                # 验证处理器确实存在
                if handler_name in self.message_handlers:
                    return handler_name
                else:
                    logger.warning(
                        f"[灾害预警] 前缀匹配找到但处理器不存在: '{connection_name}' -> '{handler_name}'"
                    )

        # 如果没有找到匹配，尝试更宽松的前缀匹配
        for handler_name in self.message_handlers.keys():
            if connection_name.startswith(handler_name):
                return handler_name

        return None


class HTTPDataFetcher:
    """HTTP数据获取器"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.get("http_timeout", 30))
        )
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, exc_tb=None):
        if self.session:
            await self.session.close()

    async def fetch_json(self, url: str, headers: dict | None = None) -> dict | None:
        """获取JSON数据"""
        if not self.session:
            return None

        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"[灾害预警] HTTP请求失败 {url}: {response.status}")
        except Exception as e:
            logger.error(f"[灾害预警] HTTP请求异常 {url}: {e}")

        return None
