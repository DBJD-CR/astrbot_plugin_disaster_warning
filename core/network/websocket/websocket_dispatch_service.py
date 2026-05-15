"""
WebSocket 消息分发与关闭处理服务。
负责托管单连接消息循环、原始消息记录、处理器定位、关闭码判定与异常关闭后的策略分流。
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from aiohttp import ClientWebSocketResponse, WSMsgType

from astrbot.api import logger


class WebSocketDispatchService:
    """WebSocket 消息循环分发服务。"""

    _NORMAL_CLOSE_CODES = {
        1000,
        1001,
    }

    _NO_RECONNECT_CODES = {
        1002,
        1003,
        1007,
        1008,
        1009,
        1010,
        1011,
    }

    def __init__(self, manager):
        """保存管理器引用，复用其连接状态与处理器注册表。"""
        self.manager = manager

    async def handle_connection_session(
        self,
        name: str,
        uri: str,
        headers: dict | None,
        websocket: ClientWebSocketResponse,
    ) -> None:
        """处理单个连接的消息循环与关闭码策略。"""
        try:
            # 会话生命周期内持续消费底层消息，并按消息类型分流到不同处理路径。
            async for msg in websocket:
                # 文本与二进制业务消息统一进入负载处理链，关闭码与错误消息则单独处理。
                if msg.type == WSMsgType.TEXT:
                    await self._handle_payload_message(
                        name=name,
                        uri=uri,
                        message=msg.data,
                        error_label="消息处理错误",
                    )
                elif msg.type == WSMsgType.BINARY:
                    await self._handle_payload_message(
                        name=name,
                        uri=uri,
                        message=msg.data,
                        error_label="二进制消息处理错误",
                    )
                elif msg.type == WSMsgType.ERROR:
                    raise msg.data
                elif msg.type == WSMsgType.CLOSED:
                    logger.debug(
                        f"[灾害预警] WebSocket {name} 的连接已收到关闭帧，关闭码为 {websocket.close_code}"
                    )
                    break
                elif msg.type in {WSMsgType.PING, WSMsgType.PONG}:
                    self._touch_connection(name)

            await self.handle_close_code(
                name=name,
                uri=uri,
                headers=headers,
                close_code=websocket.close_code,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[灾害预警] WebSocket消息循环异常 {name}: {e}")
            raise

        logger.debug(f"[灾害预警] WebSocket 连接 {name} 的消息循环已结束")

    def log_message(self, name: str, message: Any, uri: str) -> None:
        """记录原始 WebSocket 消息。"""
        if not self.manager.message_logger:
            return

        try:
            # 优先走结构化原始消息记录接口，便于统一落盘格式与连接元数据。
            self.manager.message_logger.log_raw_message(
                source=f"websocket_{name}",
                message_type="websocket_message",
                payload_data=message,
                connection_info={
                    "url": uri,
                    "connection_type": "websocket",
                    "handler": self.get_handler_name_for_connection(name),
                    **self.manager.connection_info.get(name, {}),
                },
            )
        except (TypeError, AttributeError):
            # 兼容旧记录器接口，避免日志子系统升级前后出现硬性耦合。
            try:
                self.manager.message_logger.log_websocket_message(name, message, uri)
            except Exception as e:
                logger.warning(f"[灾害预警] 消息记录失败: {e}")

    def get_handler_name_for_connection(self, connection_name: str) -> str:
        """获取连接对应的处理器名称。"""
        connection_meta = self.manager.connection_info.get(connection_name, {})
        explicit_handler = str(connection_meta.get("handler") or "").strip()
        if explicit_handler:
            return explicit_handler

        handler_name = self.find_handler_by_prefix(connection_name)
        return handler_name or "unknown"

    def find_handler_by_prefix(self, connection_name: str) -> str | None:
        """通过已注册处理器名称查找连接对应处理器。"""
        matched_handler = None

        # 取“最长前缀命中”的处理器，兼容同族连接名下的主备实例或多路连接。
        for handler_name in self.manager.message_handlers.keys():
            if connection_name.startswith(handler_name):
                if matched_handler is None or len(handler_name) > len(matched_handler):
                    matched_handler = handler_name

        if matched_handler is not None:
            return matched_handler

        candidate_handler = connection_name.split("_", 1)[0].strip()
        if candidate_handler and candidate_handler not in self.manager.message_handlers:
            logger.warning(
                f"[灾害预警] 前缀匹配找到但处理器不存在: '{connection_name}' -> '{candidate_handler}'"
            )

        return None

    async def handle_close_code(
        self,
        name: str,
        uri: str,
        headers: dict | None,
        close_code: int | None,
    ) -> None:
        """根据关闭码执行关闭后策略。"""
        if close_code is None:
            return

        # 关闭码策略显式区分：正常关闭、不应重连的协议错误、以及需要重连的异常关闭。
        if close_code in self._NORMAL_CLOSE_CODES:
            logger.info(f"[灾害预警] WebSocket {name} 的连接已正常关闭，关闭码为 {close_code}")
            return

        if close_code in self._NO_RECONNECT_CODES:
            raise Exception(f"WebSocket协议错误关闭（不重连），代码 {close_code}")

        if close_code == 1006:
            logger.warning(
                f"[灾害预警] WebSocket {name} 的连接异常关闭，关闭码为 {close_code}，准备重连"
            )
            self.manager._handle_connection_error(
                name,
                uri,
                headers,
                RuntimeError(f"WebSocket异常关闭（连接中断），代码 {close_code}"),
            )
            return

        raise Exception(f"WebSocket意外关闭，代码 {close_code}")

    async def _handle_payload_message(
        self,
        name: str,
        uri: str,
        message: Any,
        error_label: str,
    ) -> None:
        """处理文本或二进制消息。"""
        # 一旦收到业务消息，就刷新最近活跃时间，避免健康状态被误判。
        self._touch_connection(name)

        try:
            self.log_message(name, message, uri)
            # 处理器优先取连接显式配置，其次再按前缀自动推断。
            connection_info = self.manager.connection_info[name]
            handler_name = str(connection_info.get("handler") or "").strip()
            if not handler_name:
                handler_name = self.find_handler_by_prefix(name)

            if handler_name and handler_name in self.manager.message_handlers:
                await self.manager.message_handlers[handler_name](
                    message,
                    connection_name=name,
                    connection_info=connection_info,
                )
            else:
                logger.warning(f"[灾害预警] 连接 {name} 没有匹配到可用的消息处理器")
        except Exception as e:
            logger.error(f"[灾害预警] {error_label} {name}: {e}")
            logger.debug(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def _touch_connection(self, name: str) -> None:
        """刷新连接最近活跃时间。"""
        self.manager.last_heartbeat_time[name] = asyncio.get_running_loop().time()
