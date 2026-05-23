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
        """保存管理器引用，供生命周期操作复用共享状态。"""
        self.manager = manager

    async def heartbeat_loop(self, name: str, websocket) -> None:
        """应用层心跳循环。"""
        # 读取心跳发送频率配置，若未指定则默认为 30 秒
        interval = self.manager.config.get("heartbeat_interval", 30)
        try:
            while True:
                await asyncio.sleep(interval)
                # 套接字连接已断开，心跳循环直接退出
                if websocket.closed:
                    break

                last_time = self.manager.last_heartbeat_time.get(name, 0)
                current_time = asyncio.get_running_loop().time()
                # 判定保活失效：超过两个心跳周期，没有任何数据包到达
                if current_time - last_time > interval * 2:
                    try:
                        # 尝试通过 websocket 发送应用层 ping 帧检测死链接
                        await websocket.ping()
                    except Exception as e:
                        logger.warning(
                            f"[灾害预警] WebSocket {name} 的 Ping 保活失败，错误为 {e}"
                        )
                        # 写入超时原因，物理断开底层套接字
                        await websocket.close(code=1001, message=b"Heartbeat timeout")
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[灾害预警] 心跳循环异常 {name}: {e}")

    async def disconnect(self, name: str) -> None:
        """断开连接。"""
        # 断开指定命名的物理连接并释放资源
        if name in self.manager.connections:
            try:
                await self.manager.connections[name].close()
                logger.debug(f"[灾害预警] WebSocket {name} 的连接句柄已关闭")
            except Exception as e:
                logger.error(f"[灾害预警] WebSocket {name} 断开连接时出错，错误为 {e}")
            finally:
                # 无论 close 最终是否成功，都必须彻底清理管理器持有的状态，避免脏数据挂载
                self.manager.connections.pop(name, None)
                self.manager.connection_info.pop(name, None)
                # 取消该连接对应的主动心跳保活循环任务
                if name in self.manager.heartbeat_tasks:
                    self.manager.heartbeat_tasks[name].cancel()
                    self.manager.heartbeat_tasks.pop(name, None)

        # 清除处于等待队列中的重连任务
        if name in self.manager.reconnect_tasks:
            self.manager.reconnect_tasks[name].cancel()
            self.manager.reconnect_tasks.pop(name, None)

    async def cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        # 遍历取消全部异步任务，并聚合等待回收
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self) -> None:
        """启动管理器。"""
        self.manager.running = True
        self.manager._stopping = False

        # 如果共享的 ClientSession 还没就绪或已关闭，在此进行物理初始化
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
            # 引入防止重复停止的并发锁保护
            if self.manager._stopping:
                logger.debug("[灾害预警] WebSocket管理器已在停止流程中，跳过重复调用")
                return
            self.manager._stopping = True
            try:
                logger.info("[灾害预警] WebSocket管理器正在停止...")
                self.manager.running = False

                # 1. 优先关闭所有重连等待任务，防止在停止期间因为连接关闭而触发重连，陷入恶性循环
                reconnect_tasks = list(self.manager.reconnect_tasks.values())
                await self.cancel_and_wait(reconnect_tasks)
                self.manager.reconnect_tasks.clear()

                # 2. 取消所有还在运行的心跳保活任务
                heartbeat_tasks = [
                    task
                    for task in self.manager.heartbeat_tasks.values()
                    if task and not task.done()
                ]
                await self.cancel_and_wait(heartbeat_tasks)
                self.manager.heartbeat_tasks.clear()

                # 3. 物理切断所有现存的 WebSocket 连接句柄
                for name in list(self.manager.connections.keys()):
                    await self.disconnect(name)

                # 4. 彻底释放并关闭共享的 ClientSession
                if self.manager.session:
                    await self.manager.session.close()
                    self.manager.session = None

                # 5. 彻底清空所有状态缓存
                self.manager.connections.clear()
                self.manager.connection_info.clear()
                self.manager.connection_retry_counts.clear()
                self.manager.fallback_retry_counts.clear()
                self.manager.last_heartbeat_time.clear()

                logger.info("[灾害预警] WebSocket管理器已停止")
            finally:
                self.manager._stopping = False
