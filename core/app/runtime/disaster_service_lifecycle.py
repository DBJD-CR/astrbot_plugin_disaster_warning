"""
灾害服务生命周期编排服务。
负责 DisasterWarningService 的启动、停止、连接任务管理与后台任务回收，
减少主服务类中的生命周期过程式代码。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from astrbot.api import logger


class DisasterServiceLifecycleService:
    """灾害服务生命周期编排服务。"""

    def __init__(self, service):
        self.service = service

    async def start(self) -> None:
        """启动灾害服务。"""
        async with self.service._start_lock:
            if self.service.running:
                logger.debug("[灾害预警] 服务已在运行中，跳过重复启动")
                return

            try:
                self.service.running = True
                self.service._stopping = False
                self.service.start_time = datetime.now(timezone.utc)
                logger.info("[灾害预警] 正在启动灾害预警服务...")

                # 先恢复统计与缓存状态，再启动网络连接，避免启动后第一批事件缺少历史上下文。
                await self.service.statistics_manager.initialize()
                self.service._load_earthquake_lists_cache()
                self.service._load_eew_query_cache()

                # 运行时任务按“ws 管理器 -> 建连 -> 定时 HTTP -> 清理任务”顺序启动。
                await self.service.ws_manager.start()
                await self.service._establish_websocket_connections()
                await self.service._start_scheduled_http_fetch()
                await self.service._start_cleanup_task()

                if self.service.message_logger.enabled:
                    logger.debug(
                        f"[灾害预警] 原始消息日志记录已启用，日志文件: {self.service.message_logger.log_file_path}"
                    )
                else:
                    logger.debug(
                        "[灾害预警] 原始消息日志记录未启用。如需调试或记录原始数据，请使用命令 '/灾害预警日志开关' 启用。"
                    )

                logger.info("[灾害预警] 灾害预警服务已启动")
            except Exception as e:
                logger.error(f"[灾害预警] 启动服务失败: {e}")
                self.service.running = False
                if self.service._telemetry and self.service._telemetry.enabled:
                    await self.service._telemetry.track_error(
                        e, module="core.disaster_service.start"
                    )
                raise

    async def cancel_and_wait(self, tasks: list[asyncio.Task]) -> None:
        """取消并等待任务结束。"""
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        """停止灾害服务。"""
        async with self.service._stop_lock:
            if self.service._stopping:
                logger.debug("[灾害预警] 停止流程已在执行中，跳过重复调用")
                return
            self.service._stopping = True
            try:
                logger.info("[灾害预警] 正在停止灾害预警服务...")
                was_running = self.service.running
                self.service.running = False

                # 只有服务曾经真正运行过，才有必要落盘缓存状态。
                if was_running:
                    self.service._save_earthquake_lists_cache()
                    self.service._save_eew_query_cache()

                # 先停连接/调度/后台任务，再回收底层网络与数据库资源，避免任务使用已关闭对象。
                connection_tasks = list(self.service.connection_tasks)
                await self.cancel_and_wait(connection_tasks)
                self.service.connection_tasks.clear()

                scheduled_tasks = list(self.service.scheduled_tasks)
                await self.cancel_and_wait(scheduled_tasks)
                self.service.scheduled_tasks.clear()

                background_tasks = [
                    task
                    for task in self.service.background_tasks
                    if task and not task.done()
                ]
                await self.cancel_and_wait(background_tasks)
                self.service.background_tasks.clear()

                await self.service.ws_manager.stop()

                if self.service.http_fetcher:
                    await self.service.http_fetcher.close()

                if (
                    self.service.statistics_manager
                    and self.service.statistics_manager._db_initialized
                ):
                    await self.service.statistics_manager.db.close()

                logger.info("[灾害预警] 灾害预警服务已停止")
            except Exception as e:
                logger.error(f"[灾害预警] 停止服务时出错: {e}")
                if self.service._telemetry and self.service._telemetry.enabled:
                    await self.service._telemetry.track_error(
                        e, module="core.disaster_service.stop"
                    )
            finally:
                self.service._stopping = False
