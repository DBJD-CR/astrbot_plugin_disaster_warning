"""
WebSocket 消息分发与关闭处理服务。
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from aiohttp import ClientWebSocketResponse, WSMsgType

from astrbot.api import logger


class WebSocketDispatchService:
    """WebSocket 消息循环分发服务。"""

    _PREFIX_MAPPINGS: dict[str, str] = {
        "fan_studio_all": "fan_studio",
        "p2p_": "p2p",
        "wolfx_": "wolfx",
        "global_quake": "global_quake",
    }

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
            async for msg in websocket:
                # 文本/二进制消息统一走 payload handler，关闭码与错误消息则单独处理。
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
                    logger.info(
                        f"[灾害预警] WebSocket连接已关闭: {name}, code={websocket.close_code}"
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

        logger.info(f"[灾害预警] 连接断开: {name}")

    def log_message(self, name: str, message: Any, uri: str) -> None:
        """记录原始 WebSocket 消息。"""
        if not self.manager.message_logger:
            return

        try:
            self.manager.message_logger.log_raw_message(
                source=f"websocket_{name}",
                message_type="websocket_message",
                raw_data=message,
                connection_info={
                    "url": uri,
                    "connection_type": "websocket",
                    "handler": self.get_handler_name_for_connection(name),
                    **self.manager.connection_info.get(name, {}),
                },
            )
        except (TypeError, AttributeError):
            try:
                self.manager.message_logger.log_websocket_message(name, message, uri)
            except Exception as e:
                logger.warning(f"[灾害预警] 消息记录失败: {e}")

    def get_handler_name_for_connection(self, connection_name: str) -> str:
        """获取连接对应的处理器名称。"""
        for prefix, handler_name in self._PREFIX_MAPPINGS.items():
            if connection_name.startswith(prefix):
                return handler_name

        for handler_name in self.manager.message_handlers.keys():
            if connection_name.startswith(handler_name):
                return handler_name

        return "unknown"

    def find_handler_by_prefix(self, connection_name: str) -> str | None:
        """通过前缀匹配查找处理器名称。"""
        for prefix, handler_name in self._PREFIX_MAPPINGS.items():
            if connection_name.startswith(prefix):
                if handler_name in self.manager.message_handlers:
                    return handler_name
                logger.warning(
                    f"[灾害预警] 前缀匹配找到但处理器不存在: '{connection_name}' -> '{handler_name}'"
                )

        for handler_name in self.manager.message_handlers.keys():
            if connection_name.startswith(handler_name):
                return handler_name

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
            logger.info(f"[灾害预警] WebSocket正常关闭: {name}, code={close_code}")
            return

        if close_code in self._NO_RECONNECT_CODES:
            raise Exception(f"WebSocket协议错误关闭（不重连），代码 {close_code}")

        if close_code == 1006:
            logger.warning(
                f"[灾害预警] WebSocket异常关闭，准备重连: {name}, code={close_code}"
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
        self._touch_connection(name)

        try:
            self.log_message(name, message, uri)
            handler_name = self.find_handler_by_prefix(name)
            if handler_name:
                await self.manager.message_handlers[handler_name](
                    message,
                    connection_name=name,
                    connection_info=self.manager.connection_info[name],
                )
            else:
                logger.warning(f"[灾害预警] 未找到消息处理器 - 连接: {name}")
        except Exception as e:
            logger.error(f"[灾害预警] {error_label} {name}: {e}")
            logger.debug(f"[灾害预警] 异常堆栈: {traceback.format_exc()}")

    def _touch_connection(self, name: str) -> None:
        """刷新连接最近活跃时间。"""
        self.manager.last_heartbeat_time[name] = asyncio.get_running_loop().time()
