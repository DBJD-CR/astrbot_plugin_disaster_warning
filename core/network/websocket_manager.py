"""
WebSocket连接管理器
适配数据处理器架构，提供更好的错误处理和重连机制
(已迁移至 aiohttp 实现以获得更好的跨平台兼容性)
"""

import asyncio
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType

from astrbot.api import logger


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self, config: dict[str, Any], message_logger=None, telemetry=None):
        self.config = config
        self.message_logger = message_logger
        self._telemetry = telemetry
        self.connections: dict[str, ClientWebSocketResponse] = {}
        self.message_handlers: dict[str, Callable] = {}
        self.reconnect_tasks: dict[str, asyncio.Task] = {}
        self.connection_retry_counts: dict[str, int] = {}
        self.fallback_retry_counts: dict[str, int] = {}  # 兜底重试计数
        self.connection_info: dict[str, dict] = {}  # 新增：存储连接信息
        self.running = False
        self.session: aiohttp.ClientSession | None = None
        self.heartbeat_tasks: dict[str, asyncio.Task] = {}  # 心跳任务
        self.last_heartbeat_time: dict[str, float] = {}  # 最后心跳时间
        self._stop_lock = asyncio.Lock()
        self._stopping = False
        self._offline_notify_callback: (
            Callable[[dict[str, Any]], Awaitable[None]] | None
        ) = None

    def register_handler(self, connection_name: str, handler: Callable):
        """注册消息处理器"""
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
        """建立WebSocket连接 - aiohttp版本

        Args:
            name: 连接名称
            uri: WebSocket URI
            headers: 可选的HTTP头
            is_retry: 是否为重试连接
            connection_info: 可选的连接元数据（如 backup_url 等）
        """
        # 确保 session 存在
        if not self.session or self.session.closed:
            logger.warning(f"[灾害预警] WebSocket会话未就绪，正在重新初始化: {name}")
            if self.session and not self.session.closed:
                try:
                    await self.session.close()
                except Exception:
                    pass
            # 复用 http_timeout 配置
            timeout_val = self.config.get("http_timeout", 30)
            timeout = aiohttp.ClientTimeout(total=timeout_val)
            self.session = aiohttp.ClientSession(timeout=timeout)

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
                logger.debug(f"[灾害预警] 正在连接 {name}")
                # 首次连接时重置重试计数
                self.connection_retry_counts[name] = 0

            # aiohttp ws_connect 配置
            conn_timeout = self.config.get("connection_timeout", 30)
            connect_kwargs = {
                "url": uri,
                "headers": headers or {},
                "heartbeat": self.config.get("heartbeat_interval", 60),
                "timeout": conn_timeout,  # aiohttp 内部握手超时
                "max_msg_size": self.config.get("max_message_size", 2**20),  # 1MB默认
            }

            # 添加SSL配置（如果需要）
            if self.config.get("ssl_verify", True) is False:
                connect_kwargs["ssl"] = False

            # 显式使用 wait_for 包裹连接过程，确保不被卡死
            # 注意：ws_connect 返回的是一个 ClientWebSocketResponse，它是一个异步上下文管理器
            # 但 wait_for 返回的是 ws_connect 的结果（即 ClientWebSocketResponse 对象）
            # 所以我们需要先获取 websocket 对象，然后再使用 async with 管理它
            websocket = await asyncio.wait_for(
                self.session.ws_connect(**connect_kwargs),
                timeout=conn_timeout + 5,  # 略大于内部超时
            )

            async with websocket:
                self.connections[name] = websocket
                self.connection_info[name]["established_time"] = (
                    asyncio.get_running_loop().time()
                )
                logger.info(f"[灾害预警] WebSocket连接成功: {name}")
                # 连接成功，重置所有重试计数
                self.connection_retry_counts[name] = 0
                self.fallback_retry_counts[name] = 0
                self.last_heartbeat_time[name] = asyncio.get_running_loop().time()

                # 启动心跳任务
                self.heartbeat_tasks[name] = asyncio.create_task(
                    self._heartbeat_loop(name, websocket)
                )

                try:
                    # 处理消息 - aiohttp 风格
                    async for msg in websocket:
                        if msg.type == WSMsgType.TEXT:
                            message = msg.data
                            self.last_heartbeat_time[name] = (
                                asyncio.get_running_loop().time()
                            )  # 更新心跳时间
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
                                # 注：使用 Exception 是安全的，KeyboardInterrupt/SystemExit 继承自 BaseException 不会被捕获
                                logger.error(f"[灾害预警] 消息处理错误 {name}: {e}")
                                logger.debug(
                                    f"[灾害预警] 异常堆栈: {traceback.format_exc()}"
                                )

                        elif msg.type == WSMsgType.BINARY:
                            message = msg.data  # bytes
                            self.last_heartbeat_time[name] = (
                                asyncio.get_running_loop().time()
                            )
                            try:
                                # 记录二进制消息（由 message_logger 输出安全摘要）
                                if self.message_logger:
                                    self._log_message(name, message, uri)

                                # 智能处理器查找（支持前缀匹配）
                                handler_name = self._find_handler_by_prefix(name)

                                if handler_name:
                                    # 传递二进制数据给处理器
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
                                logger.error(
                                    f"[灾害预警] 二进制消息处理错误 {name}: {e}"
                                )
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

                        elif msg.type == WSMsgType.PING:
                            self.last_heartbeat_time[name] = (
                                asyncio.get_running_loop().time()
                            )

                        elif msg.type == WSMsgType.PONG:
                            self.last_heartbeat_time[name] = (
                                asyncio.get_running_loop().time()
                            )

                    # 精细化处理 WebSocket 关闭代码
                    if websocket.close_code is not None:
                        close_code = websocket.close_code

                        # 正常关闭代码（不需要重连）
                        normal_close_codes = {
                            1000,  # Normal Closure - 正常关闭
                            1001,  # Going Away - 服务器/客户端正常离开
                        }

                        # 不应重连的关闭代码（协议/认证错误）
                        no_reconnect_codes = {
                            1002,  # Protocol Error - 协议错误
                            1003,  # Unsupported Data - 不支持的数据类型
                            1007,  # Invalid Frame Payload Data - 无效的帧数据
                            1008,  # Policy Violation - 策略违规
                            1009,  # Message Too Big - 消息过大
                            1010,  # Mandatory Extension - 必需的扩展
                            1011,  # Internal Server Error - 服务器内部错误
                        }

                        # 特殊处理的关闭代码
                        if close_code in normal_close_codes:
                            # 正常关闭，不触发异常
                            logger.info(
                                f"[灾害预警] WebSocket正常关闭: {name}, code={close_code}"
                            )
                        elif close_code in no_reconnect_codes:
                            # 协议/配置错误，不应该重连
                            raise Exception(
                                f"WebSocket协议错误关闭（不重连），代码 {close_code}"
                            )
                        elif close_code == 1006:
                            # Abnormal Closure - 异常关闭（连接意外断开）
                            # 这是最常见的网络故障，应该重连
                            raise Exception(
                                f"WebSocket异常关闭（连接中断），代码 {close_code}"
                            )
                        else:
                            # 其他未知关闭代码，尝试重连
                            raise Exception(f"WebSocket意外关闭，代码 {close_code}")

                except asyncio.CancelledError:
                    # 任务被取消，正常传播（不在此处记录，交由外层统一记录）
                    raise
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

        except asyncio.CancelledError:
            # 任务被取消（通常在 stop() 时），不触发重连
            logger.info(f"[灾害预警] WebSocket连接任务被取消: {name}")
            self.connections.pop(name, None)
            self.connection_info.pop(name, None)
            raise  # 正常传播取消信号
        except Exception as e:
            logger.error(f"[灾害预警] 未知连接错误 {name}: {type(e).__name__} - {e}")
            logger.debug(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")
            # 上报未知 WebSocket 错误到遥测
            if self._telemetry and self._telemetry.enabled:
                asyncio.create_task(
                    self._telemetry.track_error(
                        e, module=f"core.websocket_manager.connect.{name}"
                    )
                )
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
        if name in self.heartbeat_tasks:
            self.heartbeat_tasks[name].cancel()
            self.heartbeat_tasks.pop(name, None)

        # 获取连接信息（不移除，保持在列表中显示为离线状态）
        connection_info = self.connection_info.get(name, {})

        # 启动重连任务
        if not self.running:
            return

        # 检查是否是致命错误（SSL等配置错误），这种情况下停止重连
        error_msg = str(error).lower()
        if "ssl" in error_msg or "certificate" in error_msg:
            logger.warning(f"[灾害预警] {name} 遇到SSL配置错误，停止重连: {error}")
            self._emit_offline_notification(
                connection_name=name,
                stage="stop",
                reason=f"SSL/证书错误: {error}",
                retry_count=self.connection_retry_counts.get(name, 0),
                fallback_count=self.fallback_retry_counts.get(name, 0),
            )
            return

        # 检查是否是关键错误（认证、协议错误等），这种情况下直接进入兜底重连
        force_fallback = self._is_critical_error(error)
        if force_fallback:
            logger.warning(
                f"[灾害预警] {name} 遇到关键错误，将直接进入兜底重连阶段: {error}"
            )

        # 避免同一连接并发创建多个重连任务
        existing_task = self.reconnect_tasks.get(name)
        if existing_task and not existing_task.done():
            logger.debug(f"[灾害预警] {name} 已有正在运行的重连任务，跳过重复创建")
            return

        reconnect_task = asyncio.create_task(
            self._schedule_reconnect(
                name, uri, headers, connection_info, force_fallback=force_fallback
            ),
            name=f"dw_reconnect_{name}",
        )
        self.reconnect_tasks[name] = reconnect_task

    def _is_critical_error(self, error: Exception) -> bool:
        """判断是否为关键错误（需要直接进入兜底重连）

        Args:
            error: 捕获到的异常对象

        Returns:
            bool: True 表示是关键错误，应跳过短时重连直接兜底
        """
        error_msg = str(error).lower()

        # 认证错误
        if "401" in error_msg or "403" in error_msg:
            return True

        # 协议错误关闭代码
        if "协议错误关闭（不重连）" in error_msg:
            return True

        return False

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
        connection_info: dict[str, Any] | None = None,
        force_fallback: bool = False,
    ):
        """计划重连 - 优化版本，基于配置的固定间隔

        Args:
            name: 连接名称
            uri: WebSocket URI
            headers: 可选的HTTP头
            connection_info: 从 _handle_connection_error 传递的连接元数据
            force_fallback: 是否强制进入兜底重试阶段
        """
        if not self.running:
            return

        try:
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

            # 如果强制兜底，将当前重试次数设置为最大值，以触发兜底逻辑
            if force_fallback:
                current_retry = total_max_retries
                # 更新计数器，确保后续逻辑一致
                self.connection_retry_counts[name] = total_max_retries

            if current_retry >= total_max_retries:
                # 短时重连次数用尽，检查是否启用兜底重试
                if not fallback_enabled:
                    logger.error(
                        f"[灾害预警] {name} 重连失败，已达到最大重试次数 ({total_max_retries})，停止重连"
                    )
                    self._emit_offline_notification(
                        connection_name=name,
                        stage="stop",
                        reason="短时重连次数已达上限且未启用兜底重试",
                        retry_count=current_retry,
                        fallback_count=current_fallback,
                    )
                    return

                # 检查兜底重试次数是否达到上限
                if fallback_max_count != -1 and current_fallback >= fallback_max_count:
                    logger.error(
                        f"[灾害预警] {name} 兜底重试失败，已达到最大兜底重试次数 ({fallback_max_count})，停止重连"
                    )
                    self._emit_offline_notification(
                        connection_name=name,
                        stage="stop",
                        reason="兜底重试次数已达上限",
                        retry_count=current_retry,
                        fallback_count=current_fallback,
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
                self._emit_offline_notification(
                    connection_name=name,
                    stage="fallback",
                    reason="短时重连失败，进入兜底重试",
                    next_retry_in=fallback_interval_display,
                    retry_count=current_retry,
                    fallback_count=self.fallback_retry_counts.get(name, 0),
                )

                await asyncio.sleep(fallback_interval)
                if not self.running:
                    return

                # 关键修改：在兜底重试时，不重置短时重连计数器
                # 这样如果这次连接失败，下次会继续进入兜底逻辑，而不是重新开始短时重连
                # self.connection_retry_counts[name] = 0  <-- 已移除

                logger.info(f"[灾害预警] {name} 开始兜底重试连接...")

                # 关键修复：在发起连接前，先清理当前任务记录
                # 这样如果 connect 失败并触发 _handle_connection_error，
                # 它能检测到当前没有任务在运行，从而创建新的重连任务
                self.reconnect_tasks.pop(name, None)

                await self.connect(
                    name,
                    uri,
                    headers,
                    is_retry=True,
                    connection_info=connection_info,
                )
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

            await asyncio.sleep(reconnect_interval)
            if not self.running:
                return

            # 标记为重试连接
            # 必须将 connection_info 传回去，否则下次重试时配置会丢失

            # 关键修复：在发起连接前，先清理当前任务记录
            self.reconnect_tasks.pop(name, None)

            await self.connect(
                name,
                target_uri,
                headers,
                is_retry=True,
                connection_info=connection_info,
            )
        except asyncio.CancelledError:
            logger.info(f"[灾害预警] {name} 重连任务被取消")
            raise
        except Exception as e:
            logger.error(f"[灾害预警] WebSocket管理器重连执行失败 {name}: {e}")
        finally:
            # 双重保险：如果任务还在字典里（比如 sleep 期间被取消），清理它
            current_task = self.reconnect_tasks.get(name)
            if current_task is asyncio.current_task():
                self.reconnect_tasks.pop(name, None)

    async def _heartbeat_loop(self, name: str, websocket: ClientWebSocketResponse):
        """应用层心跳循环"""
        interval = self.config.get("heartbeat_interval", 30)
        try:
            while True:
                await asyncio.sleep(interval)
                if websocket.closed:
                    break

                # 检查上次收到消息的时间
                last_time = self.last_heartbeat_time.get(name, 0)
                current_time = asyncio.get_running_loop().time()

                # 如果超过 2 倍心跳间隔没有收到任何消息（包括Pong），主动发送 Ping
                if current_time - last_time > interval * 2:
                    try:
                        logger.debug(f"[灾害预警] 发送应用层 Ping: {name}")
                        await websocket.ping()
                    except Exception as e:
                        logger.warning(f"[灾害预警] Ping 失败 {name}: {e}")
                        # Ping 失败通常意味着连接已断，抛出异常触发外层重连
                        await websocket.close(code=1001, message=b"Heartbeat timeout")
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[灾害预警] 心跳循环异常 {name}: {e}")

    async def force_reconnect(self, name: str) -> bool:
        """强制立即重连指定连接（跳过等待）

        Returns:
            bool: 是否触发了重连操作
        """
        # 1. 如果当前已连接且正常，跳过
        if name in self.connections and not self.connections[name].closed:
            return False

        # 2. 如果有正在等待的重连任务，取消它
        if name in self.reconnect_tasks:
            task = self.reconnect_tasks[name]
            if not task.done():
                task.cancel()
                logger.debug(f"[灾害预警] 取消了 {name} 正在等待的重连任务 (强制重连)")
            self.reconnect_tasks.pop(name, None)

        # 3. 获取连接信息
        info = self.connection_info.get(name)
        if not info:
            logger.warning(f"[灾害预警] 无法重连 {name}: 找不到连接信息")
            return False

        uri = info.get("uri")
        headers = info.get("headers")

        # 4. 重置重试计数，确保作为一次新的尝试
        self.connection_retry_counts[name] = 0
        self.fallback_retry_counts[name] = 0

        logger.info(f"[灾害预警] 正在手动重连 {name}...")

        # 5. 立即发起连接
        # 使用 create_task 避免阻塞当前调用者
        asyncio.create_task(
            self.connect(
                name,
                uri,
                headers,
                is_retry=False,  # 视为新连接，重置状态
                connection_info=info,
            )
        )
        return True

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
                if name in self.heartbeat_tasks:
                    self.heartbeat_tasks[name].cancel()
                    self.heartbeat_tasks.pop(name, None)

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

        # 添加最后心跳时间
        if name in self.last_heartbeat_time:
            status["last_active"] = self.last_heartbeat_time[name]

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
        self._stopping = False

        # 初始化 Shared Session
        if not self.session or self.session.closed:
            # 复用 http_timeout 配置
            timeout = aiohttp.ClientTimeout(total=self.config.get("http_timeout", 30))
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("[灾害预警] WebSocket管理器已启动")

        if not self.message_handlers:
            logger.warning("[灾害预警] 没有注册任何消息处理器")

    async def _cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        """停止管理器"""
        async with self._stop_lock:
            if self._stopping:
                logger.debug("[灾害预警] WebSocket管理器已在停止流程中，跳过重复调用")
                return
            self._stopping = True
            try:
                logger.info("[灾害预警] WebSocket管理器正在停止...")
                self.running = False

                # 取消并等待所有重连任务退出，避免停机后重连复活连接
                reconnect_tasks = list(self.reconnect_tasks.values())
                await self._cancel_and_wait(reconnect_tasks)
                self.reconnect_tasks.clear()

                # 取消所有心跳任务（防御性编程，确保没有遗漏）
                heartbeat_tasks = [
                    task
                    for task in self.heartbeat_tasks.values()
                    if task and not task.done()
                ]
                await self._cancel_and_wait(heartbeat_tasks)
                self.heartbeat_tasks.clear()

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
                self.last_heartbeat_time.clear()

                logger.info("[灾害预警] WebSocket管理器已停止")
            finally:
                self._stopping = False

    def set_offline_notify_callback(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    ) -> None:
        """设置离线通知回调"""
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
        """触发离线通知回调（异步安全）"""
        if not self._offline_notify_callback:
            return

        info = self.connection_info.get(connection_name, {})
        payload = {
            "connection_name": connection_name,
            "data_source": info.get("data_source")
            or info.get("connection_name")
            or "unknown",
            "stage": stage,
            "reason": reason,
            "next_retry_in": next_retry_in,
            "retry_count": retry_count,
            "fallback_count": fallback_count,
        }
        asyncio.create_task(self._offline_notify_callback(payload))

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
        await self.close()  # 调用显式的 close

    async def close(self):
        """显式关闭 Session"""
        if self.session and not self.session.closed:
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
