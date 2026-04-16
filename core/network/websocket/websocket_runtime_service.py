"""
WebSocket 运行时生命周期服务。
负责心跳循环、启动/停止、任务取消与连接断开清理，
减少 WebSocketManager 中的运行时生命周期过程式逻辑。
"""

from __future__ import annotations

import asyncio

import aiohttp

from astrbot.api import logger


class WebSocketRuntimeService:
    """WebSocket 运行时生命周期服务。"""

    def __init__(self, manager):
        self.manager = manager

    async def heartbeat_loop(self, name: str, websocket) -> None:
        """应用层心跳循环。"""
        interval = self.manager.config.get("heartbeat_interval", 30)
        try:
            while True:
                await asyncio.sleep(interval)
                if websocket.closed:
                    break

                last_time = self.manager.last_heartbeat_time.get(name, 0)
                current_time = asyncio.get_running_loop().time()
                # 若超过 2 个心跳周期仍无任何活跃信号，则主动发送 ping 做保活探测。
                if current_time - last_time > interval * 2:
                    try:
                        logger.debug(f"[灾害预警] 发送应用层 Ping: {name}")
                        await websocket.ping()
                    except Exception as e:
                        logger.warning(f"[灾害预警] Ping 失败 {name}: {e}")
                        await websocket.close(code=1001, message=b"Heartbeat timeout")
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[灾害预警] 心跳循环异常 {name}: {e}")

    async def disconnect(self, name: str) -> None:
        """断开连接。"""
        if name in self.manager.connections:
            try:
                await self.manager.connections[name].close()
                logger.info(f"[灾害预警] WebSocket连接已关闭: {name}")
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket断开连接时出错 {name}: {e}")
            finally:
                self.manager.connections.pop(name, None)
                self.manager.connection_info.pop(name, None)
                if name in self.manager.heartbeat_tasks:
                    self.manager.heartbeat_tasks[name].cancel()
                    self.manager.heartbeat_tasks.pop(name, None)

        if name in self.manager.reconnect_tasks:
            self.manager.reconnect_tasks[name].cancel()
            self.manager.reconnect_tasks.pop(name, None)

    async def cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self) -> None:
        """启动管理器。"""
        self.manager.running = True
        self.manager._stopping = False

        if not self.manager.session or self.manager.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.manager.config.get("http_timeout", 30)
            )
            self.manager.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("[灾害预警] WebSocket管理器已启动")

        if not self.manager.message_handlers:
            logger.warning("[灾害预警] 没有注册任何消息处理器")

    async def stop(self) -> None:
        """停止管理器。"""
        async with self.manager._stop_lock:
            if self.manager._stopping:
                logger.debug("[灾害预警] WebSocket管理器已在停止流程中，跳过重复调用")
                return
            self.manager._stopping = True
            try:
                logger.info("[灾害预警] WebSocket管理器正在停止...")
                self.manager.running = False

                # 先停重连/心跳，再逐个断开连接，最后关闭共享 session，避免停机期任务继续拉起连接。
                reconnect_tasks = list(self.manager.reconnect_tasks.values())
                await self.cancel_and_wait(reconnect_tasks)
                self.manager.reconnect_tasks.clear()

                heartbeat_tasks = [
                    task
                    for task in self.manager.heartbeat_tasks.values()
                    if task and not task.done()
                ]
                await self.cancel_and_wait(heartbeat_tasks)
                self.manager.heartbeat_tasks.clear()

                for name in list(self.manager.connections.keys()):
                    await self.disconnect(name)

                if self.manager.session:
                    await self.manager.session.close()
                    self.manager.session = None

                self.manager.connections.clear()
                self.manager.connection_info.clear()
                self.manager.connection_retry_counts.clear()
                self.manager.fallback_retry_counts.clear()
                self.manager.last_heartbeat_time.clear()

                logger.info("[灾害预警] WebSocket管理器已停止")
            finally:
                self.manager._stopping = False
