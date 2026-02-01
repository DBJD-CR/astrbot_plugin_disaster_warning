import asyncio
import json
import os
import re
import time
import traceback
from datetime import datetime
from typing import Any

import astrbot.api.message_components as Comp

# [已移除] Windows平台WebSocket兼容性修复
# 采用 aiohttp 替代 websockets 库，原生支持 Windows EventLoop，无需修改全局策略
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.disaster_service import get_disaster_service, stop_disaster_service
from .core.telemetry_manager import TelemetryManager
from .models.models import (
    DATA_SOURCE_MAPPING,
    DisasterEvent,
    DisasterType,
    EarthquakeData,
    get_data_source_from_id,
)
from .utils.fe_regions import translate_place_name
from .utils.version import get_plugin_version


class DisasterWarningPlugin(Star):
    """多数据源灾害预警插件，支持地震、海啸、气象预警"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config: AstrBotConfig = config
        self.disaster_service: Any = None  # DisasterService 类型，避免循环导入
        self._service_task: asyncio.Task[None] | None = None
        self.telemetry: TelemetryManager | None = None
        self._config_schema: dict[str, Any] | None = None  # JSON Schema 缓存
        self._original_exception_handler: Any = None  # asyncio 异常处理器
        self._telemetry_tasks: set[asyncio.Task[None]] = set()  # 遥测任务引用集合
        self._heartbeat_task: asyncio.Task[None] | None = None  # 心跳定时任务
        self._start_time: float = 0.0  # 插件启动时间

    async def initialize(self):
        """初始化插件"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警插件...")

            # 首次加载时，尝试同步 AstrBot 全局管理员到插件配置 (仅在未配置时)
            if (
                "admin_users" not in self.config
                or self.config.get("admin_users") is None
            ):
                global_admins = self.context.get_config().get("admins_id", [])
                if global_admins:
                    self.config["admin_users"] = list(global_admins)
                    self.config.save_config()
                    logger.info(
                        f"[灾害预警] 已自动同步全局管理员到插件配置: {global_admins}"
                    )

            # 检查插件是否启用
            if not self.config.get("enabled", True):
                logger.info("[灾害预警] 插件已禁用，跳过初始化")
                return

            # 获取灾害预警服务
            self.disaster_service = await get_disaster_service(
                self.config, self.context
            )

            # 启动服务
            self._service_task = asyncio.create_task(self.disaster_service.start())

            # 初始化遥测
            self.telemetry = TelemetryManager(
                config=dict(self.config),
                plugin_version=get_plugin_version(),
            )
            # 将遥测管理器注入到灾害服务
            if self.disaster_service:
                self.disaster_service.set_telemetry(self.telemetry)

            # 设置全局 asyncio 异常处理器（捕获未处理的 task 异常）
            if self.telemetry.enabled:
                loop = asyncio.get_event_loop()
                # 保存原有的异常处理器
                self._original_exception_handler = loop.get_exception_handler()
                loop.set_exception_handler(self._handle_asyncio_exception)
                logger.debug("[灾害预警] 已设置全局异常处理器")

            if self.telemetry.enabled:
                # 记录启动时间（使用单调时钟）
                self._start_time = time.monotonic()
                
                # 发送启动事件和配置快照
                startup_task = asyncio.create_task(self.telemetry.track_startup())
                config_task = asyncio.create_task(
                    self.telemetry.track_config(dict(self.config))
                )
                # 保存任务引用,防止被垃圾回收
                self._telemetry_tasks.add(startup_task)
                self._telemetry_tasks.add(config_task)
                # 任务完成后自动从集合中移除
                startup_task.add_done_callback(self._telemetry_tasks.discard)
                config_task.add_done_callback(self._telemetry_tasks.discard)
                
                # 启动心跳定时任务
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                logger.debug("[灾害预警] 已启动遥测心跳任务 (间隔: 12小时)")

        except Exception as e:
            logger.error(f"[灾害预警] 插件初始化失败: {e}")
            # 上报初始化失败错误到遥测
            if hasattr(self, "telemetry") and self.telemetry and self.telemetry.enabled:
                await self.telemetry.track_error(e, module="main.initialize")
            raise

    async def _cleanup_telemetry_tasks(self) -> None:
        """清理并终止所有未完成的遥测任务，避免任务泄漏"""
        if not self._telemetry_tasks:
            return

        # 创建快照，避免遍历过程中集合被修改
        pending_tasks = list(self._telemetry_tasks)

        # 先取消所有仍在运行的任务
        for task in pending_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务结束，吞掉异常防止影响终止流程
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        # 统一从集合中移除已处理的任务
        self._telemetry_tasks.clear()

    async def terminate(self):
        """插件销毁时调用"""
        try:
            logger.info("[灾害预警] 正在停止灾害预警插件...")

            # 取消心跳任务
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
                logger.debug("[灾害预警] 已停止心跳任务")

            # 恢复原有异常处理器
            if self._original_exception_handler is not None:
                loop = asyncio.get_running_loop()
                loop.set_exception_handler(self._original_exception_handler)
                self._original_exception_handler = None
                logger.debug("[灾害预警] 已恢复全局异常处理器")

            # 清理遥测任务
            await self._cleanup_telemetry_tasks()

            # 停止服务任务
            if self._service_task:
                self._service_task.cancel()
                try:
                    await self._service_task
                except asyncio.CancelledError:
                    pass

            # 停止灾害预警服务
            await stop_disaster_service()

            # 关闭浏览器管理器（释放 Playwright 资源）
            if self.disaster_service and self.disaster_service.message_manager:
                if hasattr(self.disaster_service.message_manager, "browser_manager"):
                    try:
                        await self.disaster_service.message_manager.cleanup_browser()
                    except Exception as be:
                        logger.debug(f"[灾害预警] 浏览器清理时出错（已忽略）: {be}")

            # 关闭遥测会话（best-effort，不影响主要关闭流程）
            if self.telemetry:
                try:
                    await self.telemetry.close()
                except Exception as te:
                    logger.debug(f"[灾害预警] 遥测会话关闭时出错（已忽略）: {te}")

            logger.info("[灾害预警] 灾害预警插件已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 插件停止时出错: {e}")
            # 上报停止错误到遥测
            if hasattr(self, "telemetry") and self.telemetry and self.telemetry.enabled:
                await self.telemetry.track_error(e, module="main.terminate")

    def _handle_asyncio_exception(self, loop, context):
        """
        全局 asyncio 异常处理器
        捕获未被处理的 asyncio task 异常并上报到遥测
        """
        # 获取异常信息
        exception = context.get("exception")
        message = context.get("message", "未知异常")

        # 检查异常是否来自本插件
        is_plugin_exception = False
        if exception:
            # 通过 traceback 检查是否包含本插件的模块路径
            tb = exception.__traceback__
            while tb is not None:
                frame = tb.tb_frame
                filename = frame.f_code.co_filename
                # 检查文件路径是否属于本插件
                if "astrbot_plugin_disaster_warning" in filename:
                    is_plugin_exception = True
                    break
                tb = tb.tb_next

        # 如果不是本插件的异常，传递给原处理器
        if not is_plugin_exception:
            if (
                hasattr(self, "_original_exception_handler")
                and self._original_exception_handler
            ):
                self._original_exception_handler(loop, context)
            else:
                # 使用默认处理器
                loop.default_exception_handler(context)
            return

        # 记录日志（仅本插件的异常）
        if exception:
            logger.error(f"[灾害预警] 捕获未处理的异步异常: {exception}")
            logger.error(f"[灾害预警] 异常上下文: {message}")
        else:
            logger.error(f"[灾害预警] 捕获未处理的异步错误: {message}")

        # 上报到遥测
        if hasattr(self, "telemetry") and self.telemetry and self.telemetry.enabled:
            if exception:
                # 提取 task 名称或协程名称
                task = context.get("future")
                task_name = "unknown"
                if task:
                    # 尝试提取 task name（如 'Task-323'）
                    task_name = getattr(task, "get_name", lambda: str(task))()
                    if not task_name or task_name == str(task):
                        # 如果没有名字，尝试从 repr 中提取
                        task_repr = repr(task)
                        if "name=" in task_repr:
                            match = re.search(r"name='([^']+)'", task_repr)
                            if match:
                                task_name = match.group(1)

                # 创建一个新的 task 来上报错误（避免在异常处理器中使用 await）
                error_task = asyncio.create_task(
                    self.telemetry.track_error(
                        exception, module=f"main.unhandled_async.{task_name}"
                    )
                )
                # 保存任务引用,防止被垃圾回收
                self._telemetry_tasks.add(error_task)
                error_task.add_done_callback(self._telemetry_tasks.discard)
            else:
                # 如果没有具体的异常对象，创建一个 RuntimeError
                runtime_error = RuntimeError(message)
                error_task = asyncio.create_task(
                    self.telemetry.track_error(
                        runtime_error, module="main.unhandled_async"
                    )
                )
                # 保存任务引用,防止被垃圾回收
                self._telemetry_tasks.add(error_task)
                error_task.add_done_callback(self._telemetry_tasks.discard)

    async def _heartbeat_loop(self):
        """心跳循环任务 - 启动时立即发送一次，之后每12小时发送一次"""
        heartbeat_interval = 43200  # 12小时 = 43200秒
        
        try:
            while True:
                # 检查遥测是否仍然启用
                if not self.telemetry or not self.telemetry.enabled:
                    logger.debug("[灾害预警] 遥测已禁用，跳过心跳发送")
                    await asyncio.sleep(heartbeat_interval)
                    continue
                
                # 计算运行时长（使用单调时钟）
                uptime = time.monotonic() - self._start_time
                
                # 发送心跳
                try:
                    await self.telemetry.track_heartbeat(uptime_seconds=uptime)
                    logger.debug(f"[灾害预警] 心跳数据已发送 (运行时长: {uptime:.0f}秒)")
                except Exception as e:
                    logger.debug(f"[灾害预警] 心跳发送失败: {e}")
                
                # 等待12小时后再发送下一次
                await asyncio.sleep(heartbeat_interval)
        except asyncio.CancelledError:
            # 任务被取消时正常退出
            logger.debug("[灾害预警] 心跳任务已取消")
            raise
        except Exception as e:
            logger.error(f"[灾害预警] 心跳循环异常: {e}")


    @filter.command("灾害预警")
    async def disaster_warning_help(self, event: AstrMessageEvent):
        """灾害预警插件帮助"""
        help_text = """🚨 灾害预警插件使用说明

📋 可用命令：
• /灾害预警 - 显示此帮助信息
• /灾害预警状态 - 查看服务运行状态
• /地震列表查询 [数据源] [数量] [格式] - 查询最新地震列表
• /灾害预警统计 - 查看详细的事件统计报告
• /灾害预警统计清除 - 清除所有统计信息 (仅管理员)
• /灾害预警推送开关 - 开启或关闭当前会话的推送 (仅管理员)
• /灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源] - 模拟地震事件
• /灾害预警配置 查看 - 查看当前配置摘要 (仅管理员)
• /灾害预警日志 - 查看原始消息日志统计摘要 (仅管理员)
• /灾害预警日志开关 - 开关原始消息日志记录 (仅管理员)
• /灾害预警日志清除 - 清除所有原始消息日志 (仅管理员)

更多信息可参考 README 文档"""

        yield event.plain_result(help_text)

    @filter.command("灾害预警状态")
    async def disaster_status(self, event: AstrMessageEvent):
        """查看灾害预警服务状态"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()

            # --- 基础状态 ---
            running_state = "🟢 运行中" if status["running"] else "🔴 已停止"
            uptime = status.get("uptime", "未知")

            status_text = [
                "📊 灾害预警服务状态\n",
                "\n",
                f"🔄 运行状态：{running_state} (已运行 {uptime})\n",
                f"🔗 活跃连接：{status['active_websocket_connections']} / {status['total_connections']}\n",
            ]

            # --- 连接详情 ---
            conn_details = status.get("connection_details", {})
            if conn_details:
                status_text.append("\n")
                status_text.append("📡 连接详情：\n")
                for name, detail in conn_details.items():
                    state_icon = "🟢" if detail.get("connected") else "🔴"
                    uri = detail.get("uri", "未知地址")
                    # 简化URI显示
                    if len(uri) > 30:
                        uri = uri[:27] + "..."
                    retry = detail.get("retry_count", 0)
                    retry_text = f" (重试: {retry})" if retry > 0 else ""

                    status_text.append(f"  {state_icon} `{name}`: {uri}{retry_text}\n")

            # --- 活跃数据源 ---
            active_sources = status.get("data_sources", [])
            if active_sources:
                status_text.append("\n")
                status_text.append("📡 数据源详情：\n")

                # 按照服务分组
                service_groups = {}
                for source in active_sources:
                    parts = source.split(".", 1)
                    service = parts[0]
                    name = parts[1] if len(parts) > 1 else source
                    if service not in service_groups:
                        service_groups[service] = []
                    service_groups[service].append(name)

                # 映射服务名称为中文
                service_names = {
                    "fan_studio": "FAN Studio",
                    "p2p_earthquake": "P2P地震情报",
                    "wolfx": "Wolfx",
                    "global_quake": "Global Quake",
                }

                # 格式化输出
                for service, sources in service_groups.items():
                    display_name = service_names.get(service, service)
                    sources_str = ", ".join(sources)
                    status_text.append(f"  • {display_name}: {sources_str}\n")

            yield event.plain_result("".join(status_text))

        except Exception as e:
            logger.error(f"[灾害预警] 获取服务状态失败: {e}")
            yield event.plain_result(f"❌ 获取服务状态失败: {str(e)}")

    @filter.command("灾害预警统计")
    async def disaster_stats(self, event: AstrMessageEvent):
        """查看灾害预警详细统计"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()
            stats_summary = status.get("statistics_summary", "❌ 暂无统计数据")

            # 附加过滤统计信息
            if self.disaster_service and self.disaster_service.message_logger:
                filter_stats = self.disaster_service.message_logger.filter_stats
                if filter_stats and filter_stats["total_filtered"] > 0:
                    stats_summary += "\n\n🛡️ 日志过滤拦截统计:\n"
                    stats_summary += f"• 重复数据拦截: {filter_stats.get('duplicate_events_filtered', 0)}\n"
                    stats_summary += (
                        f"• 心跳包过滤: {filter_stats.get('heartbeat_filtered', 0)}\n"
                    )
                    stats_summary += (
                        f"• P2P节点状态: {filter_stats.get('p2p_areas_filtered', 0)}\n"
                    )
                    stats_summary += f"• 连接状态过滤: {filter_stats.get('connection_status_filtered', 0)}\n"
                    stats_summary += (
                        f"📊 总计拦截: {filter_stats.get('total_filtered', 0)}"
                    )

            yield event.plain_result(stats_summary)
        except Exception as e:
            logger.error(f"[灾害预警] 获取统计信息失败: {e}")
            yield event.plain_result(f"❌ 获取统计信息失败: {str(e)}")

    @filter.command("灾害预警日志")
    async def disaster_logs(self, event: AstrMessageEvent):
        """查看原始消息日志信息"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            log_summary = self.disaster_service.message_logger.get_log_summary()

            if not log_summary["enabled"]:
                yield event.plain_result(
                    "📋 原始消息日志功能未启用\n\n使用 /灾害预警日志开关 启用日志记录"
                )
                return

            if not log_summary["log_exists"]:
                yield event.plain_result(
                    "📋 暂无日志记录\n\n当日志功能启用后，所有接收到的原始消息将被记录。"
                )
                return

            log_info = f"""📊 原始消息日志统计

