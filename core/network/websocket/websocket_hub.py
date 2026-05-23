"""
管理端 WebSocket 广播中心。
负责维护前端连接集合，并统一提供完整快照广播、常规更新广播、事件推送与批量关闭能力。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api import logger


class WebSocketHub:
    """WebSocket 连接与广播中心。"""

    def __init__(self):
        """初始化连接集合。"""
        self.connections: list[Any] = []

    def add(self, websocket) -> None:
        """注册连接。"""
        # 这里不做去重假设，调用方保证同一连接只在握手成功后注册一次。
        self.connections.append(websocket)

    def remove(self, websocket) -> None:
        """移除连接。"""
        if websocket in self.connections:
            self.connections.remove(websocket)

    def count(self) -> int:
        """返回当前连接数。"""
        return len(self.connections)

    async def send_full_update(
        self,
        websocket,
        data_factory: Callable[[], Awaitable[dict[str, Any]]],
    ) -> bool:
        """向单个客户端发送完整更新。"""
        try:
            data = await data_factory()
            await websocket.send_json({"type": "full_update", "data": data})
            return True
        except Exception as e:
            logger.debug(f"[灾害预警] 发送数据失败: {e}")
            self.remove(websocket)
            return False

    async def broadcast_update(
        self,
        data_factory: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        """向所有连接客户端广播常规更新。"""
        if not self.connections:
            return

        # 同一轮广播内数据只构建一次，避免重复读取运行时状态。
        data = await data_factory()
        message = {"type": "update", "data": data}
        disconnected = []
        for websocket in list(self.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        # 发送失败的连接在本轮广播后统一清理，避免边遍历边修改列表。
        for websocket in disconnected:
            self.remove(websocket)

    async def broadcast_event(
        self,
        data_factory: Callable[[], Awaitable[dict[str, Any]]],
        event_data: dict[str, Any] | None = None,
    ) -> None:
        """向所有连接客户端广播事件更新。"""
        if not self.connections:
            return

        # 事件推送既携带最新面板快照，也可附带一条新增事件详情。
        data = await data_factory()
        message: dict[str, Any] = {
            "type": "event",
            "data": data,
        }
        if event_data:
            message["new_event"] = event_data

        disconnected = []
        for websocket in list(self.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.remove(websocket)

        if event_data:
            logger.debug(f"[灾害预警] 已推送新事件到 {self.count()} 个客户端")

    async def close_all(self) -> None:
        """关闭并清空所有连接。"""
        for websocket in list(self.connections):
            try:
                await websocket.close()
            except Exception:
                pass
        self.connections.clear()
