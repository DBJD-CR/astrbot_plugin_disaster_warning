import asyncio
import sys

# Windows平台WebSocket兼容性修复
# 解决websockets 12.0+ 在Windows上的ProactorEventLoop兼容性问题
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .core.disaster_service import get_disaster_service, stop_disaster_service
from .models.models import DisasterEvent, EarthquakeData, DataSource, DisasterType


class DisasterWarningPlugin(Star):
    """多数据源灾害预警插件，支持地震、海啸、气象预警"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.disaster_service = None
        self._service_task = None

    async def initialize(self):
        """初始化插件"""
        try:
            logger.info("[灾害预警] 正在初始化灾害预警插件...")

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

        except Exception as e:
            logger.error(f"[灾害预警] 插件初始化失败: {e}")
            raise

    async def terminate(self):
        """插件销毁时调用"""
        try:
            logger.info("[灾害预警] 正在停止灾害预警插件...")

            # 停止服务任务
            if self._service_task:
                self._service_task.cancel()
                try:
                    await self._service_task
                except asyncio.CancelledError:
                    pass

            # 停止灾害预警服务
            await stop_disaster_service()

            logger.info("[灾害预警] 灾害预警插件已停止")

        except Exception as e:
            logger.error(f"[灾害预警] 插件停止时出错: {e}")

    @filter.command("灾害预警")
    async def disaster_warning_help(self, event: AstrMessageEvent):
        """灾害预警插件帮助"""
        help_text = """🚨 灾害预警插件使用说明

📋 可用命令：
• /灾害预警状态 - 查看服务运行状态
• /灾害预警测试 [群号] [灾害类型] [格式] - 测试推送功能
• /灾害预警统计 - 查看推送统计信息
• /灾害预警配置 查看 - 查看当前配置摘要
• /灾害预警去重统计 - 查看事件去重统计
• /灾害预警日志 - 查看原始消息日志统计
• /灾害预警日志开关 - 开关原始消息日志记录
• /灾害预警日志清除 - 清除所有原始消息日志
• /灾害预警帮助 - 显示此帮助信息

🧪 测试功能说明：
/灾害预警测试 [群号] [灾害类型] [格式]
• 群号：可选，默认为当前群
• 灾害类型：earthquake(地震)|tsunami(海啸)|weather(气象)
• 格式：可选，不同数据源的消息格式
  - 地震：china(中国格式)|japan(日本格式)|usgs(美国格式)
  - 海啸：china(中国格式)|japan(日本格式)
  - 气象：china(中国格式)

📋 测试示例：
• /灾害预警测试 - 在当前群测试中国地震格式
• /灾害预警测试 earthquake japan - 测试日本地震格式
• /灾害预警测试 123456 earthquake usgs - 在群123456测试美国地震格式
• /灾害预警测试 tsunami japan - 测试日本海啸格式

⚙️ 配置说明：
插件支持通过WebUI进行配置，包括：
• 数据源选择（地震、海啸、气象等）
• 推送阈值设置（震级、烈度等）
• 频率控制（报数控制）
• 目标群号设置
• 消息过滤（心跳包、P2P节点状态、重复事件等）

