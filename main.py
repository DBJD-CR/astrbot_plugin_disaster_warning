import asyncio
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.app.disaster_service import get_disaster_service
from .core.network.admin.host.web_server import WebAdminServer
from .core.services.telemetry.telemetry_service import TelemetryManager
from .plugin.commands.plugin_admin_command_service import PluginAdminCommandService
from .plugin.commands.plugin_query_command_service import PluginQueryCommandService
from .plugin.plugin_command_support_service import PluginCommandSupportService
from .plugin.plugin_lifecycle_service import PluginLifecycleService


class DisasterWarningPlugin(Star):
    """多数据源灾害预警插件，支持地震、海啸、气象预警"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        # main.py 现在主要承担 AstrBot 插件入口壳职责，
        # 具体生命周期和命令实现分别下沉到 plugin/ 子服务中。
        self.config: AstrBotConfig = config
        self.disaster_service: Any = None  # DisasterService 类型，避免循环导入
        self._service_task: asyncio.Task[None] | None = None
        self.telemetry: TelemetryManager | None = None
        self._config_schema: dict[str, Any] | None = None  # JSON Schema 缓存
        self._original_exception_handler: Any = None  # asyncio 异常处理器
        self._telemetry_tasks: set[asyncio.Task[None]] = set()  # 遥测任务引用集合
        self._heartbeat_task: asyncio.Task[None] | None = None  # 心跳定时任务
        self._start_time: float = 0.0  # 插件启动时间
        self.web_server = None
        self._lifecycle_service = PluginLifecycleService(self)
        self._command_support_service = PluginCommandSupportService(self)
        self._admin_command_service = PluginAdminCommandService(self)
        self._query_command_service = PluginQueryCommandService(self)

    async def initialize(self):
        """初始化插件"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警插件...")

            # 初始化期先处理配置与管理员同步，再装配 disaster_service / telemetry / web_admin。
            self._lifecycle_service.sync_admin_users_from_global()
            self._lifecycle_service.validate_and_fix_config()

            # 检查插件是否启用
            if not self.config.get("enabled", True):
                logger.info("[灾害预警] 插件已禁用，跳过初始化")
                return

            # 获取灾害预警服务
            self.disaster_service = await get_disaster_service(
                self.config, self.context
            )

            # 启动服务使用后台 task 承载，这样插件 initialize() 不会长期阻塞 AstrBot 的启动流程。
            self._service_task = asyncio.create_task(self.disaster_service.start())

            # 遥测相关初始化放在 disaster_service 创建之后，确保能把 telemetry 引用回注到服务层。
            self._lifecycle_service.setup_telemetry()
            self._lifecycle_service.install_asyncio_exception_handler()
            self._lifecycle_service.start_telemetry_tasks()

            if self.config.get("web_admin", {}).get("enabled", False):
                self.web_server = WebAdminServer(self.disaster_service, self.config)
                # 注入引用以支持事件驱动的实时推送
                self.disaster_service.web_admin_server = self.web_server
                await self.web_server.start()

        except Exception as e:
            logger.error(f"[灾害预警] 插件初始化失败: {e}")
            # 上报初始化失败错误到遥测
            if hasattr(self, "telemetry") and self.telemetry and self.telemetry.enabled:
                try:
                    await self.telemetry.track_error(e, module="main.initialize")
                except Exception:
                    pass

            # 发生异常时，确保清理已启动的任务和资源，防止任务泄露
            await self.terminate()
            raise

    async def _cleanup_telemetry_tasks(self) -> None:
        """清理并终止所有未完成的遥测任务，避免任务泄漏"""
        await self._lifecycle_service.cleanup_telemetry_tasks()

    async def terminate(self):
        """插件销毁时调用"""
        try:
            logger.info("[灾害预警] 正在停止灾害预警插件...")

            await self._lifecycle_service.stop_heartbeat_task()
            self._lifecycle_service.restore_asyncio_exception_handler()
            await self._cleanup_telemetry_tasks()
            await self._lifecycle_service.shutdown_plugin_resources()

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
        self._lifecycle_service.handle_asyncio_exception(loop, context)

    async def _heartbeat_loop(self):
        """心跳循环任务 - 启动时立即发送一次，之后每12小时发送一次"""
        await self._lifecycle_service.heartbeat_loop()

    @filter.command("灾害预警")
    async def disaster_warning_help(self, event: AstrMessageEvent):
        """灾害预警插件帮助"""
        help_text = """🚨 灾害预警插件使用说明

📋 可用命令：
• /灾害预警 - 显示此帮助信息
• /灾害预警状态 - 查看服务运行状态
• /灾害预警重连 - 强制重连所有数据源 (仅管理员)
• /地震列表查询 或 /地震列表 [数据源] [数量] [格式] - 查询最新地震列表
• /地震预警查询 或 /地震预警 - 查询各机构 EEW 状态与无 EEW 计时
• /气象预警查询 或 /气象预警 <省份/地名|全国> [预警类型] [预警颜色] 或 <预警ID>
• /灾害预警统计 - 查看详细的事件统计报告
• /灾害预警统计清除 - 清除所有统计信息 (仅管理员)
• /灾害预警推送开关 - 开启或关闭当前会话的推送 (仅管理员)
• /灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源] - 模拟地震事件
• /灾害预警配置 查看 [全局|当前|会话UMO] - 查看配置（会话模式返回差异覆写）(仅管理员)
• /灾害预警日志 - 查看原始消息日志统计摘要 (仅管理员)
• /灾害预警日志开关 - 开关原始消息日志记录 (仅管理员)
• /灾害预警日志清除 - 清除所有原始消息日志 (仅管理员)

更多信息可参考 README 文档"""

        yield event.plain_result(help_text)

    @filter.command("灾害预警重连")
    async def disaster_reconnect(self, event: AstrMessageEvent):
        """强制对所有已启用但离线的数据源发起重连"""
        async for result in self._admin_command_service.handle_disaster_reconnect(
            event
        ):
            yield result

    @filter.command("灾害预警状态")
    async def disaster_status(self, event: AstrMessageEvent):
        """查看灾害预警服务状态"""
        async for result in self._admin_command_service.handle_disaster_status(event):
            yield result

    @filter.command("灾害预警统计")
    async def disaster_stats(self, event: AstrMessageEvent):
        """查看灾害预警详细统计"""
        async for result in self._admin_command_service.handle_disaster_stats(event):
            yield result

    @filter.command("灾害预警日志")
    async def disaster_logs(self, event: AstrMessageEvent):
        """查看原始消息日志信息"""
        async for result in self._admin_command_service.handle_disaster_logs(event):
            yield result

    @filter.command("灾害预警日志开关")
    async def toggle_message_logging(self, event: AstrMessageEvent):
        """开关原始消息日志记录"""
        async for result in self._admin_command_service.handle_toggle_message_logging(
            event
        ):
            yield result

    @filter.command("灾害预警日志清除")
    async def clear_message_logs(self, event: AstrMessageEvent):
        """清除所有原始消息日志"""
        async for result in self._admin_command_service.handle_clear_message_logs(
            event
        ):
            yield result

    @filter.command("灾害预警统计清除")
    async def clear_statistics(self, event: AstrMessageEvent):
        """清除统计数据"""
        async for result in self._admin_command_service.handle_clear_statistics(event):
            yield result

    @filter.command("灾害预警推送开关")
    async def toggle_push(self, event: AstrMessageEvent):
        """开关当前会话的推送"""
        async for result in self._admin_command_service.handle_toggle_push(event):
            yield result

    @filter.command("灾害预警配置")
    async def disaster_config(
        self,
        event: AstrMessageEvent,
        action: str = None,
        target: str = None,
    ):
        """查看当前配置信息（支持按会话查看差异覆写）"""
        async for result in self._admin_command_service.handle_disaster_config(
            event, action=action, target=target
        ):
            yield result

    async def is_plugin_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为插件管理员或Bot管理员"""
        return await self._command_support_service.is_plugin_admin(event)

    @staticmethod
    def _with_quote_reply(
        event: AstrMessageEvent,
        chain: list[Any],
    ) -> list[Any]:
        """为消息链添加引用回复段（若可用）。"""
        return PluginCommandSupportService.with_quote_reply(event, chain)

    @filter.command("气象预警查询", alias={"气象预警"})
    async def query_weather_alarm(
        self,
        event: AstrMessageEvent,
        keyword: str = None,
        optional_a: str = None,
        optional_b: str = None,
    ):
        """气象预警查询"""
        async for result in self._query_command_service.handle_query_weather_alarm(
            event,
            keyword=keyword,
            optional_a=optional_a,
            optional_b=optional_b,
        ):
            yield result

    @filter.command("地震预警查询", alias={"地震预警"})
    async def query_earthquake_warning(self, event: AstrMessageEvent):
        """查询各机构地震预警（EEW）状态"""
        async for result in self._query_command_service.handle_query_earthquake_warning(
            event
        ):
            yield result

    @filter.command("地震列表查询", alias={"地震列表"})
    async def query_earthquake_list(
        self,
        event: AstrMessageEvent,
        source: str = "cenc",
        count: int = 9,
        mode: str = "card",
    ):
        """查询最新的地震列表"""
        async for result in self._query_command_service.handle_query_earthquake_list(
            event,
            source=source,
            count=count,
            mode=mode,
        ):
            yield result

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
        """模拟地震事件测试预警响应"""
        async for result in self._query_command_service.handle_simulate_disaster(
            event,
            lat=lat,
            lon=lon,
            magnitude=magnitude,
            depth=depth,
            source=source,
        ):
            yield result

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot加载完成时的钩子"""
        logger.debug("[灾害预警] AstrBot已加载完成，灾害预警插件准备就绪")
