"""
插件运行时与遥测生命周期服务。
负责初始化期的配置修正、遥测注入、异常处理器安装、心跳任务管理与终止清理，
减少 main.DisasterWarningPlugin 中的生命周期细节堆积。
"""

from __future__ import annotations

import asyncio
import copy
import re
import time

from astrbot.api import logger

from ..core.support.config_validator import ConfigValidator
from ..core.support.telemetry_manager import TelemetryManager
from ..utils.version import get_plugin_version


class PluginLifecycleService:
    """插件生命周期编排服务。"""

    def __init__(self, plugin):
        self.plugin = plugin

    def sync_admin_users_from_global(self) -> None:
        config = self.plugin.config
        # 仅当插件未显式配置 admin_users 时，才回退同步 AstrBot 全局管理员，避免覆盖用户自定义设置。
        if "admin_users" not in config or config.get("admin_users") is None:
            global_admins = self.plugin.context.get_config().get("admins_id", [])
            if global_admins:
                config["admin_users"] = list(global_admins)
                config.save_config()
                logger.info(
                    f"[灾害预警] 已自动同步全局管理员到插件配置: {global_admins}"
                )

    def validate_and_fix_config(self) -> None:
        try:
            config_copy = copy.deepcopy(dict(self.plugin.config))
            validated_config = ConfigValidator.validate(config_copy)
            config_changed = False
            for key, value in validated_config.items():
                if self.plugin.config.get(key) != value:
                    self.plugin.config[key] = value
                    config_changed = True
            if config_changed:
                self.plugin.config.save_config()
                logger.info("[灾害预警] 配置已自动修正并保存")
        except Exception as e:
            logger.error(f"[灾害预警] 配置校验失败: {e}")

    def setup_telemetry(self) -> None:
        self.plugin.telemetry = TelemetryManager(
            config=dict(self.plugin.config),
            plugin_version=get_plugin_version(),
        )
        if self.plugin.disaster_service:
            self.plugin.disaster_service.set_telemetry(self.plugin.telemetry)

    def install_asyncio_exception_handler(self) -> None:
        if not self.plugin.telemetry or not self.plugin.telemetry.enabled:
            return
        loop = asyncio.get_running_loop()
        self.plugin._original_exception_handler = loop.get_exception_handler()
        loop.set_exception_handler(self.handle_asyncio_exception)
        logger.debug("[灾害预警] 已设置全局异常处理器")

    def start_telemetry_tasks(self) -> None:
        if not self.plugin.telemetry or not self.plugin.telemetry.enabled:
            return

        self.plugin._start_time = time.monotonic()
        startup_task = asyncio.create_task(self.plugin.telemetry.track_startup())
        config_task = asyncio.create_task(
            self.plugin.telemetry.track_config(dict(self.plugin.config))
        )
        self.plugin._telemetry_tasks.add(startup_task)
        self.plugin._telemetry_tasks.add(config_task)
        startup_task.add_done_callback(self.plugin._telemetry_tasks.discard)
        config_task.add_done_callback(self.plugin._telemetry_tasks.discard)

        self.plugin._heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        logger.debug("[灾害预警] 已启动遥测心跳任务 (间隔: 12小时)")

    async def cleanup_telemetry_tasks(self) -> None:
        if not self.plugin._telemetry_tasks:
            return
        pending_tasks = list(self.plugin._telemetry_tasks)
        for task in pending_tasks:
            if not task.done():
                task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        self.plugin._telemetry_tasks.clear()

    async def stop_heartbeat_task(self) -> None:
        if self.plugin._heartbeat_task:
            self.plugin._heartbeat_task.cancel()
            try:
                await self.plugin._heartbeat_task
            except asyncio.CancelledError:
                pass
            logger.debug("[灾害预警] 已停止心跳任务")

    def restore_asyncio_exception_handler(self) -> None:
        if self.plugin._original_exception_handler is not None:
            loop = asyncio.get_running_loop()
            loop.set_exception_handler(self.plugin._original_exception_handler)
            self.plugin._original_exception_handler = None
            logger.debug("[灾害预警] 已恢复全局异常处理器")

    async def shutdown_plugin_resources(self) -> None:
        # 插件停机时按“服务任务 -> 主服务 -> 子资源”顺序清理，尽量降低悬挂任务与残留连接风险。
        if self.plugin._service_task:
            self.plugin._service_task.cancel()
            try:
                await self.plugin._service_task
            except asyncio.CancelledError:
                pass

        from ..core.app.disaster_service import stop_disaster_service

        await stop_disaster_service()

        if (
            self.plugin.disaster_service
            and self.plugin.disaster_service.message_manager
        ):
            if hasattr(self.plugin.disaster_service.message_manager, "browser_manager"):
                try:
                    await self.plugin.disaster_service.message_manager.cleanup_browser()
                except Exception as be:
                    logger.debug(f"[灾害预警] 浏览器清理时出错（已忽略）: {be}")
            try:
                await (
                    self.plugin.disaster_service.message_manager.weather_filter.close()
                )
            except Exception as wfe:
                logger.debug(
                    f"[灾害预警] 气象过滤器 session 关闭时出错（已忽略）: {wfe}"
                )

        if (
            self.plugin.disaster_service
            and self.plugin.disaster_service.statistics_manager
        ):
            try:
                await self.plugin.disaster_service.statistics_manager._weather_region_resolver.close()
            except Exception as wfe:
                logger.debug(
                    f"[灾害预警] 统计模块气象 session 关闭时出错（已忽略）: {wfe}"
                )

        if self.plugin.telemetry:
            try:
                await self.plugin.telemetry.close()
            except Exception as te:
                logger.debug(f"[灾害预警] 遥测会话关闭时出错（已忽略）: {te}")

        if self.plugin.web_server:
            await self.plugin.web_server.stop()

    def handle_asyncio_exception(self, loop, context) -> None:
        exception = context.get("exception")
        message = context.get("message", "未知异常")

        is_plugin_exception = False
        if exception:
            tb = exception.__traceback__
            while tb is not None:
                frame = tb.tb_frame
                filename = frame.f_code.co_filename
                if "astrbot_plugin_disaster_warning" in filename:
                    is_plugin_exception = True
                    break
                tb = tb.tb_next

        if not is_plugin_exception:
            if self.plugin._original_exception_handler:
                self.plugin._original_exception_handler(loop, context)
            else:
                loop.default_exception_handler(context)
            return

        if exception:
            logger.error(f"[灾害预警] 捕获未处理的异步异常: {exception}")
            logger.error(f"[灾害预警] 异常上下文: {message}")
        else:
            logger.error(f"[灾害预警] 捕获未处理的异步错误: {message}")

        if self.plugin.telemetry and self.plugin.telemetry.enabled:
            if exception:
                task = context.get("future")
                task_name = "unknown"
                if task:
                    task_name = getattr(task, "get_name", lambda: str(task))()
                    if not task_name or task_name == str(task):
                        task_repr = repr(task)
                        if "name=" in task_repr:
                            match = re.search(r"name='([^']+)'", task_repr)
                            if match:
                                task_name = match.group(1)
                error_task = asyncio.create_task(
                    self.plugin.telemetry.track_error(
                        exception,
                        module=f"main.unhandled_async.{task_name}",
                    )
                )
            else:
                runtime_error = RuntimeError(message)
                error_task = asyncio.create_task(
                    self.plugin.telemetry.track_error(
                        runtime_error,
                        module="main.unhandled_async",
                    )
                )
            self.plugin._telemetry_tasks.add(error_task)
            error_task.add_done_callback(self.plugin._telemetry_tasks.discard)

    async def heartbeat_loop(self) -> None:
        heartbeat_interval = 43200
        try:
            while True:
                if not self.plugin.telemetry or not self.plugin.telemetry.enabled:
                    logger.debug("[灾害预警] 遥测已禁用，跳过心跳发送")
                    await asyncio.sleep(heartbeat_interval)
                    continue

                uptime = time.monotonic() - self.plugin._start_time
                try:
                    await self.plugin.telemetry.track_heartbeat(uptime_seconds=uptime)
                    logger.debug(
                        f"[灾害预警] 心跳数据已发送 (运行时长: {uptime:.0f}秒)"
                    )
                except Exception as e:
                    logger.debug(f"[灾害预警] 心跳发送失败: {e}")

                await asyncio.sleep(heartbeat_interval)
        except asyncio.CancelledError:
            logger.debug("[灾害预警] 心跳任务已取消")
            raise
        except Exception as e:
            logger.error(f"[灾害预警] 心跳循环异常: {e}")