🔧 注意事项：
• 需要先在WebUI中配置目标群号
• 插件会自动过滤低于设置阈值的地震信息
• 原始消息日志记录默认关闭，如需调试请使用 /灾害预警日志开关 开启"""

        yield event.plain_result(help_text)

    @filter.command("灾害预警状态")
    async def disaster_status(self, event: AstrMessageEvent):
        """查看灾害预警服务状态"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            status = self.disaster_service.get_service_status()

            status_text = f"""📊 灾害预警服务状态

🔄 运行状态：{"运行中" if status["running"] else "已停止"}
🔗 活跃连接：{status["active_websocket_connections"]} 个
📡 数据源：{len(status["data_sources"])} 个"""

            # 推送统计
            push_stats = status.get("push_stats", {})
            if push_stats:
                status_text += f"""
📈 推送统计：
  • 总事件数：{push_stats.get("total_events", 0)}
  • 总推送数：{push_stats.get("total_pushes", 0)}
  • 最终报数：{push_stats.get("final_reports_pushed", 0)}"""

            # 过滤统计（如果启用）
            if self.disaster_service and self.disaster_service.message_logger:
                filter_stats = self.disaster_service.message_logger.filter_stats
                if filter_stats and filter_stats["total_filtered"] > 0:
                    status_text += f"""
🎯 消息过滤统计：
  • 心跳包过滤：{filter_stats.get("heartbeat_filtered", 0)} 条
  • P2P节点状态过滤：{filter_stats.get("p2p_areas_filtered", 0)} 条
  • 重复事件过滤：{filter_stats.get("duplicate_events_filtered", 0)} 条
  • 连接状态过滤：{filter_stats.get("connection_status_filtered", 0)} 条
  • 总计过滤：{filter_stats.get("total_filtered", 0)} 条"""

            # 最近事件
            recent_events = push_stats.get("recent_events", [])
            if recent_events:
                status_text += f"""
🕐 最近24小时事件 (插件启动后)：{len(recent_events)} 个"""

            yield event.plain_result(status_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取服务状态失败: {e}")
            yield event.plain_result(f"❌ 获取服务状态失败: {str(e)}")

    @filter.command("灾害预警测试")
    async def disaster_test(
        self,
        event: AstrMessageEvent,
        target_group: str = None,
        disaster_type: str = None,
        test_type: str = None,
    ):
        """测试灾害预警推送功能 - 支持多种灾害类型和测试格式"""
        if not self.disaster_service:
            yield event.plain_result("❌ 灾害预警服务未启动")
            return

        try:
            # 解析参数 - 支持多种参数组合
            target_session = None
            disaster_test_type = "earthquake"  # 默认测试地震
            format_test_type = None  # 默认使用推荐格式

            # 中文参数映射
            type_mapping = {
                "地震": "earthquake",
                "海啸": "tsunami",
                "气象": "weather",
                "earthquake": "earthquake",
                "tsunami": "tsunami",
                "weather": "weather",
            }

            format_mapping = {
                "中国": "china",
                "日本": "japan",
                "美国": "usgs",
                "china": "china",
                "japan": "japan",
                "usgs": "usgs",
            }

            # 获取平台名称配置
            platform_name = self.config.get("platform_name", "aiocqhttp")

            # 辅助函数：判断字符串是否为灾害类型
            def is_disaster_type(s):
                return s in type_mapping

            # 辅助函数：判断字符串是否为测试格式
            def is_format_type(s):
                return s in format_mapping

            # 参数解析逻辑 - 支持最多3个参数
            if target_group and disaster_type and test_type:
                # 三个参数：群号 + 灾害类型 + 测试格式
                target_session = f"{platform_name}:GroupMessage:{target_group}"
                disaster_test_type = type_mapping.get(disaster_type, disaster_type)
                format_test_type = format_mapping.get(test_type, test_type)

            elif target_group and disaster_type:
                # 两个参数：需要判断第二个是灾害类型还是测试格式
                if is_disaster_type(disaster_type):
                    # 情况1: 群号 + 灾害类型 (例如: 123456 earthquake)
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                    disaster_test_type = type_mapping.get(disaster_type)
                    # test_type 保持 None，使用默认格式
                elif is_format_type(disaster_type):
                    # 第二个是格式，需要判断第一个是群号还是灾害类型
                    if is_disaster_type(target_group):
                        # 情况2: 灾害类型 + 格式 (例如: earthquake japan) -> 使用当前群
                        target_session = event.unified_msg_origin
                        disaster_test_type = type_mapping.get(target_group)
                        format_test_type = format_mapping.get(disaster_type)
                    else:
                        # 情况3: 群号 + 格式 (例如: 123456 japan) -> 默认地震
                        target_session = f"{platform_name}:GroupMessage:{target_group}"
                        disaster_test_type = "earthquake"
                        format_test_type = format_mapping.get(disaster_type)
                else:
                    # 其他情况，尝试智能匹配
                    if is_disaster_type(target_group) and is_format_type(disaster_type):
                        target_session = event.unified_msg_origin
                        disaster_test_type = type_mapping.get(target_group)
                        format_test_type = format_mapping.get(disaster_type)
                    else:
                        # 默认处理
                        target_session = f"{platform_name}:GroupMessage:{target_group}"
                        disaster_test_type = type_mapping.get(
                            disaster_type, disaster_type
                        )

            elif target_group:
                # 只提供一个参数：需要判断是群号还是灾害类型/测试格式
                if is_disaster_type(target_group):
                    # 是灾害类型，使用当前群
                    target_session = event.unified_msg_origin
                    disaster_test_type = type_mapping.get(target_group)
                elif is_format_type(target_group):
                    # 是测试格式，使用当前群，默认地震
                    target_session = event.unified_msg_origin
                    disaster_test_type = "earthquake"
                    format_test_type = format_mapping.get(target_group)
                else:
                    # 是群号，默认测试地震
                    target_session = f"{platform_name}:GroupMessage:{target_group}"
                    disaster_test_type = "earthquake"
            else:
                # 没有额外参数：使用当前群，默认测试地震
                target_session = event.unified_msg_origin
                disaster_test_type = "earthquake"

            # 验证灾害类型
            valid_types = ["earthquake", "tsunami", "weather"]
            if disaster_test_type not in valid_types:
                yield event.plain_result(
                    f"❌ 未知的灾害类型 '{disaster_test_type}'\n\n支持的类型：地震(earthquake), 海啸(tsunami), 气象(weather)"
                )
                return

            # 验证测试格式
            valid_formats = {
                "earthquake": ["china", "japan", "usgs"],
                "tsunami": ["china", "japan"],
                "weather": ["china"],  # 气象只有中国格式
            }

            if format_test_type:
                allowed_formats = valid_formats.get(disaster_test_type, [])
                if format_test_type not in allowed_formats:
                    yield event.plain_result(
                        f"❌ 灾害类型 '{disaster_test_type}' 不支持测试格式 '{format_test_type}'\n\n"
                        f"支持的格式：{', '.join(allowed_formats)}"
                    )
                    return

            # 执行测试
            logger.info(
                f"[灾害预警] 开始{disaster_test_type}测试推送到 {target_session} (格式: {format_test_type or '默认'})"
            )
            test_result = await self.disaster_service.test_push(
                target_session, disaster_test_type, format_test_type
            )

            if test_result and "✅" in test_result:
                # 测试成功，直接返回测试结果
                yield event.plain_result(test_result)
            else:
                yield event.plain_result(test_result or "❌ 测试推送失败，请检查日志")

        except Exception as e:
            logger.error(f"[灾害预警] 测试推送失败: {e}")
            yield event.plain_result(f"❌ 测试推送失败: {str(e)}")

    @filter.command("灾害预警统计")
    async def disaster_stats(self, event: AstrMessageEvent):
        """查看推送统计信息"""
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 统计信息不可用")
            return

        try:
            stats = self.disaster_service.message_manager.get_push_stats()

            stats_text = f"""📈 灾害预警推送统计

📊 总体统计：
  • 总事件数：{stats["total_events"]}
  • 总推送数：{stats["total_pushes"]}
  • 最终报数：{stats["final_reports_pushed"]}

🕐 最近24小时 (插件启动后)：
  • 事件数：{len(stats["recent_events"])}"""

            # 显示最近的事件
            if stats["recent_events"]:
                stats_text += "\n\n📋 最近事件："
                for i, event in enumerate(stats["recent_events"][:5]):
                    stats_text += f"\n  {i + 1}. {event['event_id']} (推送{event['push_count']}次)"

            yield event.plain_result(stats_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取统计信息失败: {e}")
            yield event.plain_result(f"❌ 获取统计信息失败: {str(e)}")

    @filter.command_group("灾害预警配置")
    async def disaster_config(self, event: AstrMessageEvent):
        """灾害预警配置管理"""
        pass

    @disaster_config.command("查看")
    async def view_config(self, event: AstrMessageEvent):
        """查看当前配置"""
        try:
            config_summary = self._get_config_summary()
            yield event.plain_result(config_summary)
        except Exception as e:
            logger.error(f"[灾害预警] 获取配置摘要失败: {e}")
            yield event.plain_result("❌ 获取配置摘要失败")

    def _get_config_summary(self) -> str:
        """获取配置摘要"""
        summary = "⚙️ 灾害预警插件配置摘要\n\n"

        # 基本状态
        enabled = self.config.get("enabled", True)
        summary += f"🔧 插件状态：{'启用' if enabled else '禁用'}\n"

        # 目标群号 - 使用正确的配置键名
        target_groups = self.config.get("target_groups", [])
        if target_groups:
            summary += f"📢 目标群号：{len(target_groups)} 个\n"
            for group in target_groups[:5]:
                summary += f"  • {group}\n"
            if len(target_groups) > 5:
                summary += f"  ...等{len(target_groups)}个群号\n"
        else:
            summary += "📢 目标群号：未配置（将不会进行推送）\n"

        # 数据源 - 适配细粒度配置结构
        data_sources = self.config.get("data_sources", {})
        active_sources = []

        # 遍历新的配置结构，收集启用的数据源
        for service_name, service_config in data_sources.items():
            if isinstance(service_config, dict) and service_config.get(
                "enabled", False
            ):
                # 收集该服务下启用的具体数据源
                for source_name, enabled in service_config.items():
                    if (
                        source_name != "enabled"
                        and isinstance(enabled, bool)
                        and enabled
                    ):
                        active_sources.append(f"{service_name}.{source_name}")

        summary += f"\n📡 活跃数据源：{len(active_sources)} 个\n"
        for source in active_sources[:5]:
            summary += f"  • {self._format_source_name(source)}\n"
        if len(active_sources) > 5:
            summary += f"  ...等{len(active_sources)}个数据源\n"

        # 阈值设置 - 使用新的配置结构
        earthquake_filters = self.config.get("earthquake_filters", {})
        if earthquake_filters:
            summary += "\n📊 阈值设置：\n"

            # 烈度过滤器
            intensity_filter = earthquake_filters.get("intensity_filter", {})
            if intensity_filter.get("enabled", True):
                if "min_magnitude" in intensity_filter:
                    summary += (
                        f"  • 烈度过滤-最小震级：M{intensity_filter['min_magnitude']}\n"
                    )
                if "min_intensity" in intensity_filter:
                    summary += (
                        f"  • 烈度过滤-最小烈度：{intensity_filter['min_intensity']}\n"
                    )

            # 震度过滤器
            scale_filter = earthquake_filters.get("scale_filter", {})
            if scale_filter.get("enabled", True):
                if "min_magnitude" in scale_filter:
                    summary += (
                        f"  • 震度过滤-最小震级：M{scale_filter['min_magnitude']}\n"
                    )
                if "min_scale" in scale_filter:
                    summary += f"  • 震度过滤-最小震度：{scale_filter['min_scale']}\n"

            # USGS过滤器
            magnitude_only_filter = earthquake_filters.get("magnitude_only_filter", {})
            if magnitude_only_filter.get("enabled", True):
                if "min_magnitude" in magnitude_only_filter:
                    summary += f"  • USGS过滤-最小震级：M{magnitude_only_filter['min_magnitude']}\n"

        # 推送频率
        freq_control = self.config.get("push_frequency_control", {})
        if freq_control:
            summary += f"\n⏱️ 推送频率：每{freq_control.get('push_every_n_reports', 3)}报推送一次\n"

        summary += "\n💡 提示：详细配置请通过WebUI进行修改"
        return summary

    @filter.command("灾害预警日志")
    async def disaster_logs(self, event: AstrMessageEvent):
        """查看原始消息日志信息"""
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

    @filter.command("灾害预警去重统计")
    async def deduplication_stats(self, event: AstrMessageEvent):
        """查看事件去重统计信息"""
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 去重功能不可用")
            return

        try:
            stats = self.disaster_service.message_manager.deduplicator.get_deduplication_stats()

            stats_text = f"""📊 事件去重统计

⏱️ 时间窗口：{stats["time_window_minutes"]} 分钟
📏 位置容差：{stats["location_tolerance_km"]} 公里
📊 震级容差：{stats["magnitude_tolerance"]} 级

📈 当前记录：{stats["recent_events_count"]} 个事件

💡 说明：
• 同一地震事件只推送最先接收到信息的数据源
• 时间窗口内（1分钟）的相似事件会被去重
• 位置差异在20公里内视为同一事件
• 震级差异在0.5级内视为同一事件"""

            yield event.plain_result(stats_text)

        except Exception as e:
            logger.error(f"[灾害预警] 获取去重统计失败: {e}")
            yield event.plain_result(f"❌ 获取去重统计失败: {str(e)}")

    def _format_source_name(self, source_key: str) -> str:
        """格式化数据源名称 - 细粒度配置结构"""
        # 配置格式：service.source (如：fan_studio.china_earthquake_warning)
        service, source = source_key.split(".", 1)
        source_names = {
            "fan_studio": {
                "china_earthquake_warning": "中国地震网地震预警",
                "taiwan_cwa_earthquake": "台湾中央气象署强震即时警报",
                "china_cenc_earthquake": "中国地震台网地震测定",
                "japan_jma_earthquake": "日本气象厅地震情报",
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

    @filter.command("灾害预警模拟")
    async def simulate_earthquake(
        self,
        event: AstrMessageEvent,
        lat: float,
        lon: float,
        magnitude: float,
        depth: float = 10.0,
        source: str = "cea_fanstudio",
        place_name: str = "模拟测试地点"
    ):
        """模拟地震事件测试预警响应
        格式：/灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源] [地名]
        数据源可选：cea_fanstudio(默认), usgs_fanstudio, jma_p2p 等
        注意：地名如果有空格，请使用引号包裹，例如 "Test Place"
        """
        if not self.disaster_service or not self.disaster_service.message_manager:
            yield event.plain_result("❌ 服务未启动")
            return

        try:
            # 获取数据源
            from .models.models import get_data_source_from_id, DataSource, DATA_SOURCE_MAPPING
            
            data_source = get_data_source_from_id(source)
            if not data_source:
                valid_sources = ", ".join(DATA_SOURCE_MAPPING.keys())
                yield event.plain_result(f"❌ 无效的数据源: {source}\n可用数据源: {valid_sources}")
                return

            # 1. 构造模拟数据
            from datetime import datetime
            from .utils.fe_regions import translate_place_name
            
            # 尝试翻译地名
            final_place_name = translate_place_name(place_name, lat, lon)
            
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
                raw_data={"test": True, "source_id": source}
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
                source_id=source
            )

            manager = self.disaster_service.message_manager
            
            # 分开的消息构建
            report_lines = [
                "🧪 **灾害预警模拟报告**",
                f"Input: M{magnitude} @ ({lat}, {lon}), Depth {depth}km\n"
            ]

            # 2. 检查全局过滤器 (Global Filters)
            global_pass = True
            if manager.intensity_filter:
                if manager.intensity_filter.should_filter(earthquake):
                    global_pass = False
                    report_lines.append(f"❌ **全局过滤**: 拦截 (不满足最小震级/烈度要求)")
                else:
                    report_lines.append(f"✅ **全局过滤**: 通过")
            
            # 3. 检查本地监控 (Local Monitor)
            local_pass = True
            if manager.local_monitor and manager.local_monitor.enabled:
                allowed, dist, inte = manager.local_monitor.check_event(earthquake)
                
                # 为了模拟真实流程，手动注入 local_estimation
                disaster_event.raw_data["local_estimation"] = {
                    "distance": dist,
                    "intensity": inte
                }

                if allowed:
                    report_lines.append(f"✅ **本地监控**: 触发")
                else:
                    local_pass = False
                    report_lines.append(f"❌ **本地监控**: 拦截 (严格模式生效中)")
                    
                report_lines.append(f"   ⦁ 严格模式: {'开启' if manager.local_monitor.strict_mode else '关闭 (仅计算不拦截)'}")
                report_lines.extend([
                    f"   ⦁ 距本地: {dist:.1f}km",
                    f"   ⦁ 预估本地烈度: {inte:.1f}级",
                    f"   ⦁ 本地阈值: {manager.local_monitor.threshold}级"
                ])
            else:
                report_lines.append(f"ℹ️ **本地监控**: 未启用")

            # 发送报告
            yield event.plain_result("\n".join(report_lines))
            
            # 稍作等待，确保第一条消息发出
            await asyncio.sleep(1)

            # 4. 模拟消息构建
            if global_pass and local_pass:
                try:
                    logger.info("[灾害预警] 开始构建模拟预警消息...")
                    msg_chain = manager._build_message(disaster_event)
                    logger.info(f"[灾害预警] 消息构建成功，链长度: {len(msg_chain.chain)}")
                    
                    # 直接使用context发送消息，绕过command generator
                    await self.context.send_message(event.unified_msg_origin, msg_chain)
                except Exception as build_e:
                     import traceback
                     logger.error(f"[灾害预警] 消息构建失败: {build_e}\n{traceback.format_exc()}")
                     yield event.plain_result(f"❌ 消息构建失败: {build_e}")
            else:
                yield event.plain_result("\n⛔ **结论**: 该事件不会触发预警推送。")

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"[灾害预警] 模拟测试失败: {e}\n{error_trace}")
            yield event.plain_result(f"❌ 模拟失败: {e}")

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot加载完成时的钩子"""
        logger.info("[灾害预警] AstrBot已加载完成，灾害预警插件准备就绪")

