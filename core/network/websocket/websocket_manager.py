"""
WebSocket 连接管理器。
负责维护连接状态、消息处理器、重连任务、心跳任务与共享会话，
并把生命周期、分发、重连等细节委托给独立服务实现。
"""

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from aiohttp import ClientWebSocketResponse

from astrbot.api import logger

from .websocket_dispatch_service import WebSocketDispatchService
from .websocket_reconnect_service import WebSocketReconnectService
from .websocket_runtime_service import WebSocketRuntimeService


class WebSocketManager:
    """WebSocket 连接管理器。"""

    def __init__(self, config: dict[str, Any], message_logger=None, telemetry=None):
        # 共享配置与日志、遥测工具依赖注入
        self.config = config
        self.message_logger = message_logger
        self._telemetry = telemetry

        # 共享状态维护
        self.connections: dict[str, ClientWebSocketResponse] = {}
        self.message_handlers: dict[str, Callable] = {}
        self.reconnect_tasks: dict[str, asyncio.Task] = {}
        self.connection_retry_counts: dict[str, int] = {}
        self.fallback_retry_counts: dict[str, int] = {}  # 兜底重试计数
        self.connection_info: dict[str, dict] = {}  # 存放连接 URI, header 等元数据
        self.running = False
        self.session: aiohttp.ClientSession | None = None
        self.heartbeat_tasks: dict[str, asyncio.Task] = {}  # 保活协程任务集合
        self.last_heartbeat_time: dict[str, float] = {}  # 上一次接收到数据的时间戳
        self._stop_lock = asyncio.Lock()
        self._stopping = False
        self._offline_notify_callback: (
            Callable[[dict[str, Any]], Awaitable[None]] | None
        ) = None

        # 实例化委托服务，保持高内聚低耦合
        self._reconnect_service = WebSocketReconnectService(self)
        self._runtime_service = WebSocketRuntimeService(self)
        self._dispatch_service = WebSocketDispatchService(self)

    def register_handler(self, connection_name: str, handler: Callable):
        """注册指定连接前缀对应的消息处理器。"""
        self.message_handlers[connection_name] = handler
        logger.debug(f"[灾害预警] 注册处理器: {connection_name}")

    async def connect(
        self,
        name: str,
        uri: str,
        headers: dict | None = None,
        is_retry: bool = False,
        connection_info: dict[str, Any] | None = None,
    ):
        """建立 WebSocket 连接并托管整个会话生命周期。"""
        # 复用 aiohttp 会话，保证连接池管理更合理
        if not self.session or self.session.closed:
            logger.warning(f"[灾害预警] WebSocket会话未就绪，正在重新初始化: {name}")
            if self.session and not self.session.closed:
                try:
                    await self.session.close()
                except Exception:
                    pass
            # 引入全局超时配置
            timeout_val = self.config.get("http_timeout", 30)
            timeout = aiohttp.ClientTimeout(total=timeout_val)
            self.session = aiohttp.ClientSession(timeout=timeout)

        try:
            # 记录连接参数以便重连或状态上报
            self.connection_info[name] = {
                "uri": uri,
                "headers": headers,
                "connection_type": "websocket",
                "established_time": None,
                "retry_count": 0,
                **(connection_info or {}),
            }

            # 递增重试次数
            if is_retry:
                current_retry = self.connection_retry_counts.get(name, 0) + 1
                self.connection_retry_counts[name] = current_retry
            else:
                logger.debug(f"[灾害预警] 正在连接 {name}")
                self.connection_retry_counts[name] = 0

            # 统一配置建连的超时时间及负载限制
            conn_timeout = self.config.get("connection_timeout", 30)
            connect_kwargs = {
                "url": uri,
                "headers": headers or {},
                "heartbeat": self.config.get("heartbeat_interval", 60),
                "timeout": conn_timeout,  # aiohttp 握手超时限制
                "max_msg_size": self.config.get(
                    "max_message_size", 2**20
                ),  # 默认 1MB 限制
            }

            # 按需取消证书校验
            if self.config.get("ssl_verify", True) is False:
                connect_kwargs["ssl"] = False

            # 外挂一层超时保护，防止 DNS 解析或三次握手长久卡死
            websocket = await asyncio.wait_for(
                self.session.ws_connect(**connect_kwargs),
                timeout=conn_timeout + 5,
            )

            # 建连成功，记录状态并注册生命周期及心跳协程
            async with websocket:
                self.connections[name] = websocket
                self.connection_info[name]["established_time"] = (
                    asyncio.get_running_loop().time()
                )
                self.connection_info[name].pop("offline_since", None)
                self.connection_info[name].pop("short_retry_notified", None)
                logger.info(f"[灾害预警] WebSocket连接成功: {name}")

                # 重置重连相关的状态变量
                self.connection_retry_counts[name] = 0
                self.fallback_retry_counts[name] = 0
                self.last_heartbeat_time[name] = asyncio.get_running_loop().time()

                # 启动后台应用层心跳保活协程
                self.heartbeat_tasks[name] = asyncio.create_task(
                    self._heartbeat_loop(name, websocket)
                )

                # 开启并阻塞在消息循环派发服务中，直到断开
                await self._dispatch_service.handle_connection_session(
                    name=name,
                    uri=uri,
                    headers=headers,
                    websocket=websocket,
                )

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # 常见网络错误或握手超时，走重试容灾逻辑
            logger.warning(f"[灾害预警] 连接中断或失败 {name}: {e}")
            self._handle_connection_error(name, uri, headers, e)

        except asyncio.CancelledError:
            # 主动关闭或插件卸载引发的任务取消，不做额外处理，正常退出
            logger.info(f"[灾害预警] WebSocket连接任务被取消: {name}")
            self.connections.pop(name, None)
            self.connection_info.pop(name, None)
            raise
        except Exception as e:
            # 非预期类型错误，上报异常遥测
            logger.error(f"[灾害预警] 未知连接错误 {name}: {type(e).__name__} - {e}")
            logger.debug(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")
            if self._telemetry and self._telemetry.enabled:
                asyncio.create_task(
                    self._telemetry.track_error(
                        e, module=f"core.websocket_manager.connect.{name}"
                    )
                )
            self._handle_connection_error(name, uri, headers, e)

    def _log_message(self, name: str, message: Any, uri: str):
        """记录消息的辅助入口。"""
        self._dispatch_service.log_message(name, message, uri)

    def _handle_connection_error(
        self, name: str, uri: str, headers: dict | None, error: Exception
    ):
        """统一分发连接错误处理。"""
        self._reconnect_service.handle_connection_error(name, uri, headers, error)

    def _is_critical_error(self, error: Exception) -> bool:
        """判断是否属于需要立即切换兜底策略的关键错误。"""
        return self._reconnect_service.is_critical_error(error)

    def _get_handler_name_for_connection(self, connection_name: str) -> str:
        """获取连接名对应的处理器名称。"""
        return self._dispatch_service.get_handler_name_for_connection(connection_name)

    async def _schedule_reconnect(
        self,
        name: str,
        uri: str,
        headers: dict | None = None,
        connection_info: dict[str, Any] | None = None,
        force_fallback: bool = False,
    ):
        """按统一重连策略安排一次后续重连。"""
        await self._reconnect_service.schedule_reconnect(
            name,
            uri,
            headers,
            connection_info,
            force_fallback=force_fallback,
        )

    async def _heartbeat_loop(self, name: str, websocket: ClientWebSocketResponse):
        """运行应用层心跳循环。"""
        await self._runtime_service.heartbeat_loop(name, websocket)

    async def force_reconnect(self, name: str) -> bool:
        """强制立即重连指定连接，跳过原有等待队列。"""
        # 若已有健康连接，没必要强行断开
        if name in self.connections and not self.connections[name].closed:
            return False

        # 取消已处于等待计时队列中的待执行重试任务，避免竞争
        if name in self.reconnect_tasks:
            task = self.reconnect_tasks[name]
            if not task.done():
                task.cancel()
                logger.debug(f"[灾害预警] 取消了 {name} 正在等待的重连任务 (强制重连)")
            self.reconnect_tasks.pop(name, None)

        # 检查是否保留了该连接的配置元信息
        info = self.connection_info.get(name)
        if not info:
            logger.warning(f"[灾害预警] 无法重连 {name}: 找不到连接信息")
            return False

        uri = info.get("uri")
        headers = info.get("headers")

        # 手动重连开始，所有失败统计和时间标记必须置空
        self.connection_retry_counts[name] = 0
        self.fallback_retry_counts[name] = 0
        info.pop("offline_since", None)
        info.pop("short_retry_notified", None)

        logger.info(f"[灾害预警] 正在手动重连 {name}...")

        # 异步启动物理连接，不卡死调用线程
        asyncio.create_task(
            self.connect(
                name,
                uri,
                headers,
                is_retry=False,
                connection_info=info,
            )
        )
        return True

    async def disconnect(self, name: str):
        """断开指定连接。"""
        await self._runtime_service.disconnect(name)

    async def send_message(self, name: str, message: str):
        """向指定连接发送文本消息。"""
        if name in self.connections:
            try:
                await self.connections[name].send_str(message)
            except Exception as e:
                logger.error(
                    f"[灾害预警] WebSocket 管理器向 {name} 发送消息失败，错误为 {e}"
                )
        else:
            logger.warning(f"[灾害预警] WebSocket 管理器尝试向未连接的 {name} 发送消息")

    def get_connection_status(self, name: str) -> dict[str, Any]:
        """获取单个连接的状态摘要。"""
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

        # 最近活跃时间可辅助管理端判断连接是否假活跃。
        if name in self.last_heartbeat_time:
            status["last_active"] = self.last_heartbeat_time[name]

        return status

    def get_all_connections_status(self) -> dict[str, dict[str, Any]]:
        """获取全部连接的状态摘要。"""
        return {
            name: self.get_connection_status(name)
            for name in self.connection_info.keys()
        }

    async def start(self):
        """启动管理器。"""
        await self._runtime_service.start()

    async def _cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        await self._runtime_service.cancel_and_wait(tasks)

    async def stop(self):
        """停止管理器。"""
        await self._runtime_service.stop()

    def set_offline_notify_callback(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        """设置离线通知回调。"""
        self._offline_notify_callback = callback

    def _emit_offline_notification(
        self,
        connection_name: str,
        stage: str,
        reason: str,
        next_retry_in: str | None = None,
        retry_count: int | None = None,
        fallback_count: int | None = None,
    ) -> None:
        """以异步安全方式触发离线通知回调。"""
        self._reconnect_service.emit_offline_notification(
            connection_name=connection_name,
            stage=stage,
            reason=reason,
            next_retry_in=next_retry_in,
            retry_count=retry_count,
            fallback_count=fallback_count,
        )

    def _find_handler_by_prefix(self, connection_name: str) -> str | None:
        """按连接名前缀匹配处理器名称。"""
        return self._dispatch_service.find_handler_by_prefix(connection_name)


class HTTPDataFetcher:
    """HTTP 数据获取器。"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        # 采用 session 上下文模式，每次 fetch 使用完自动回收套接字资源，防止连接池泄漏
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.get("http_timeout", 30))
        )
        return self

    async def __aexit__(self, exc_type=None, exc_val=None, exc_tb=None):
        await self.close()

    async def close(self):
        """显式关闭会话。"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_json(self, url: str, headers: dict | None = None) -> dict | None:
        """获取 JSON 数据。"""
        if not self.session:
            return None

        try:
            # 异步拉取 HTTP 接口
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"[灾害预警] HTTP请求失败 {url}: {response.status}")
        except Exception as e:
            logger.error(f"[灾害预警] HTTP请求异常 {url}: {e}")

        return None
