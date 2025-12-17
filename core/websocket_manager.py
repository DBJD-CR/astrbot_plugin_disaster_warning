"""
WebSocket连接管理器
适配数据处理器架构，提供更好的错误处理和重连机制
"""

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

import aiohttp
import websockets

from astrbot.api import logger


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self, config: dict[str, Any], message_logger=None):
        self.config = config
        self.message_logger = message_logger
        self.connections: dict[str, websockets.WebSocketServerProtocol] = {}
        self.message_handlers: dict[str, Callable] = {}
        self.reconnect_tasks: dict[str, asyncio.Task] = {}
        self.connection_retry_counts: dict[str, int] = {}
        self.connection_info: dict[str, dict] = {}  # 新增：存储连接信息
        self.running = False

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
        """建立WebSocket连接 - 增强版本"""
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
                max_retries = self.config.get("max_reconnect_retries", 3)
                logger.info(
                    f"[灾害预警] 尝试重连 {name} (尝试 {current_retry}/{max_retries})"
                )
            else:
                logger.info(f"[灾害预警] 正在连接 {name}: {uri}")
                # 首次连接时重置重试计数
                self.connection_retry_counts[name] = 0

            # 增强的连接配置
            connect_kwargs = {
                "uri": uri,
                "ping_interval": self.config.get("heartbeat_interval", 60),
                "ping_timeout": self.config.get("connection_timeout", 10),
                "close_timeout": self.config.get("close_timeout", 10),
                "max_size": self.config.get("max_message_size", 2**20),  # 1MB默认
            }

            # 只有在有headers时才添加
            if headers:
                connect_kwargs["extra_headers"] = headers

            # 添加SSL配置（如果需要）
            if self.config.get("ssl_verify", True) is False:
                connect_kwargs["ssl"] = False

            async with websockets.connect(**connect_kwargs) as websocket:
                self.connections[name] = websocket
                self.connection_info[name]["established_time"] = (
                    asyncio.get_event_loop().time()
                )
                logger.info(f"[灾害预警] WebSocket连接成功: {name}")
                # 连接成功，重置重试计数
                self.connection_retry_counts[name] = 0

                # 处理消息
                async for message in websocket:
                    try:
                        # 记录原始消息 - 适配消息记录器
                        if self.message_logger:
                            try:
                                # 尝试使用消息记录器格式
                                self.message_logger.log_raw_message(
                                    source=f"websocket_{name}",
                                    message_type="websocket_message",
                                    raw_data=message,
                                    connection_info={
                                        "url": uri,
                                        "connection_type": "websocket",
                                        "handler": self._get_handler_name_for_connection(
                                            name
                                        ),
                                        **self.connection_info[name],
                                    },
                                )
                            except (TypeError, AttributeError):
                                # 向后兼容：旧的消息记录器格式
                                try:
                                    self.message_logger.log_websocket_message(
                                        name, message, uri
                                    )
                                except Exception as e:
                                    logger.warning(f"[灾害预警] 消息记录失败: {e}")

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
                        logger.error(f"[灾害预警] 处理消息时出错 {name}: {e}")
                        logger.error(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

                        # 增强的错误处理：根据错误类型决定是否重连
                        if self._should_reconnect_on_error(e):
                            await self._schedule_reconnect(name, uri, headers)

        except Exception as e:
            # 增强的错误分析和日志
            error_msg = str(e)
            error_type = type(e).__name__

            # 记录详细的错误信息
            logger.error(f"[灾害预警] 连接失败 {name}: {error_type} - {error_msg}")

            # 分类处理不同类型的错误
            if "1012" in error_msg and "service restart" in error_msg:
                logger.warning(f"[灾害预警] 收到服务重启通知 {name}")
                logger.info(f"[灾害预警] {name} 服务器正在重启，将在稍后自动重连")
            elif "HTTP 502" in error_msg or "HTTP 503" in error_msg:
                logger.warning(f"[灾害预警] 服务器网关错误 {name}")
                logger.info(f"[灾害预警] {name} 服务器可能正在维护")
            elif "connection refused" in error_msg.lower():
                logger.warning(f"[灾害预警] 连接被拒绝 {name}")
                logger.info(f"[灾害预警] {name} 服务器可能暂时不可用")
            elif "timeout" in error_msg.lower():
                logger.warning(f"[灾害预警] 连接超时 {name}")
                logger.info(f"[灾害预警] {name} 连接超时，将稍后重试")
            elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                logger.warning(f"[灾害预警] SSL证书问题 {name}")
                logger.info("[灾害预警] 请检查SSL配置或服务器证书")
            else:
                logger.error(f"[灾害预警] 未知错误 {name}: {error_msg}")

            # 清理连接信息
            self.connections.pop(name, None)
            self.connection_info.pop(name, None)

            # 启动重连任务
            if self.running:
                await self._schedule_reconnect(name, uri, headers)

    def _should_reconnect_on_error(self, error: Exception) -> bool:
        """判断遇到错误时是否应该重连"""
        error_msg = str(error).lower()

        # 这些错误类型值得重试
        reconnect_errors = [
            "timeout",
            "connection reset",
            "connection refused",
            "broken pipe",
            "eof occurred",
            "websocket connection closed",
        ]

        for error_type in reconnect_errors:
            if error_type in error_msg:
                return True

        # SSL错误通常不需要重试（配置问题）
        if "ssl" in error_msg or "certificate" in error_msg:
            return False

        # 认证错误不需要重试
        if "401" in error_msg or "403" in error_msg:
            return False

        return True

    def _get_handler_name_for_connection(self, connection_name: str) -> str:
        """获取连接对应的处理器名称"""
        # 定义连接名称前缀到处理器名称的映射
        prefix_mappings = {
            "fan_studio_": "fan_studio",
            "p2p_": "p2p",
            "wolfx_": "wolfx",
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
        self, name: str, uri: str, headers: dict | None = None
    ):
        """计划重连 - 增强版本，支持备用服务器"""
        if name in self.reconnect_tasks:
            self.reconnect_tasks[name].cancel()

        async def reconnect():
            # 获取当前重试次数和最大重试次数
            current_retry = self.connection_retry_counts.get(name, 0)
            max_retries = self.config.get("max_reconnect_retries", 3)

            # 检查是否已达到最大重试次数
            if current_retry >= max_retries * 2:  # 主备服务器各尝试max_retries次
                logger.error(
                    f"[灾害预警] {name} 重连失败，主备服务器均已达到最大重试次数，将停止重连"
                )
                return

            # 获取备用服务器URL
            backup_url = None
            if name in self.connection_info:
                backup_url = self.connection_info[name].get("backup_url")

            # 判断使用主服务器还是备用服务器
            # 每尝试 max_retries 次后切换服务器
            use_backup = backup_url and (current_retry >= max_retries)
            target_uri = backup_url if use_backup else uri

            # 计算重试次数（在当前服务器上的尝试次数）
            server_retry_count = current_retry % max_retries if use_backup else current_retry

            # 固定5秒等待后重试
            delay = 5

            server_type = "备用服务器" if use_backup else "主服务器"
            logger.info(
                f"[灾害预警] {name} 将在 {delay} 秒后尝试连接{server_type}: {target_uri}"
            )

            try:
                await asyncio.sleep(delay)
                # 标记为重试连接
                await self.connect(name, target_uri, headers, is_retry=True)
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket管理器重连失败 {name}: {e}")
                # 如果还有重试次数，继续安排重连（回到主服务器URI以便下次判断）
                if self.connection_retry_counts.get(name, 0) < max_retries * 2:
                    await self._schedule_reconnect(name, uri, headers)

        self.reconnect_tasks[name] = asyncio.create_task(reconnect())


    async def disconnect(self, name: str):
        """断开连接 - 增强版本"""
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
        """发送消息 - 增强版本"""
        if name in self.connections:
            try:
                await self.connections[name].send(message)
                logger.debug(f"[灾害预警] 消息已发送到 {name}: {message[:100]}...")
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket管理器发送消息失败 {name}: {e}")
                # 可以在这里实现消息重试机制
        else:
            logger.warning(f"[灾害预警] WebSocket管理器尝试发送到未连接的连接: {name}")

    def get_connection_status(self, name: str) -> dict[str, Any]:
        """获取连接状态信息"""
        status = {
            "connected": name in self.connections,
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
        """启动管理器 - 增强版本"""
        self.running = True

        # 可以在这里添加初始化检查
        if not self.message_handlers:
            logger.warning("[灾害预警] 没有注册任何消息处理器")

    async def stop(self):
        """停止管理器 - 增强版本"""
        logger.info("[灾害预警] WebSocket管理器正在停止...")
        self.running = False

        # 取消所有重连任务
        for task in self.reconnect_tasks.values():
            task.cancel()

        # 断开所有连接
        for name in list(self.connections.keys()):
            await self.disconnect(name)

        # 清理所有状态
        self.connections.clear()
        self.connection_info.clear()
        self.connection_retry_counts.clear()

        logger.info("[灾害预警] WebSocket管理器已停止")

    def _find_handler_by_prefix(self, connection_name: str) -> str | None:
        """通过前缀匹配查找处理器名称 - 增强版本"""
        # 定义连接名称前缀到处理器名称的映射
        prefix_mappings = {
            "fan_studio_": "fan_studio",
            "p2p_": "p2p",
            "wolfx_": "wolfx",
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


# 保持向后兼容的别名
WebSocketManager = WebSocketManager


class HTTPDataFetcher:
    """HTTP数据获取器 - 保持不变"""

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


class GlobalQuakeClient:
    """Global Quake TCP客户端 - 保持不变"""

    def __init__(self, config: dict[str, Any], message_logger=None):
        self.config = config
        self.message_logger = message_logger

        # 服务器配置
        self.primary_server = config.get("primary_server", "server-backup.globalquake.net")
        self.secondary_server = config.get("secondary_server", "server-backup.globalquake.net")
        self.primary_port = config.get("primary_port", 38000)
        self.secondary_port = config.get("secondary_port", 38000)


        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.running = False
        self.message_handler: Callable | None = None

    def register_handler(self, handler: Callable):
        """注册消息处理器"""
        self.message_handler = handler

    async def connect(self):
        """连接到Global Quake服务器"""
        servers = [
            (self.primary_server, self.primary_port),
            (self.secondary_server, self.secondary_port),
        ]

        for server, port in servers:
            try:
                logger.info(f"[灾害预警] 正在连接Global Quake服务器 {server}:{port}")
                self.reader, self.writer = await asyncio.open_connection(server, port)
                logger.info(f"[灾害预警] Global Quake 服务器连接成功: {server}:{port}")
                return True
            except Exception as e:
                logger.error(
                    f"[灾害预警] Global Quake服务器连接失败 {server}:{port}: {e}"
                )

        return False

    async def listen(self):
        """监听消息"""
        if not self.reader or not self.writer:
            return

        self.running = True

        try:
            while self.running:
                data = await self.reader.readline()
                if not data:
                    break

                message = data.decode("utf-8").strip()
                if message and self.message_handler:
                    try:
                        logger.info(
                            f"[灾害预警] Global Quake收到原始消息: {message[:128]}..."
                        )

                        # 记录原始消息
                        if self.message_logger:
                            try:
                                self.message_logger.log_tcp_message(
                                    self.writer.get_extra_info("peername")[0]
                                    if self.writer
                                    else "unknown",
                                    self.writer.get_extra_info("peername")[1]
                                    if self.writer
                                    else 0,
                                    message,
                                )
                            except Exception as e:
                                logger.warning(
                                    f"[灾害预警] Global Quake消息记录失败: {e}"
                                )

                        await self.message_handler(message)
                    except Exception as e:
                        logger.error(f"[灾害预警] 处理Global Quake消息时出错: {e}")

        except asyncio.CancelledError:
            logger.info("[灾害预警] Global Quake监听任务被取消")
        except Exception as e:
            logger.error(f"[灾害预警] Global Quake监听异常: {e}")
        finally:
            await self.disconnect()

    async def disconnect(self):
        """断开连接"""
        self.running = False

        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.error(f"[灾害预警] 断开Global Quake连接时出错: {e}")
            finally:
                self.writer = None
                self.reader = None

    async def send_message(self, message: str):
        """发送消息"""
        if self.writer:
            try:
                self.writer.write(message.encode("utf-8"))
                await self.writer.drain()
            except Exception as e:
                logger.error(f"[灾害预警] 发送Global Quake消息失败: {e}")