📁 日志文件：{log_summary["log_file"]}
📈 总条目数：{log_summary["total_entries"]}
📦 文件大小：{log_summary.get("file_size_mb", 0):.2f} MB
📅 时间范围：{log_summary["date_range"]["start"]} 至 {log_summary["date_range"]["end"]}

📡 数据源统计："""

            for source in log_summary["data_sources"]:
                log_info += f"\n  • {source}"

            log_info += "\n\n💡 提示：使用 /灾害预警日志开关 可以关闭日志记录"

            yield event.plain_result(log_info)

        except Exception as e:
            logger.error(f"[灾害预警] 获取日志信息失败: {e}")
            yield event.plain_result(f"❌ 获取日志信息失败: {str(e)}")

    @filter.command("灾害预警日志开关")
    async def toggle_message_logging(self, event: AstrMessageEvent):
        """开关原始消息日志记录"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            current_state = self.disaster_service.message_logger.enabled
            new_state = not current_state

            # 更新配置
            self.config["debug_config"]["enable_raw_message_logging"] = new_state
            self.disaster_service.message_logger.enabled = new_state

            # 保存配置
            self.config.save_config()

            status = "启用" if new_state else "禁用"
            action = "开始" if new_state else "停止"

            yield event.plain_result(
                f"✅ 原始消息日志记录已{status}\n\n插件将{action}记录所有数据源的原始消息格式。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 切换日志状态失败: {e}")
            yield event.plain_result(f"❌ 切换日志状态失败: {str(e)}")

    @filter.command("灾害预警日志清除")
    async def clear_message_logs(self, event: AstrMessageEvent):
        """清除所有原始消息日志"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        if not self.disaster_service or not self.disaster_service.message_logger:
            yield event.plain_result("❌ 日志功能不可用")
            return

        try:
            self.disaster_service.message_logger.clear_logs()
            yield event.plain_result(
                "✅ 所有原始消息日志已清除\n\n日志文件已被删除，新的消息记录将重新开始。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 清除日志失败: {e}")
            yield event.plain_result(f"❌ 清除日志失败: {str(e)}")

    @filter.command("灾害预警统计清除")
    async def clear_statistics(self, event: AstrMessageEvent):
        """清除统计数据"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        if not self.disaster_service or not self.disaster_service.statistics_manager:
            yield event.plain_result("❌ 统计功能不可用")
            return

        try:
            self.disaster_service.statistics_manager.reset_stats()
            yield event.plain_result(
                "✅ 统计数据已重置\n\n所有历史统计记录已被清除，新的统计将重新开始。"
            )

        except Exception as e:
            logger.error(f"[灾害预警] 清除统计失败: {e}")
            yield event.plain_result(f"❌ 清除统计失败: {str(e)}")

    @filter.command("灾害预警推送开关")
    async def toggle_push(self, event: AstrMessageEvent):
        """开关当前会话的推送"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        try:
            # 获取当前会话的 UMO
            session_umo = event.unified_msg_origin

            if not session_umo:
                yield event.plain_result("❌ 无法获取当前会话的 UMO")
                return

            # 获取当前推送列表
            target_sessions = self.config.get("target_sessions", [])
            if target_sessions is None:
                target_sessions = []

            # 检查当前 UMO 是否在列表中
            if session_umo in target_sessions:
                # 如果存在，则移除
                target_sessions.remove(session_umo)
                self.config["target_sessions"] = target_sessions
                self.config.save_config()
                yield event.plain_result(
                    f"✅ 推送已关闭\n\n会话 ({session_umo}) 已从推送列表中移除。"
                )
                logger.info(f"[灾害预警] 会话 {session_umo} 已关闭推送")
            else:
                # 如果不存在，则添加
                target_sessions.append(session_umo)
                self.config["target_sessions"] = target_sessions
                self.config.save_config()
                yield event.plain_result(
                    f"✅ 推送已开启\n\n会话 ({session_umo}) 已添加到推送列表。"
                )
                logger.info(f"[灾害预警] 会话 {session_umo} 已开启推送")

        except Exception as e:
            logger.error(f"[灾害预警] 切换推送状态失败: {e}")
            yield event.plain_result(f"❌ 切换推送状态失败: {str(e)}")

    @filter.command("灾害预警配置")
    async def disaster_config(self, event: AstrMessageEvent, action: str = None):
        """查看当前配置信息"""
        if not await self.is_plugin_admin(event):
            yield event.plain_result("🚫 权限不足：此命令仅限管理员使用。")
            return

        if action != "查看":
            yield event.plain_result("❓ 请使用格式：/灾害预警配置 查看")
            return

        try:
            # 加载 schema 文件以获取中文描述 (优先使用缓存)
            if self._config_schema is None:
                schema_path = os.path.join(
                    os.path.dirname(__file__), "_conf_schema.json"
                )
                if os.path.exists(schema_path):
                    with open(schema_path, encoding="utf-8") as f:
                        self._config_schema = json.load(f)
                else:
                    self._config_schema = {}

            schema = self._config_schema

            def _translate_recursive(config_item, schema_item):
                """递归将配置键名转换为中文描述"""
                if not isinstance(config_item, dict):
                    return config_item

                translated = {}
                for key, value in config_item.items():
                    # 获取当前键的 schema 定义
                    item_schema = schema_item.get(key, {}) if schema_item else {}

                    # 获取中文描述，如果没有则使用原键名
                    # 格式：中文描述
                    description = item_schema.get("description", key)

                    # 处理嵌套结构
                    if isinstance(value, dict):
                        # 如果 schema 中有 items 定义（通常用于嵌套对象），则传入子 schema
                        sub_schema = item_schema.get("items", {})
                        translated[description] = _translate_recursive(
                            value, sub_schema
                        )
                    else:
                        translated[description] = value

                return translated

            # 将配置转换为字典并进行翻译
            config_data = dict(self.config)
            translated_config = _translate_recursive(config_data, schema)

            # 转换为格式化的 JSON 字符串
            config_str = json.dumps(translated_config, indent=2, ensure_ascii=False)

            # 构造返回消息
            yield event.plain_result(f"🔧 当前配置详情：{config_str}")

        except Exception as e:
            logger.error(f"[灾害预警] 获取配置详情失败: {e}")
            yield event.plain_result(f"❌ 获取配置详情失败: {str(e)}")

    async def is_plugin_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为插件管理员或Bot管理员

        Note: 改为异步方法以防止 event.is_admin() 可能的阻塞风险
              在某些适配器实现中，is_admin() 可能涉及数据库查询
        """
        # 1. 检查是否为 AstrBot 全局管理员
        # event.is_admin() 是同步方法，但在 async 函数中调用是安全的
        # 如果未来 AstrBot 将其改为异步方法，只需添加 await 即可
        if event.is_admin():
            return True

        # 2. 检查 sender_id 是否在插件配置的 admin_users 中
        sender_id = event.get_sender_id()
        plugin_admins = self.config.get("admin_users", [])
        if sender_id in plugin_admins:
            return True

        return False

    @staticmethod
    def _format_source_name(source_key: str) -> str:
        """格式化数据源名称 - 细粒度配置结构"""
        # 配置格式：service.source (如：fan_studio.china_earthquake_warning)
        service, source = source_key.split(".", 1)
        source_names = {
            "fan_studio": {
                "china_earthquake_warning": "中国地震网地震预警",
                "taiwan_cwa_earthquake": "台湾中央气象署强震即时警报",
                "taiwan_cwa_report": "台湾中央气象署地震报告",
                "china_cenc_earthquake": "中国地震台网地震测定",
                "japan_jma_eew": "日本气象厅紧急地震速报",
                "usgs_earthquake": "USGS地震测定",
                "china_weather_alarm": "中国气象局气象预警",
                "china_tsunami": "自然资源部海啸预警",
            },
            "p2p_earthquake": {
                "japan_jma_eew": "P2P-日本气象厅紧急地震速报",
                "japan_jma_earthquake": "P2P-日本气象厅地震情报",
                "japan_jma_tsunami": "P2P-日本气象厅海啸预报",
            },
            "wolfx": {
                "japan_jma_eew": "Wolfx-日本气象厅紧急地震速报",
                "china_cenc_eew": "Wolfx-中国地震台网预警",
                "taiwan_cwa_eew": "Wolfx-台湾地震预警",
                "japan_jma_earthquake": "Wolfx-日本气象厅地震情报",
                "china_cenc_earthquake": "Wolfx-中国地震台网地震测定",
            },
            "global_quake": {
                "enabled": "Global Quake",
            },
        }
        return source_names.get(service, {}).get(source, source_key)

    @filter.command("地震列表查询")
    async def query_earthquake_list(
        self,
        event: AstrMessageEvent,
        source: str = "cenc",
        count: int = 5,
        mode: str = "card",
    ):
        """查询最新的地震列表

        Args:
            event: 消息事件对象
            source: 数据源 (cenc/jma)，默认为 cenc
            count: 返回的事件数量，默认为 5
            mode: 显示模式 (card/text)，默认为 card
        """
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        source = source.lower()
        if source not in ["cenc", "jma"]:
            yield event.plain_result("❌ 无效的数据源，仅支持 cenc 或 jma")
            return

        try:
            # 确定显示模式
            show_card = mode.lower() != "text"

            # 限制数量
            # 文本模式最大 50，卡片模式最大 10
            max_count = 10 if show_card else 50
            if count > max_count:
                count = max_count
                yield event.plain_result(
                    f"⚠️ 提示：{'卡片' if show_card else '文本'}模式最多支持显示 {max_count} 条记录"
                )
            elif count < 1:
                count = 1

            # 获取格式化后的数据
            # 总是请求 max_count 个数据，以便在卡片渲染失败时回退到文本模式能有足够的数据
            request_count = 50
            formatted_list = self.disaster_service.get_formatted_list_data(
                source, request_count
            )

            if not formatted_list:
                yield event.plain_result(
                    f"❌ 未找到 {source.upper()} 的地震列表数据，可能是因为服务刚启动，尚未获取到数据。"
                )
                return

            if show_card and self.disaster_service.message_manager:
                # 卡片模式
                display_list = formatted_list[:count]
                source_name = (
                    "中国地震台网 (CENC)" if source == "cenc" else "日本气象厅 (JMA)"
                )

                # 渲染卡片
                img_path = await self.disaster_service.message_manager.render_earthquake_list_card(
                    display_list, source_name
                )

                if img_path:
                    yield event.chain_result([Comp.Image.fromFileSystem(img_path)])
                else:
                    # 如果卡片渲染失败，回退到文本模式
                    yield event.plain_result(
                        "⚠️ 卡片渲染失败，转为文本显示\n"
                        + DisasterWarningPlugin._format_list_text(
                            formatted_list[:count], source
                        )
                    )
            else:
                # 文本模式
                display_list = formatted_list[:count]
                yield event.plain_result(
                    DisasterWarningPlugin._format_list_text(display_list, source)
                )

        except Exception as e:
            logger.error(f"[灾害预警] 查询地震列表失败: {e}")
            yield event.plain_result(f"❌ 查询失败: {e}")

    @staticmethod
    def _format_list_text(data_list: list[dict], source: str) -> str:
        """格式化地震列表文本 (仿 MessageLogger 风格)"""
        if not data_list:
            return "暂无数据"

        source_name = "http_wolfx_cenc" if source == "cenc" else "http_wolfx_jma"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"🕐 查询时间: {current_time}",
            f"📡 来源: {source_name}",
            "📋 类型: earthquake_list_query",
            "",
            "📊 列表数据:",
            f"    📋 total_events: {len(data_list)} (显示数量)",
            f"    📋 sample_events ({len(data_list)}项):",
        ]

        for i, item in enumerate(data_list):
            idx = i + 1
            lines.append(f"      [{idx}]:")
            lines.append(f"        📋 发生时间: {item['time']}")
            lines.append(f"        📋 震中: {item['location']}")
            lines.append(f"        📋 震级: {item['magnitude']}")
            depth_label = item.get("depth_label", "深度")
            lines.append(f"        📋 {depth_label}: {item['depth']}")

            if source == "cenc":
                lines.append(f"        📋 烈度: {item['intensity_display']}")
            else:
                lines.append(f"        📋 震度: {item['intensity_display']}")

        lines.append("")

        # 获取插件版本
        version = get_plugin_version()

        lines.append(
            f"🔧 @DBJD-CR/astrbot_plugin_disaster_warning (灾害预警) {version}"
        )

        return "\n".join(lines)

    @filter.command("灾害预警模拟")
    async def simulate_earthquake(
        self,
        event: AstrMessageEvent,
        lat: float,
        lon: float,
        magnitude: float,
        depth: float = 10.0,
        source: str = "cea_fanstudio",
    ):
        """模拟地震事件测试预警响应
        格式：/灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源]

        常用数据源ID：
        • cea_fanstudio (中国地震预警网 - 默认)
        • cenc_fanstudio (中国地震台网 - 正式)
        • jma_p2p (日本气象厅P2P - 预警)
        • jma_p2p_info (日本气象厅P2P - 情报)
        • cwa_fanstudio (台湾中央气象署)
        • usgs_fanstudio (USGS)
        • global_quake (Global Quake)
        """
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 服务未启动")
            return

        try:
            # 获取数据源
            data_source = get_data_source_from_id(source)
            if not data_source:
                valid_sources = ", ".join(DATA_SOURCE_MAPPING.keys())
                yield event.plain_result(
                    f"❌ 无效的数据源: {source}\n可用数据源: {valid_sources}"
                )
                return

            # 1. 构造模拟数据
            # 自动根据传入的经纬度生成地名
            final_place_name = translate_place_name("模拟震中", lat, lon)

            earthquake = EarthquakeData(
                id=f"sim_{int(datetime.now().timestamp())}",
                event_id=f"sim_{int(datetime.now().timestamp())}",
                source=data_source,
                disaster_type=DisasterType.EARTHQUAKE,
                shock_time=datetime.now(),
                latitude=lat,
                longitude=lon,
                depth=depth,
                magnitude=magnitude,
                place_name=final_place_name,
                source_id=source,
                raw_data={"test": True, "source_id": source},
            )

            # 针对USGS等特定数据源的特殊处理
            if source == "usgs_fanstudio":
                earthquake.update_time = datetime.now()

            # P2P数据源需要最大震度
            if source in ["jma_p2p", "jma_wolfx", "jma_p2p_info"]:
                # 简单估算一个震度用于测试
                earthquake.max_scale = max(0, min(7, int(magnitude - 2)))
                earthquake.scale = earthquake.max_scale

            disaster_event = DisasterEvent(
                id=f"sim_evt_{int(datetime.now().timestamp())}",
                data=earthquake,
                source=data_source,
                disaster_type=DisasterType.EARTHQUAKE,
                source_id=source,
            )

            manager = self.disaster_service.message_manager

            # 分开的消息构建
            report_lines = [
                "🧪 灾害预警模拟报告",
                f"Input: M{magnitude} @ ({lat}, {lon}), Depth {depth}km\n",
            ]

            # 2. 检查全局过滤器 (Global Filters)
            global_pass = True
            if manager.intensity_filter:
                if manager.intensity_filter.should_filter(earthquake):
                    global_pass = False
                    report_lines.append("❌ 全局过滤: 拦截 (不满足最小震级/烈度要求)")
                else:
                    report_lines.append("✅ 全局过滤: 通过")

            # 3. 检查本地监控 (Local Monitor)
            local_pass = True
            if manager.local_monitor:
                # 使用统一的辅助方法，返回 None 表示未启用，返回 dict 表示启用
                result = manager.local_monitor.inject_local_estimation(earthquake)

                if result is None:
                    # 未启用
                    report_lines.append("ℹ️ 本地监控: 未启用")
                else:
                    allowed = result.get("is_allowed", True)
                    dist = result.get("distance")
                    inte = result.get("intensity")

                    if allowed:
                        report_lines.append("✅ 本地监控: 触发")
                    else:
                        local_pass = False
                        report_lines.append("❌ 本地监控: 拦截 (严格模式生效中)")

                    report_lines.append(
                        f"   ⦁ 严格模式: {'开启' if manager.local_monitor.strict_mode else '关闭 (仅计算不拦截)'}"
                    )

                    # 安全格式化，处理可能的 None 值
                    dist_str = f"{dist:.1f} km" if dist is not None else "未知"
                    inte_str = f"{inte:.1f}" if inte is not None else "未知"
                    report_lines.extend(
                        [
                            f"   ⦁ 距本地: {dist_str}",
                            f"   ⦁ 预估最大本地烈度: {inte_str}",
                            f"   ⦁ 本地烈度阈值: {manager.local_monitor.threshold}",
                        ]
                    )
            else:
                report_lines.append("ℹ️ 本地监控: 未配置")

            # 发送报告
            yield event.plain_result("\n".join(report_lines))

            # 稍作等待，确保第一条消息发出
            await asyncio.sleep(1)

            # 4. 模拟消息构建
            if global_pass and local_pass:
                try:
                    logger.info("[灾害预警] 开始构建模拟预警消息...")
                    # 使用异步版本以支持卡片渲染
                    msg_chain = await manager.build_message_async(disaster_event)
                    logger.info(
                        f"[灾害预警] 消息构建成功，链长度: {len(msg_chain.chain)}"
                    )

                    # 直接使用context发送消息，绕过command generator
                    await self.context.send_message(event.unified_msg_origin, msg_chain)
                except Exception as build_e:
                    logger.error(
                        f"[灾害预警] 消息构建失败: {build_e}\n{traceback.format_exc()}"
                    )
                    yield event.plain_result(f"❌ 消息构建失败: {build_e}")
            else:
                yield event.plain_result("\n⛔ 结论: 该事件不会触发预警推送。")

        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"[灾害预警] 模拟测试失败: {e}\n{error_trace}")
            # 上报模拟测试错误到遥测
            if self.telemetry and self.telemetry.enabled:
                await self.telemetry.track_error(e, module="main.simulate_earthquake")
            yield event.plain_result(f"❌ 模拟失败: {e}")

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot加载完成时的钩子"""
        logger.info("[灾害预警] AstrBot已加载完成，灾害预警插件准备就绪")
